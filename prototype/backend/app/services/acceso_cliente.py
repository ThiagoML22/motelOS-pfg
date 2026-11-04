"""El cliente en su habitación: con el QR de su ticket ve su tiempo y su cuenta y le pide algo a la ventanilla.

No hay cuenta ni datos personales. El enlace lleva el turno y una firma del servidor (HMAC): no se puede inventar ni
pasar al turno de otro, no hace falta guardar nada, y sirve solo mientras el turno está en curso. Por eso va en un
ticket y no pegado en la habitación: un código fijo le mostraría la cuenta del siguiente cliente a quien lo fotografió.

El cliente no ve la patente, ni quién atiende, ni nada de la caja. Un pedido no toca el stock ni la cuenta: el conserje
lo atiende, y recién ahí se carga como consumo con las reglas de siempre.
"""

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.articulo import Articulo
from app.models.categoria import CategoriaHabitacion
from app.models.consumo import Consumo
from app.models.establecimiento import Establecimiento
from app.models.habitacion import Habitacion
from app.models.pedido_cliente import ARTICULO, ATENDIDO, AVISOS, PENDIENTE, RECHAZADO, PedidoCliente
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services.billing_service import calcular_sobreturno
from app.services.liquidacion import con_zona, liquidar_turno

LARGO_FIRMA = 22
# Hasta acá llega lo que un enlace puede pedir: alcanza para una estadía y frena a quien lo use para molestar.
MAXIMO_PENDIENTES = 3
MAXIMO_POR_TURNO = 30
MAXIMA_CANTIDAD = 5
# Hasta dónde se busca el próximo cargo por sobreturno.
HORIZONTE_MIN = 720


def _firma(establecimiento_id: int, turno_id: str) -> str:
    clave = hmac.new(settings.JWT_SECRET.encode(), b"acceso-cliente", hashlib.sha256).digest()
    resumen = hmac.new(clave, f"{establecimiento_id}.{turno_id}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(resumen).decode().rstrip("=")[:LARGO_FIRMA]


def token_de(establecimiento_id: int, turno_id: uuid.UUID) -> str:
    return f"{establecimiento_id}.{turno_id.hex}.{_firma(establecimiento_id, turno_id.hex)}"


def leer_token(token: str) -> tuple[int, uuid.UUID] | None:
    partes = token.split(".")
    if len(partes) != 3:
        return None
    establecimiento, turno, firma = partes
    if not establecimiento.isdigit() or not hmac.compare_digest(firma, _firma(int(establecimiento), turno)):
        return None
    try:
        return int(establecimiento), uuid.UUID(turno)
    except ValueError:
        return None


def direccion_de(token: str) -> str:
    return f"{settings.url_aplicacion}/?cliente={token}"


def _proximo_cargo(tarifa: Tarifa, minutos: float, sobreturno: Decimal) -> dict | None:
    """En cuánto se suma la próxima fracción y cuánto. Nada si ya llegó al tope."""
    parametros = tarifa.parametros()
    for extra in range(1, HORIZONTE_MIN):
        despues = calcular_sobreturno(timedelta(minutes=minutos + extra), parametros)
        if despues > sobreturno:
            return {"minutos": extra, "monto": float(despues - sobreturno)}
    return None


def _pedido(pedido: PedidoCliente, nombres: dict[int, str]) -> dict:
    return {
        "id": pedido.id,
        "tipo": pedido.tipo,
        "descripcion": nombres.get(pedido.articulo_id, "Artículo") if pedido.tipo == ARTICULO else AVISOS[pedido.tipo],
        "cantidad": pedido.cantidad,
        "estado": pedido.estado,
    }


async def estadia(db: AsyncSession, turno: Turno) -> dict:
    """Lo que ve el cliente. Solo se consulta: el cálculo no se guarda desde acá."""
    establecimiento = await db.get(Establecimiento, turno.establecimiento_id)
    marca = {"motel": establecimiento.nombre, "color_marca": establecimiento.color_marca}
    if turno.estado != "En Curso":
        return {"activa": False, **marca}
    liquidacion = await liquidar_turno(db, turno)
    tarifa = await db.get(Tarifa, turno.tarifa_id)
    habitacion = await db.get(Habitacion, turno.habitacion_id)
    categoria = await db.get(CategoriaHabitacion, tarifa.categoria_id)
    articulos = list(
        (await db.execute(select(Articulo).where(Articulo.activo.is_(True)).order_by(Articulo.descripcion))).scalars()
    )
    nombres = {a.id: a.descripcion for a in articulos}
    consumos = list((await db.execute(select(Consumo).where(Consumo.turno_id == turno.id))).scalars())
    pedidos = list(
        (
            await db.execute(
                select(PedidoCliente).where(PedidoCliente.turno_id == turno.id).order_by(PedidoCliente.id.desc())
            )
        ).scalars()
    )
    ahora = datetime.now(UTC)
    minutos = (ahora - con_zona(turno.hora_inicio)).total_seconds() / 60
    respuesta = {
        "activa": True,
        **marca,
        "numero": habitacion.numero,
        "categoria": categoria.nombre if categoria else None,
        "hora_inicio": con_zona(turno.hora_inicio).isoformat(),
        "ahora": ahora.isoformat(),
        "estadia_base_min": tarifa.estadia_base_min,
        "tarifa_base": float(turno.tarifa_base),
        "total_sobreturno": float(turno.total_sobreturno),
        "total_consumos": float(turno.total_consumos),
        "total": float(liquidacion.saldo_pendiente),
        "proximo_cargo": _proximo_cargo(tarifa, minutos, Decimal(str(turno.total_sobreturno))),
        "consumos": [
            {
                "descripcion": nombres.get(c.articulo_id, "Artículo"),
                "cantidad": c.cantidad,
                "subtotal": float(c.subtotal),
            }
            for c in consumos
        ],
        "articulos": [
            {"id": a.id, "descripcion": a.descripcion, "precio": float(a.precio_unitario), "categoria": a.categoria}
            for a in articulos
            if a.stock_actual > 0
        ],
        "avisos": [{"tipo": tipo, "descripcion": texto} for tipo, texto in AVISOS.items()],
        "pedidos": [_pedido(p, nombres) for p in pedidos[:10]],
    }
    await db.rollback()
    return respuesta


async def pedir(db: AsyncSession, turno: Turno, tipo: str, articulo_id: int | None, cantidad: int | None) -> dict:
    if turno.estado != "En Curso":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta estadía ya terminó.")
    if tipo != ARTICULO and tipo not in AVISOS:
        raise HTTPException(status_code=422, detail="Pedido desconocido.")
    del_turno = list((await db.execute(select(PedidoCliente).where(PedidoCliente.turno_id == turno.id))).scalars())
    pendientes = [p for p in del_turno if p.estado == PENDIENTE]
    if len(pendientes) >= MAXIMO_PENDIENTES or len(del_turno) >= MAXIMO_POR_TURNO:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ya tenés pedidos en camino. Esperá a que te los traigan para pedir otra cosa.",
        )
    if tipo == ARTICULO:
        cantidad = cantidad or 1
        if not 1 <= cantidad <= MAXIMA_CANTIDAD or articulo_id is None:
            raise HTTPException(status_code=422, detail=f"Se pueden pedir hasta {MAXIMA_CANTIDAD} por vez.")
        articulo = (await db.execute(select(Articulo).where(Articulo.id == articulo_id))).scalars().first()
        if articulo is None or not articulo.activo or articulo.stock_actual < cantidad:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese artículo no está disponible.")
    else:
        articulo_id, cantidad = None, None
        if any(p.tipo == tipo for p in pendientes):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya lo avisamos: enseguida te atienden.")
    db.add(PedidoCliente(turno_id=turno.id, tipo=tipo, articulo_id=articulo_id, cantidad=cantidad))
    await db.commit()
    return {"ok": True}


async def pendientes_de_la_ventanilla(db: AsyncSession) -> list[dict]:
    """Los pedidos sin atender de los turnos en curso, del más viejo al más nuevo."""
    filas = (
        await db.execute(
            select(
                PedidoCliente, Turno.habitacion_id, Habitacion.numero, Articulo.descripcion, Articulo.precio_unitario
            )
            .join(Turno, Turno.id == PedidoCliente.turno_id)
            .join(Habitacion, Habitacion.id == Turno.habitacion_id)
            .outerjoin(Articulo, Articulo.id == PedidoCliente.articulo_id)
            .where(PedidoCliente.estado == PENDIENTE, Turno.estado == "En Curso")
            .order_by(PedidoCliente.creado_en, PedidoCliente.id)
        )
    ).all()
    return [
        {
            "id": pedido.id,
            "turno_id": str(pedido.turno_id),
            "habitacion_id": habitacion_id,
            "numero": numero,
            "tipo": pedido.tipo,
            "descripcion": descripcion if pedido.tipo == ARTICULO else AVISOS[pedido.tipo],
            "cantidad": pedido.cantidad,
            "subtotal": float(precio * pedido.cantidad) if pedido.tipo == ARTICULO and precio is not None else None,
            "creado_en": con_zona(pedido.creado_en).isoformat(),
        }
        for pedido, habitacion_id, numero, descripcion, precio in filas
    ]


async def bloquear_pendiente(db: AsyncSession, pedido_id: int) -> PedidoCliente:
    pedido = (
        (await db.execute(select(PedidoCliente).where(PedidoCliente.id == pedido_id).with_for_update()))
        .scalars()
        .first()
    )
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El pedido no existe.")
    if pedido.estado != PENDIENTE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese pedido ya se atendió.")
    return pedido


def resolver(pedido: PedidoCliente, operador_id: int, atendido: bool) -> None:
    pedido.estado = ATENDIDO if atendido else RECHAZADO
    pedido.atendido_por_id = operador_id
    pedido.atendido_en = datetime.now(UTC)
