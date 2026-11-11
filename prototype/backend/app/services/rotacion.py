"""Rotación de las habitaciones: el historial de sus estados (migración 011) y lo que se calcula con él.

- Cada cambio de estado pasa por cambiar_estado, que lo deja en el historial en la misma transacción.
- proxima_libre estima cuándo queda disponible cada habitación, con la duración real de las estadías de su categoría y
  el tiempo real de limpieza: dado lo que ya lleva un turno, cuánto les faltaba a los que duraron más que eso.
- linea_de_tiempo arma los tramos de 24 horas de cada habitación. No lleva patentes ni importes.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.categoria import CategoriaHabitacion
from app.models.evento_habitacion import COBRO, EventoHabitacion
from app.models.habitacion import Habitacion
from app.models.operacion import TrasladoTurno
from app.models.operador import Operador
from app.models.pedido_cliente import RECHAZADO, SALIDA, TIEMPO, PedidoCliente
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services.liquidacion import con_zona

LIBRE, OCUPADA, LIMPIEZA, MANTENIMIENTO = "Libre", "Ocupada", "En Limpieza", "Mantenimiento"
# Hasta que haya limpiezas medidas se asume este tiempo.
LIMPIEZA_POR_DEFECTO_MIN = 25
# Días de estadías cerradas que se miran, y cuántas hacen falta para confiar en la estimación de un turno.
DIAS_DE_ESTADIAS = 60
DIAS_DE_LIMPIEZAS = 30
MINIMO_MUESTRAS = 8
# Lo que tarda en irse quien pidió la cuenta: (temprano, típico, tarde), en minutos.
SALIDA_AVISADA_MIN = (3.0, 8.0, 15.0)


async def cambiar_estado(
    db: AsyncSession, habitacion: Habitacion, nuevo: str, operador: Operador, origen: str, turno_id=None
) -> None:
    """Cambia el estado y agrega el evento; los guarda el commit de quien llama."""
    anterior = habitacion.estado
    if anterior == nuevo:
        return
    habitacion.estado = nuevo
    db.add(
        EventoHabitacion(
            habitacion_id=habitacion.id,
            estado_anterior=anterior,
            estado_nuevo=nuevo,
            origen=origen,
            turno_id=turno_id,
            operador_id=operador.id,
        )
    )


# --- Limpiezas -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Tramo:
    """Un período en un estado, armado con dos eventos seguidos de la misma habitación."""

    habitacion_id: int
    inicio: datetime
    fin: datetime | None
    origen: str
    operador_id: int

    @property
    def minutos(self) -> float | None:
        return (self.fin - self.inicio).total_seconds() / 60 if self.fin else None

    @property
    def tras_un_turno(self) -> bool:
        return self.origen == COBRO


def tramos_en_estado(eventos: list[EventoHabitacion], estado: str) -> list[Tramo]:
    """Los períodos de `estado`, de eventos ordenados por habitación y hora. El último puede seguir abierto."""
    tramos: list[Tramo] = []
    abierto: EventoHabitacion | None = None
    for evento in eventos:
        if abierto is not None and evento.habitacion_id != abierto.habitacion_id:
            tramos.append(_tramo(abierto, None))
            abierto = None
        if abierto is not None and evento.estado_anterior == estado:
            tramos.append(_tramo(abierto, evento.creado_en))
            abierto = None
        if evento.estado_nuevo == estado:
            abierto = evento
    if abierto is not None:
        tramos.append(_tramo(abierto, None))
    return tramos


def _tramo(evento: EventoHabitacion, fin: datetime | None) -> Tramo:
    return Tramo(
        evento.habitacion_id,
        con_zona(evento.creado_en),
        con_zona(fin) if fin else None,
        evento.origen,
        evento.operador_id,
    )


async def eventos_de(db: AsyncSession, estado: str, desde: datetime) -> list[EventoHabitacion]:
    consulta = (
        select(EventoHabitacion)
        .where(
            EventoHabitacion.creado_en >= desde,
            or_(EventoHabitacion.estado_nuevo == estado, EventoHabitacion.estado_anterior == estado),
        )
        .order_by(EventoHabitacion.habitacion_id, EventoHabitacion.creado_en, EventoHabitacion.id)
    )
    return list((await db.execute(consulta)).scalars())


def reloj() -> datetime:
    """Hora del servidor de la aplicación. Las pruebas la adelantan: los eventos toman siempre la hora de la base
    (trigger de la migración 011), así que no se puede fabricar una limpieza que empezó hace 31 minutos."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class EstadoLimpieza:
    """Cuánto lleva En Limpieza una habitación y si ya demora (RF-12)."""

    desde: datetime
    minutos: int
    demora: bool


async def limpiezas_en_curso(
    db: AsyncSession, habitaciones: list[Habitacion], ahora: datetime | None = None
) -> dict[int, EstadoLimpieza]:
    """Para cada habitación que está En Limpieza: desde cuándo (su último paso a ese estado en el historial) y los
    minutos enteros que lleva, con el reloj del servidor. Demora si supera DEMORA_LIMPIEZA_MIN; con ese valor exacto,
    todavía no. Una habitación sin ese paso en el historial (datos anteriores a la migración 011) no se marca."""
    ids = [h.id for h in habitaciones if h.estado == LIMPIEZA]
    if not ids:
        return {}
    ahora = ahora or reloj()
    consulta = (
        select(EventoHabitacion.habitacion_id, func.max(EventoHabitacion.creado_en))
        .where(EventoHabitacion.habitacion_id.in_(ids), EventoHabitacion.estado_nuevo == LIMPIEZA)
        .group_by(EventoHabitacion.habitacion_id)
    )
    estados = {}
    for habitacion_id, desde in (await db.execute(consulta)).all():
        desde = con_zona(desde)
        minutos = int((ahora - desde).total_seconds() // 60)
        estados[habitacion_id] = EstadoLimpieza(desde, minutos, minutos > settings.DEMORA_LIMPIEZA_MIN)
    return estados


async def limpieza_tipica(db: AsyncSession, ahora: datetime | None = None) -> float:
    """Minutos de una limpieza típica tras un turno (la mediana de los últimos 30 días)."""
    ahora = ahora or datetime.now(UTC)
    tramos = tramos_en_estado(await eventos_de(db, LIMPIEZA, ahora - timedelta(days=DIAS_DE_LIMPIEZAS)), LIMPIEZA)
    medidas = [t.minutos for t in tramos if t.tras_un_turno and t.minutos is not None]
    return median(medidas) if medidas else LIMPIEZA_POR_DEFECTO_MIN


# --- Próxima libre ---------------------------------------------------------------------------------------------------


def _percentil(ordenados: list[float], parte: float) -> float:
    return ordenados[min(int(len(ordenados) * parte), len(ordenados) - 1)]


def lo_que_avisa_el_cliente(
    pedido: PedidoCliente, inicio: datetime, ahora: datetime, base: float
) -> tuple[float, float, float] | None:
    """Minutos que le faltan a un turno según lo que avisó el cliente: es mejor dato que cualquier estadística.

    Quien pidió la cuenta se está yendo. Quien avisó que se queda más, se queda hasta el fin de su estadía base (o desde
    que avisó, si ya la había pasado) más esos minutos.
    """
    if pedido.tipo == SALIDA:
        return SALIDA_AVISADA_MIN
    if pedido.tipo != TIEMPO or not pedido.minutos:
        return None
    avisado = (con_zona(pedido.creado_en) - inicio).total_seconds() / 60
    lleva = (ahora - inicio).total_seconds() / 60
    falta = max(max(base, avisado) + pedido.minutos - lleva, 5.0)
    return falta * 0.8, falta, falta * 1.25


def estimar_restante(duraciones: list[float], transcurrido: float, base: float) -> tuple[float, float, float]:
    """Minutos que le faltarían a un turno que ya lleva `transcurrido`: (temprano, típico, tarde).

    Mira solo las estadías que duraron más que eso: las más cortas ya no dicen nada de este turno. Si hay pocas (un
    turno más largo de lo habitual), se usa lo que falta para la estadía base, con un margen.
    """
    faltan = sorted(d - transcurrido for d in duraciones if d > transcurrido)
    if len(faltan) < MINIMO_MUESTRAS:
        tipico = max(base - transcurrido, 15.0)
        return tipico * 0.7, tipico, tipico * 1.4
    return _percentil(faltan, 0.25), _percentil(faltan, 0.5), _percentil(faltan, 0.75)


async def proxima_libre(db: AsyncSession, ahora: datetime | None = None) -> dict:
    """Cuándo quedaría disponible cada habitación que hoy no lo está, de la más próxima a la más lejana."""
    ahora = con_zona(ahora) if ahora else datetime.now(UTC)
    habitaciones = list(
        (await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))).scalars()
    )
    categorias = {c.id: c for c in (await db.execute(select(CategoriaHabitacion))).scalars()}
    en_curso = {
        turno.habitacion_id: (turno, base)
        for turno, base in (
            await db.execute(
                select(Turno, Tarifa.estadia_base_min)
                .join(Tarifa, Tarifa.id == Turno.tarifa_id)
                .where(Turno.estado == "En Curso")
            )
        ).all()
    }
    duraciones: dict[int, list[float]] = defaultdict(list)
    filas = await db.execute(
        select(Tarifa.categoria_id, Turno.hora_inicio, Turno.hora_fin)
        .join(Tarifa, Tarifa.id == Turno.tarifa_id)
        .where(
            Turno.estado == "FINALIZADO",
            Turno.hora_fin.is_not(None),
            Turno.hora_fin >= ahora - timedelta(days=DIAS_DE_ESTADIAS),
        )
    )
    for categoria_id, inicio, fin in filas.all():
        duraciones[categoria_id].append((con_zona(fin) - con_zona(inicio)).total_seconds() / 60)
    limpieza = await limpieza_tipica(db, ahora)
    inicio_limpieza = dict(
        (
            await db.execute(
                select(EventoHabitacion.habitacion_id, func.max(EventoHabitacion.creado_en))
                .where(EventoHabitacion.estado_nuevo == LIMPIEZA)
                .group_by(EventoHabitacion.habitacion_id)
            )
        ).all()
    )

    # Lo último que avisó cada cliente que sigue en su habitación (un aviso rechazado no cuenta).
    avisos: dict = {}
    if en_curso:
        consulta = (
            select(PedidoCliente)
            .where(
                PedidoCliente.turno_id.in_([turno.id for turno, _ in en_curso.values()]),
                PedidoCliente.tipo.in_((SALIDA, TIEMPO)),
                PedidoCliente.estado != RECHAZADO,
            )
            .order_by(PedidoCliente.id)
        )
        avisos = {p.turno_id: p for p in (await db.execute(consulta)).scalars()}

    proximas = []
    for h in habitaciones:
        aviso = None
        if h.estado == OCUPADA and h.id in en_curso:
            turno, base = en_curso[h.id]
            inicio = con_zona(turno.hora_inicio)
            lleva = (ahora - inicio).total_seconds() / 60
            aviso = avisos.get(turno.id)
            avisado = lo_que_avisa_el_cliente(aviso, inicio, ahora, float(base or 120)) if aviso else None
            temprano, tipico, tarde = avisado or estimar_restante(duraciones[h.categoria_id], lleva, float(base or 120))
            temprano, tipico, tarde = temprano + limpieza, tipico + limpieza, tarde + limpieza
        elif h.estado == LIMPIEZA:
            desde = inicio_limpieza.get(h.id)
            lleva = (ahora - con_zona(desde)).total_seconds() / 60 if desde else 0.0
            tipico = max(limpieza - lleva, 2.0)
            temprano, tarde = max(tipico * 0.6, 1.0), tipico * 1.5
        else:
            continue
        categoria = categorias.get(h.categoria_id)
        proximas.append(
            {
                "habitacion_id": h.id,
                "numero": h.numero,
                "estado": h.estado,
                "categoria_id": h.categoria_id,
                "categoria": categoria.nombre if categoria else "Sin categoría",
                "color": categoria.color if categoria else "#244473",
                "minutos": round(tipico),
                "minimo": round(temprano),
                "maximo": round(tarde),
                # Si la estimación sale de lo que avisó el cliente con su QR.
                "aviso": aviso.tipo if aviso else None,
            }
        )
    proximas.sort(key=lambda p: (p["minutos"], p["numero"]))
    por_categoria = []
    for categoria in sorted(categorias.values(), key=lambda c: c.orden):
        propias = [h for h in habitaciones if h.categoria_id == categoria.id]
        if not propias:
            continue
        primera = next((p for p in proximas if p["categoria_id"] == categoria.id), None)
        por_categoria.append(
            {
                "categoria_id": categoria.id,
                "categoria": categoria.nombre,
                "color": categoria.color,
                "disponibles": sum(1 for h in propias if h.estado == LIBRE),
                "habitaciones": len(propias),
                "proxima_min": primera["minutos"] if primera else None,
            }
        )
    return {
        "disponibles": sum(1 for h in habitaciones if h.estado == LIBRE),
        "habitaciones": len(habitaciones),
        "limpieza_min": round(limpieza),
        "proximas": proximas,
        "categorias": por_categoria,
    }


# --- Línea de tiempo -------------------------------------------------------------------------------------------------


async def linea_de_tiempo(db: AsyncSession, dia: date | None = None, ahora: datetime | None = None) -> dict:
    """Los tramos de cada habitación en 24 horas: las últimas, o las del día local indicado.

    Lo ocupado sale de los turnos (también los anteriores al historial); la limpieza y el mantenimiento, de los eventos.
    """
    zona = ZoneInfo(settings.ZONA_HORARIA)
    ahora = con_zona(ahora) if ahora else datetime.now(UTC)
    if dia is None:
        desde, hasta = ahora - timedelta(hours=24), ahora
    else:
        desde = datetime.combine(dia, time.min, zona).astimezone(UTC)
        hasta = desde + timedelta(hours=24)
    limite = min(hasta, ahora)

    habitaciones = list(
        (await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))).scalars()
    )
    categorias = {c.id: c for c in (await db.execute(select(CategoriaHabitacion))).scalars()}
    tramos: dict[int, list[dict]] = defaultdict(list)

    def agregar(habitacion_id: int, tipo: str, inicio: datetime, fin: datetime | None, sigue: bool = False) -> None:
        en_curso = fin is None
        recortado_inicio, recortado_fin = max(inicio, desde), min(fin or limite, limite)
        if recortado_fin > recortado_inicio:
            tramos[habitacion_id].append(
                {
                    "tipo": tipo,
                    "desde": recortado_inicio.isoformat(),
                    "hasta": recortado_fin.isoformat(),
                    "en_curso": en_curso,
                    "minutos": round(((fin or limite) - inicio).total_seconds() / 60),
                    # El turno siguió en otra habitación: en el resumen cuenta una vez.
                    "sigue": sigue,
                }
            )

    turnos = (
        await db.execute(
            select(Turno.id, Turno.habitacion_id, Turno.hora_inicio, Turno.hora_fin).where(
                Turno.hora_inicio < hasta, or_(Turno.hora_fin.is_(None), Turno.hora_fin > desde)
            )
        )
    ).all()
    # Un turno trasladado ocupó más de una habitación: cada una muestra su parte.
    traslados: dict = defaultdict(list)
    if turnos:
        consulta = await db.execute(
            select(TrasladoTurno)
            .where(TrasladoTurno.turno_id.in_([t[0] for t in turnos]))
            .order_by(TrasladoTurno.creado_en, TrasladoTurno.id)
        )
        for traslado in consulta.scalars():
            traslados[traslado.turno_id].append(traslado)
    for turno_id, habitacion_id, inicio, fin in turnos:
        desde_aca = con_zona(inicio)
        for traslado in traslados[turno_id]:
            agregar(traslado.desde_habitacion_id, "ocupada", desde_aca, con_zona(traslado.creado_en), sigue=True)
            desde_aca = con_zona(traslado.creado_en)
        agregar(habitacion_id, "ocupada", desde_aca, con_zona(fin) if fin else None)

    # Un período que empezó antes de la ventana también cuenta: una limpieza dura minutos, un arreglo, semanas.
    for estado, tipo, margen in ((LIMPIEZA, "limpieza", 2), (MANTENIMIENTO, "mantenimiento", 90)):
        for tramo in tramos_en_estado(await eventos_de(db, estado, desde - timedelta(days=margen)), estado):
            agregar(tramo.habitacion_id, tipo, tramo.inicio, tramo.fin)

    filas = []
    for h in habitaciones:
        categoria = categorias.get(h.categoria_id)
        filas.append(
            {
                "habitacion_id": h.id,
                "numero": h.numero,
                "estado": h.estado,
                "categoria": categoria.nombre if categoria else "Sin categoría",
                "color": categoria.color if categoria else "#244473",
                "tramos": sorted(tramos[h.id], key=lambda t: t["desde"]),
            }
        )

    ocupados = [t for f in filas for t in f["tramos"] if t["tipo"] == "ocupada"]
    limpiezas = [t["minutos"] for f in filas for t in f["tramos"] if t["tipo"] == "limpieza" and not t["en_curso"]]
    minutos_ocupados = sum(
        (datetime.fromisoformat(t["hasta"]) - datetime.fromisoformat(t["desde"])).total_seconds() / 60 for t in ocupados
    )
    disponibles = len(habitaciones) * (limite - desde).total_seconds() / 60
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "ahora": ahora.isoformat(),
        "habitaciones": filas,
        "resumen": {
            "turnos": sum(1 for t in ocupados if not t["sigue"]),
            "ocupacion": round(min(minutos_ocupados / disponibles, 1.0), 4) if disponibles > 0 else None,
            "limpieza_min": round(median(limpiezas)) if limpiezas else None,
            "turnos_por_habitacion": round(len(ocupados) / len(habitaciones), 1) if habitaciones else 0.0,
        },
    }
