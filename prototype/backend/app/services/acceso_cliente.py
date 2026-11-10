"""El cliente en su habitación: con el QR de su ticket ve su tiempo y su cuenta y le pide algo a la ventanilla.

No hay cuenta ni datos personales. El enlace lleva el turno y una firma del servidor (HMAC): no se puede inventar ni
pasar al turno de otro, no hace falta guardar nada, y sirve solo mientras el turno está en curso. Por eso va en un
ticket y no pegado en la habitación: un código fijo le mostraría la cuenta del siguiente cliente a quien lo fotografió.

El cliente no ve la patente, ni quién atiende, ni nada de la caja. Un pedido no toca el stock ni la cuenta: el conserje
lo atiende, y recién ahí se carga como consumo con las reglas de siempre. Avisar que se queda más o pedir la cuenta
tampoco cobra nada: lo que se paga sale siempre del tiempo real y se cobra en la ventanilla.

Mot responde lo mismo que la pantalla ya sabe, con botones: el cliente no escribe texto libre. Se puede calificar hasta
una hora después del cobro; el resto del enlace deja de servir al cerrar el turno.
"""

import base64
import hashlib
import hmac
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.articulo import Articulo
from app.models.calificacion import PROBLEMAS, VENTANA_DESPUES_DEL_COBRO_MIN, Calificacion
from app.models.categoria import CategoriaHabitacion
from app.models.consumo import Consumo
from app.models.establecimiento import Establecimiento
from app.models.franja_tarifa import FranjaTarifa
from app.models.habitacion import Habitacion
from app.models.pedido_cliente import (
    ARTICULO,
    ATENDIDO,
    AVISOS,
    AVISOS_DIRECTOS,
    EN_CAMINO,
    MEDIOS_PAGO,
    MINUTOS_EXTRA,
    PENDIENTE,
    RECHAZADO,
    SALIDA,
    SIN_RESOLVER,
    TIEMPO,
    PedidoCliente,
)
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services.actividad import pesos
from app.services.billing_service import calcular_sobreturno
from app.services.liquidacion import con_zona, liquidar_turno

LARGO_FIRMA = 22
# Hasta acá llega lo que un enlace puede pedir: alcanza para una estadía y frena a quien lo use para molestar.
MAXIMO_PENDIENTES = 3
MAXIMO_POR_TURNO = 30
MAXIMA_CANTIDAD = 5
MAXIMAS_LINEAS = 8
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


def _duracion_texto(minutos: int) -> str:
    horas, resto = divmod(minutos, 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h {resto} min" if resto else f"{horas} h"


def _hora(momento: datetime) -> str:
    return momento.astimezone(ZoneInfo(settings.ZONA_HORARIA)).strftime("%H:%M")


def descripcion_de(tipo: str, articulo: str | None, minutos: int | None, medio_pago: str | None) -> str:
    if tipo == ARTICULO:
        return articulo or "Artículo"
    if tipo == TIEMPO and minutos:
        return f"Se queda {_duracion_texto(minutos)} más"
    if tipo == SALIDA and medio_pago:
        return f"Pide la cuenta: paga con {MEDIOS_PAGO[medio_pago].lower()}"
    return AVISOS[tipo]


def _pedido(pedido: PedidoCliente, nombres: dict[int, str]) -> dict:
    return {
        "id": pedido.id,
        "tipo": pedido.tipo,
        "descripcion": descripcion_de(pedido.tipo, nombres.get(pedido.articulo_id), pedido.minutos, pedido.medio_pago),
        "cantidad": pedido.cantidad,
        "estado": pedido.estado,
        "lote": str(pedido.lote) if pedido.lote else None,
    }


def _opciones_de_tiempo(tarifa: Tarifa, inicio: datetime, minutos: float, sobreturno: Decimal) -> list[dict]:
    """Cuánto se sumaría a la cuenta por quedarse más. Se cuenta desde el fin de la estadía base o desde ahora, lo que
    sea más tarde, con la misma cuenta que hace el cobro: incluye la tolerancia y el tope."""
    parametros = tarifa.parametros()
    desde = max(minutos, float(tarifa.estadia_base_min))
    opciones = []
    for extra in MINUTOS_EXTRA:
        despues = calcular_sobreturno(timedelta(minutes=desde + extra), parametros)
        opciones.append(
            {
                "minutos": extra,
                "etiqueta": _duracion_texto(extra),
                "suma": float(max(despues - sobreturno, Decimal(0))),
                "hasta": (inicio + timedelta(minutes=desde + extra)).isoformat(),
            }
        )
    return opciones


def _respuestas_de_mot(
    establecimiento: Establecimiento,
    tarifa: Tarifa,
    turno: Turno,
    inicio: datetime,
    minutos: float,
    total: Decimal,
) -> list[dict]:
    """Lo que Mot le contesta al cliente: cada pregunta es un botón y sale de los datos de su estadía."""
    fin_base = inicio + timedelta(minutes=tarifa.estadia_base_min)
    extra = f"{pesos(tarifa.tarifa_fraccion)} cada {_duracion_texto(tarifa.fraccion_min)}"
    if minutos <= tarifa.estadia_base_min:
        salida = (
            f"Tu estadía incluye {_duracion_texto(tarifa.estadia_base_min)}: llega hasta las {_hora(fin_base)}. "
            f"Después se suman {extra}."
        )
    else:
        salida = f"Tu estadía base terminó a las {_hora(fin_base)}. Ahora se suman {extra}."
    if tarifa.tope is not None:
        salida += f" La estadía nunca pasa de {pesos(tarifa.tope)}."
    gasto = f"Hasta ahora son {pesos(total)}: {pesos(turno.tarifa_base)} de la estadía"
    if turno.total_sobreturno:
        gasto += f", {pesos(turno.total_sobreturno)} de tiempo extra"
    if turno.total_consumos:
        gasto += f" y {pesos(turno.total_consumos)} de lo que pediste"
    respuestas = []
    if establecimiento.wifi_nombre:
        clave = f" y la clave es {establecimiento.wifi_clave}" if establecimiento.wifi_clave else ""
        red = f"La red es {establecimiento.wifi_nombre}{clave}."
        respuestas.append({"id": "wifi", "pregunta": "¿Cuál es el Wi-Fi?", "respuesta": red})
    return respuestas + [
        {"id": "salida", "pregunta": "¿Hasta qué hora estoy?", "respuesta": salida},
        {"id": "gasto", "pregunta": "¿Cuánto llevo gastado?", "respuesta": f"{gasto}."},
        {
            "id": "pedir",
            "pregunta": "¿Cómo pido algo?",
            "respuesta": "Elegí lo que quieras en «Pedir». Te lo llevan a la habitación y recién ahí se suma a tu "
            "cuenta.",
        },
        {
            "id": "pago",
            "pregunta": "¿Cómo pago?",
            "respuesta": "En la ventanilla, al salir: efectivo, tarjeta o Mercado Pago. Con «Pedir la cuenta» te la "
            "dejamos lista.",
        },
        {
            "id": "datos",
            "pregunta": "¿Guardan mis datos?",
            "respuesta": "No. Esta página no pide cuenta ni datos tuyos, y deja de funcionar cuando te vas.",
        },
    ]


def _puede_calificar(turno: Turno, ahora: datetime) -> bool:
    if turno.estado == "En Curso":
        return True
    limite = timedelta(minutes=VENTANA_DESPUES_DEL_COBRO_MIN)
    return turno.hora_fin is not None and ahora - con_zona(turno.hora_fin) <= limite


async def _calificacion(db: AsyncSession, turno: Turno) -> Calificacion | None:
    consulta = select(Calificacion).where(Calificacion.turno_id == turno.id)
    return (await db.execute(consulta)).scalars().first()


def _problemas() -> list[dict]:
    return [{"valor": valor, "etiqueta": etiqueta} for valor, etiqueta in PROBLEMAS.items()]


async def estadia(db: AsyncSession, turno: Turno) -> dict:
    """Lo que ve el cliente. Solo se consulta: el cálculo no se guarda desde acá."""
    establecimiento = await db.get(Establecimiento, turno.establecimiento_id)
    marca = {"motel": establecimiento.nombre, "color_marca": establecimiento.color_marca}
    calificada = await _calificacion(db, turno) is not None
    if turno.estado != "En Curso":
        return {
            "activa": False,
            **marca,
            "puede_calificar": _puede_calificar(turno, datetime.now(UTC)) and not calificada,
            "problemas": _problemas(),
        }
    liquidacion = await liquidar_turno(db, turno)
    tarifa = await db.get(Tarifa, turno.tarifa_id)
    habitacion = await db.get(Habitacion, turno.habitacion_id)
    categoria = await db.get(CategoriaHabitacion, tarifa.categoria_id)
    franja = await db.get(FranjaTarifa, tarifa.franja_id) if tarifa.franja_id else None
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
    inicio = con_zona(turno.hora_inicio)
    minutos = (ahora - inicio).total_seconds() / 60
    sobreturno = Decimal(str(turno.total_sobreturno))
    respuesta = {
        "activa": True,
        **marca,
        "numero": habitacion.numero,
        "categoria": categoria.nombre if categoria else None,
        "franja": franja.nombre if franja else None,
        "bienvenida": establecimiento.bienvenida,
        "hora_inicio": inicio.isoformat(),
        "ahora": ahora.isoformat(),
        "estadia_base_min": tarifa.estadia_base_min,
        "tarifa_base": float(turno.tarifa_base),
        "total_sobreturno": float(turno.total_sobreturno),
        "total_consumos": float(turno.total_consumos),
        "total": float(liquidacion.saldo_pendiente),
        "proximo_cargo": _proximo_cargo(tarifa, minutos, sobreturno),
        "opciones_tiempo": _opciones_de_tiempo(tarifa, inicio, minutos, sobreturno),
        "medios_pago": [{"medio": medio, "etiqueta": etiqueta} for medio, etiqueta in MEDIOS_PAGO.items()],
        "mot": _respuestas_de_mot(establecimiento, tarifa, turno, inicio, minutos, liquidacion.saldo_pendiente),
        "calificada": calificada,
        "problemas": _problemas(),
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
        "avisos": [{"tipo": tipo, "descripcion": AVISOS[tipo]} for tipo in AVISOS_DIRECTOS],
        "pedidos": [_pedido(p, nombres) for p in pedidos[:20]],
    }
    await db.rollback()
    return respuesta


async def _sin_resolver(db: AsyncSession, turno: Turno, nuevas: int = 1) -> list[PedidoCliente]:
    """Lo que el turno tiene sin resolver, si todavía puede pedir `nuevas` líneas. Un carrito cuenta como un pedido."""
    if turno.estado != "En Curso":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta estadía ya terminó.")
    del_turno = list((await db.execute(select(PedidoCliente).where(PedidoCliente.turno_id == turno.id))).scalars())
    abiertos = [p for p in del_turno if p.estado in SIN_RESOLVER]
    pedidos = {p.lote or p.id for p in abiertos}
    if len(pedidos) >= MAXIMO_PENDIENTES or len(del_turno) + nuevas > MAXIMO_POR_TURNO:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ya tenés pedidos en camino. Esperá a que te los traigan para pedir otra cosa.",
        )
    return abiertos


async def pedir_carrito(db: AsyncSession, turno: Turno, lineas: list[tuple[int, int]]) -> dict:
    """Varios artículos, un solo pedido: entra completo o no entra."""
    juntas: Counter[int] = Counter()
    for articulo_id, cantidad in lineas:
        juntas[articulo_id] += cantidad
    await _sin_resolver(db, turno, len(juntas))
    if any(cantidad > MAXIMA_CANTIDAD for cantidad in juntas.values()):
        raise HTTPException(status_code=422, detail=f"Se pueden pedir hasta {MAXIMA_CANTIDAD} por vez.")
    articulos = {
        a.id: a for a in (await db.execute(select(Articulo).where(Articulo.id.in_(juntas)))).scalars()
    }
    for articulo_id, cantidad in juntas.items():
        articulo = articulos.get(articulo_id)
        if articulo is None or not articulo.activo or articulo.stock_actual < cantidad:
            nombre = articulo.descripcion if articulo else "Ese artículo"
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{nombre} no está disponible.")
    lote = uuid.uuid4()
    for articulo_id, cantidad in juntas.items():
        db.add(PedidoCliente(turno_id=turno.id, tipo=ARTICULO, articulo_id=articulo_id, cantidad=cantidad, lote=lote))
    await db.commit()
    return {"ok": True}


async def pedir(
    db: AsyncSession,
    turno: Turno,
    tipo: str,
    articulo_id: int | None,
    cantidad: int | None,
    minutos: int | None = None,
    medio_pago: str | None = None,
) -> dict:
    if tipo != ARTICULO and tipo not in AVISOS:
        raise HTTPException(status_code=422, detail="Pedido desconocido.")
    if tipo == TIEMPO and minutos not in MINUTOS_EXTRA:
        raise HTTPException(status_code=422, detail="Elegí cuánto tiempo más te quedás.")
    if tipo == SALIDA and medio_pago is not None and medio_pago not in MEDIOS_PAGO:
        raise HTTPException(status_code=422, detail="Ese medio de pago no existe.")
    pendientes = await _sin_resolver(db, turno)
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
    db.add(
        PedidoCliente(
            turno_id=turno.id,
            tipo=tipo,
            articulo_id=articulo_id,
            cantidad=cantidad,
            minutos=minutos if tipo == TIEMPO else None,
            medio_pago=medio_pago if tipo == SALIDA else None,
        )
    )
    await db.commit()
    return {"ok": True}


async def calificar(db: AsyncSession, turno: Turno, puntaje: int, problemas: int) -> dict:
    if not _puede_calificar(turno, datetime.now(UTC)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pasó el tiempo para calificar esta estadía.")
    if await _calificacion(db, turno) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya calificaste esta estadía. ¡Gracias!")
    db.add(Calificacion(turno_id=turno.id, habitacion_id=turno.habitacion_id, puntaje=puntaje, problemas=problemas))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya calificaste esta estadía. ¡Gracias!"
        ) from None
    return {"ok": True}


async def pendientes_de_la_ventanilla(db: AsyncSession) -> list[dict]:
    """Lo que los turnos en curso tienen sin resolver, del más viejo al más nuevo."""
    filas = (
        await db.execute(
            select(
                PedidoCliente, Turno.habitacion_id, Habitacion.numero, Articulo.descripcion, Articulo.precio_unitario
            )
            .join(Turno, Turno.id == PedidoCliente.turno_id)
            .join(Habitacion, Habitacion.id == Turno.habitacion_id)
            .outerjoin(Articulo, Articulo.id == PedidoCliente.articulo_id)
            .where(PedidoCliente.estado.in_(SIN_RESOLVER), Turno.estado == "En Curso")
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
            "descripcion": descripcion_de(pedido.tipo, descripcion, pedido.minutos, pedido.medio_pago),
            "cantidad": pedido.cantidad,
            "estado": pedido.estado,
            "lote": str(pedido.lote) if pedido.lote else None,
            "medio_pago": pedido.medio_pago,
            "subtotal": float(precio * pedido.cantidad) if pedido.tipo == ARTICULO and precio is not None else None,
            "creado_en": con_zona(pedido.creado_en).isoformat(),
        }
        for pedido, habitacion_id, numero, descripcion, precio in filas
    ]


async def bloquear_sin_resolver(db: AsyncSession, pedido_id: int) -> PedidoCliente:
    pedido = (
        (await db.execute(select(PedidoCliente).where(PedidoCliente.id == pedido_id).with_for_update()))
        .scalars()
        .first()
    )
    if pedido is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El pedido no existe.")
    if pedido.estado not in SIN_RESOLVER:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese pedido ya se atendió.")
    return pedido


def llevar(pedido: PedidoCliente, operador_id: int) -> None:
    """Sale de la ventanilla: el cliente lo ve en camino. Todavía no toca el stock ni la cuenta."""
    if pedido.tipo != ARTICULO:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Solo se lleva lo que se pidió del minibar.")
    if pedido.estado != PENDIENTE:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese pedido ya está en camino.")
    pedido.estado = EN_CAMINO
    pedido.llevado_por_id = operador_id
    pedido.llevado_en = datetime.now(UTC)


def resolver(pedido: PedidoCliente, operador_id: int, atendido: bool) -> None:
    pedido.estado = ATENDIDO if atendido else RECHAZADO
    pedido.atendido_por_id = operador_id
    pedido.atendido_en = datetime.now(UTC)
