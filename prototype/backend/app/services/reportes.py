"""Consultas de la gerencia sobre los arqueos confirmados (RF-09).

Solo trabajan sobre arqueos, que existen únicamente para guardias cerradas: ninguna consulta expone el
total de una guardia abierta (RN-RES-03), ni siquiera a la gerencia.
"""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.pago import Pago
from app.models.turno import Turno
from app.schemas.caja import ArqueoDetalle, ArqueoResultado, MetricaCaja, MetricasCaja, PagoDetalle
from app.services.caja import FALTANTE, SOBRANTE


def limites_del_dia(desde: date | None, hasta: date | None) -> tuple[datetime | None, datetime | None]:
    """Convierte días de la hora local del motel en instantes UTC [desde 00:00, hasta+1 00:00)."""
    zona = ZoneInfo(settings.ZONA_HORARIA)
    inicio = datetime.combine(desde, time.min, zona).astimezone(UTC) if desde else None
    fin = datetime.combine(hasta + timedelta(days=1), time.min, zona).astimezone(UTC) if hasta else None
    return inicio, fin


async def resultado_de_arqueo(db: AsyncSession, arqueo: ArqueoCaja) -> ArqueoResultado:
    guardia = await db.get(Guardia, arqueo.guardia_id)
    operador = await db.get(Operador, arqueo.operador_id)
    supervisado = arqueo.confirmado_por_id is not None and arqueo.confirmado_por_id != arqueo.operador_id
    confirma = await db.get(Operador, arqueo.confirmado_por_id) if supervisado else None
    return ArqueoResultado(
        supervisado=supervisado,
        confirmado_por_nombre=confirma.nombre_visible if confirma else None,
        observacion=arqueo.observacion,
        id=arqueo.id,
        guardia_id=arqueo.guardia_id,
        franja=guardia.franja,
        abierta_en=guardia.abierta_en,
        cerrada_en=guardia.cerrada_en,
        operador_id=arqueo.operador_id,
        operador_nombre=operador.nombre_visible if operador else "—",
        declarado_efectivo=arqueo.declarado_efectivo,
        declarado_posnet=arqueo.declarado_posnet,
        declarado_mercado_pago=arqueo.declarado_mercado_pago,
        total_declarado=arqueo.total_declarado,
        sistema_efectivo=arqueo.sistema_efectivo,
        sistema_posnet=arqueo.sistema_posnet,
        sistema_mercado_pago=arqueo.sistema_mercado_pago,
        total_sistema=arqueo.total_sistema,
        fondo_inicial=guardia.fondo_inicial,
        diferencia=arqueo.diferencia,
        categoria=arqueo.categoria,
        confirmado_en=arqueo.confirmado_en,
    )


async def listar_arqueos(
    db: AsyncSession, desde: date | None, hasta: date | None, operador_id: int | None, limite: int = 200
) -> list[ArqueoCaja]:
    inicio, fin = limites_del_dia(desde, hasta)
    consulta = select(ArqueoCaja).order_by(ArqueoCaja.confirmado_en.desc()).limit(limite)
    if inicio:
        consulta = consulta.where(ArqueoCaja.confirmado_en >= inicio)
    if fin:
        consulta = consulta.where(ArqueoCaja.confirmado_en < fin)
    if operador_id:
        consulta = consulta.where(ArqueoCaja.operador_id == operador_id)
    return list((await db.execute(consulta)).scalars().all())


async def detalle_de_arqueo(db: AsyncSession, arqueo: ArqueoCaja) -> ArqueoDetalle:
    filas = (
        await db.execute(
            select(Pago, Habitacion.numero)
            .join(Turno, Turno.id == Pago.turno_id)
            .join(Habitacion, Habitacion.id == Turno.habitacion_id)
            .where(Pago.guardia_id == arqueo.guardia_id)
            .order_by(Pago.created_at)
        )
    ).all()
    pagos = [
        PagoDetalle(
            registrado_en=pago.created_at,
            habitacion_numero=numero,
            medio_pago=pago.medio_pago,
            monto=pago.monto,
            comprobante_referencia=pago.comprobante_referencia,
        )
        for pago, numero in filas
    ]
    resumen = await resultado_de_arqueo(db, arqueo)
    return ArqueoDetalle(**resumen.model_dump(), pagos=pagos)


def _metrica(arqueos: list[ArqueoCaja], operador_id: int | None = None, nombre: str | None = None) -> MetricaCaja:
    faltantes = [a for a in arqueos if a.categoria == FALTANTE]
    sobrantes = [a for a in arqueos if a.categoria == SOBRANTE]
    cantidad = len(arqueos)
    return MetricaCaja(
        operador_id=operador_id,
        operador_nombre=nombre,
        arqueos=cantidad,
        correctos=cantidad - len(faltantes) - len(sobrantes),
        faltantes=len(faltantes),
        sobrantes=len(sobrantes),
        total_faltante=float(-sum((a.diferencia for a in faltantes), 0)),
        total_sobrante=float(sum((a.diferencia for a in sobrantes), 0)),
        tdc=round((len(faltantes) + len(sobrantes)) / cantidad, 4) if cantidad else 0.0,
    )


async def metricas(db: AsyncSession, desde: date | None, hasta: date | None) -> MetricasCaja:
    arqueos = await listar_arqueos(db, desde, hasta, None, limite=100_000)
    nombres = {o.id: o.nombre_visible for o in (await db.execute(select(Operador))).scalars().all()}
    por_operador: dict[int, list[ArqueoCaja]] = {}
    for arqueo in arqueos:
        por_operador.setdefault(arqueo.operador_id, []).append(arqueo)
    return MetricasCaja(
        desde=desde,
        hasta=hasta,
        general=_metrica(arqueos),
        por_operador=[
            _metrica(lista, operador_id, nombres.get(operador_id))
            for operador_id, lista in sorted(por_operador.items(), key=lambda par: nombres.get(par[0], ""))
        ],
    )
