"""Pedidos de reposición a proveedores (migración 010).

La gerencia arma el pedido (puede partir de la reposición sugerida por la inteligencia) y lo descarga en PDF para el
proveedor. Cuando llega la mercadería, el conserje o la gerencia lo recibe con las cantidades reales: se suman al stock
y cada una queda en el registro de actividad (lo que recibe un conserje, «por revisar»).
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.config import settings
from app.core.database import get_db
from app.models.actividad import INVENTARIO
from app.models.articulo import Articulo
from app.models.establecimiento import Establecimiento
from app.models.operador import ROL_ADMINISTRADOR, Operador
from app.models.pedido import ANULADO, PENDIENTE, RECIBIDO, PedidoItem, PedidoReposicion
from app.services import inteligencia
from app.services.actividad import registrar
from app.services.liquidacion import con_zona
from app.services.pdf import ALTO_A4, ANCHO_A4, DocumentoPDF

router = APIRouter()


class ItemAlta(BaseModel):
    articulo_id: int
    cantidad: int = Field(gt=0, le=10000)


class PedidoAlta(BaseModel):
    proveedor: str | None = Field(default=None, max_length=80)
    nota: str | None = Field(default=None, max_length=300)
    items: list[ItemAlta] = Field(min_length=1, max_length=100)


class ItemRecepcion(BaseModel):
    articulo_id: int
    recibida: int = Field(ge=0, le=10000)


class Recepcion(BaseModel):
    items: list[ItemRecepcion] = Field(min_length=1, max_length=100)


class ItemResponse(BaseModel):
    articulo_id: int
    codigo: str
    descripcion: str
    cantidad: int
    recibida: int | None = None
    stock_actual: int


class PedidoResponse(BaseModel):
    id: int
    creado_en: datetime
    creado_por_nombre: str
    proveedor: str | None = None
    nota: str | None = None
    estado: str
    cerrado_en: datetime | None = None
    cerrado_por_nombre: str | None = None
    items: list[ItemResponse]


class Sugerido(BaseModel):
    articulo_id: int
    codigo: str
    descripcion: str
    stock: int
    por_dia: float
    dias_restantes: float | None = None
    sugerido: int


def _solo_gerencia(operador: Operador) -> None:
    if operador.rol != ROL_ADMINISTRADOR:
        raise HTTPException(status_code=403, detail="Los pedidos los arma y los anula la gerencia.")


async def _respuestas(db: AsyncSession, pedidos: list[PedidoReposicion]) -> list[PedidoResponse]:
    if not pedidos:
        return []
    nombres = {i: n for i, n in (await db.execute(select(Operador.id, Operador.nombre_visible))).all()}
    articulos = {a.id: a for a in (await db.execute(select(Articulo))).scalars()}
    items = list(
        (await db.execute(select(PedidoItem).where(PedidoItem.pedido_id.in_([p.id for p in pedidos])))).scalars()
    )
    respuesta = []
    for p in pedidos:
        propios = sorted((i for i in items if i.pedido_id == p.id), key=lambda i: articulos[i.articulo_id].descripcion)
        respuesta.append(
            PedidoResponse(
                id=p.id,
                creado_en=p.creado_en,
                creado_por_nombre=nombres.get(p.creado_por_id, "—"),
                proveedor=p.proveedor,
                nota=p.nota,
                estado=p.estado,
                cerrado_en=p.cerrado_en,
                cerrado_por_nombre=nombres.get(p.cerrado_por_id) if p.cerrado_por_id else None,
                items=[
                    ItemResponse(
                        articulo_id=i.articulo_id,
                        codigo=articulos[i.articulo_id].codigo,
                        descripcion=articulos[i.articulo_id].descripcion,
                        cantidad=i.cantidad,
                        recibida=i.recibida,
                        stock_actual=articulos[i.articulo_id].stock_actual,
                    )
                    for i in propios
                ],
            )
        )
    return respuesta


async def _pedido(db: AsyncSession, pedido_id: int, bloquear: bool = False) -> PedidoReposicion:
    consulta = select(PedidoReposicion).where(PedidoReposicion.id == pedido_id)
    if bloquear:
        consulta = consulta.with_for_update()
    pedido = (await db.execute(consulta)).scalars().first()
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado.")
    return pedido


@router.get("/", response_model=list[PedidoResponse])
async def listar(db: AsyncSession = Depends(get_db)):
    """Los pendientes primero; después los últimos 15 cerrados."""
    pendientes = list(
        (
            await db.execute(
                select(PedidoReposicion)
                .where(PedidoReposicion.estado == PENDIENTE)
                .order_by(PedidoReposicion.creado_en.desc())
            )
        ).scalars()
    )
    cerrados = list(
        (
            await db.execute(
                select(PedidoReposicion)
                .where(PedidoReposicion.estado != PENDIENTE)
                .order_by(PedidoReposicion.cerrado_en.desc())
                .limit(15)
            )
        ).scalars()
    )
    return await _respuestas(db, pendientes + cerrados)


@router.get("/sugerido", response_model=list[Sugerido])
async def sugerido(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    """La reposición sugerida por la inteligencia (lo que falta para cubrir dos semanas), para armar el pedido."""
    _solo_gerencia(operador)
    ctx = await inteligencia.contexto(db)
    return [Sugerido(**r) for r in inteligencia.reposicion(ctx) if r["sugerido"] > 0]


@router.post("/", response_model=PedidoResponse, status_code=status.HTTP_201_CREATED)
async def crear(datos: PedidoAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    _solo_gerencia(operador)
    ids = [i.articulo_id for i in datos.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(status_code=422, detail="Cada artículo va una sola vez en el pedido.")
    articulos = {
        a.id: a
        for a in (await db.execute(select(Articulo).where(Articulo.id.in_(ids), Articulo.activo.is_(True)))).scalars()
    }
    if len(articulos) != len(ids):
        raise HTTPException(status_code=404, detail="Algún artículo no existe o está dado de baja.")
    pedido = PedidoReposicion(
        creado_por_id=operador.id,
        proveedor=(datos.proveedor or "").strip() or None,
        nota=(datos.nota or "").strip() or None,
    )
    db.add(pedido)
    await db.flush()
    db.add_all(PedidoItem(pedido_id=pedido.id, articulo_id=i.articulo_id, cantidad=i.cantidad) for i in datos.items)
    unidades = sum(i.cantidad for i in datos.items)
    await registrar(
        db,
        operador,
        INVENTARIO,
        "PEDIDO_ALTA",
        f"Pedido N.º {pedido.id}{f' a {pedido.proveedor}' if pedido.proveedor else ''}: {len(ids)} artículos, "
        f"{unidades} u.",
        cantidad=unidades,
    )
    await db.commit()
    return (await _respuestas(db, [await _pedido(db, pedido.id)]))[0]


@router.post("/{pedido_id}/recepcion", response_model=PedidoResponse)
async def recibir(
    pedido_id: int, datos: Recepcion, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    """Registra lo que llegó de cada artículo, lo suma al stock y cierra el pedido como Recibido."""
    pedido = await _pedido(db, pedido_id, bloquear=True)
    if pedido.estado != PENDIENTE:
        raise HTTPException(status_code=409, detail=f"El pedido ya está {pedido.estado.lower()}.")
    items = {
        i.articulo_id: i
        for i in (await db.execute(select(PedidoItem).where(PedidoItem.pedido_id == pedido.id))).scalars()
    }
    recibidas = {i.articulo_id: i.recibida for i in datos.items}
    if set(recibidas) != set(items):
        raise HTTPException(status_code=422, detail="Indique lo recibido de cada artículo del pedido (0 si no llegó).")
    articulos = {
        a.id: a
        for a in (await db.execute(select(Articulo).where(Articulo.id.in_(list(items))).with_for_update())).scalars()
    }
    for articulo_id, item in items.items():
        cantidad = recibidas[articulo_id]
        item.recibida = cantidad
        if cantidad == 0:
            continue
        articulo = articulos[articulo_id]
        anterior = articulo.stock_actual
        articulo.stock_actual = anterior + cantidad
        faltan = f" (se pidieron {item.cantidad})" if cantidad != item.cantidad else ""
        await registrar(
            db,
            operador,
            INVENTARIO,
            "ARTICULO_REPOSICION",
            f"Recepción del pedido N.º {pedido.id}: {cantidad} u. de {articulo.descripcion}{faltan}",
            articulo_id=articulo.id,
            cantidad=cantidad,
            valor_anterior=f"{anterior} u.",
            valor_nuevo=f"{articulo.stock_actual} u.",
        )
    await db.flush()
    pedido.estado = RECIBIDO
    pedido.cerrado_por_id = operador.id
    pedido.cerrado_en = datetime.now(UTC)
    await db.commit()
    return (await _respuestas(db, [await _pedido(db, pedido.id)]))[0]


@router.post("/{pedido_id}/anulacion", response_model=PedidoResponse)
async def anular(pedido_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    _solo_gerencia(operador)
    pedido = await _pedido(db, pedido_id, bloquear=True)
    if pedido.estado != PENDIENTE:
        raise HTTPException(status_code=409, detail=f"El pedido ya está {pedido.estado.lower()}.")
    pedido.estado = ANULADO
    pedido.cerrado_por_id = operador.id
    pedido.cerrado_en = datetime.now(UTC)
    await registrar(db, operador, INVENTARIO, "PEDIDO_ANULADO", f"Pedido N.º {pedido.id} anulado")
    await db.commit()
    return (await _respuestas(db, [await _pedido(db, pedido.id)]))[0]


@router.get("/{pedido_id}/pedido.pdf", response_class=Response)
async def pdf(pedido_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    """El pedido para mandar al proveedor: artículos y cantidades, sin precios de venta."""
    pedido = (await _respuestas(db, [await _pedido(db, pedido_id)]))[0]
    establecimiento = await db.get(Establecimiento, operador.establecimiento_id)
    zona = ZoneInfo(settings.ZONA_HORARIA)
    documento = DocumentoPDF(f"Pedido N.º {pedido.id}")
    pagina = documento.nueva_pagina()
    margen, y = 50, ALTO_A4 - 60
    pagina.texto(margen, y, establecimiento.nombre if establecimiento else "MotelOS", 16, negrita=True)
    if establecimiento and (establecimiento.domicilio or establecimiento.telefono):
        y -= 16
        pagina.texto(margen, y, " · ".join(v for v in (establecimiento.domicilio, establecimiento.telefono) if v), 9)
    y -= 30
    pagina.texto(margen, y, f"Pedido de mercadería N.º {pedido.id}", 13, negrita=True)
    pagina.texto_derecha(ANCHO_A4 - margen, y, f"{con_zona(pedido.creado_en).astimezone(zona):%d/%m/%Y}", 10)
    y -= 18
    if pedido.proveedor:
        pagina.texto(margen, y, f"Proveedor: {pedido.proveedor}", 10)
        y -= 16
    y -= 10
    pagina.rectangulo(margen, y - 5, ANCHO_A4 - 2 * margen, 18, gris=0.92)
    pagina.texto(margen + 6, y, "Código", 9, negrita=True)
    pagina.texto(margen + 90, y, "Artículo", 9, negrita=True)
    pagina.texto_derecha(ANCHO_A4 - margen - 6, y, "Cantidad", 9, negrita=True)
    y -= 20
    for item in pedido.items:
        pagina.texto(margen + 6, y, item.codigo, 9.5)
        pagina.texto(margen + 90, y, item.descripcion[:60], 9.5)
        pagina.texto_derecha(ANCHO_A4 - margen - 6, y, f"{item.cantidad} u.", 9.5, negrita=True)
        pagina.linea(margen, y - 6, ANCHO_A4 - margen, y - 6, grosor=0.2)
        y -= 18
    y -= 6
    pagina.texto_derecha(
        ANCHO_A4 - margen - 6, y, f"Total: {sum(i.cantidad for i in pedido.items)} unidades", 10, negrita=True
    )
    if pedido.nota:
        y -= 26
        pagina.texto(margen, y, f"Nota: {pedido.nota}", 9.5)
    y -= 60
    pagina.linea(margen, y, margen + 180, y)
    pagina.texto(margen, y - 12, f"Pidió: {pedido.creado_por_nombre}", 8.5)
    pagina.texto(margen, 30, "MotelOS · pedido generado por el sistema", 7.5)
    return Response(
        content=documento.generar(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="pedido-{pedido.id}.pdf"'},
    )
