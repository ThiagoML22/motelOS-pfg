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
from app.models.categoria import CategoriaHabitacion
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.schemas.caja import (
    ArqueoDetalle,
    ArqueoResultado,
    MetricaCaja,
    MetricasCaja,
    PagoDetalle,
    ResumenCategoria,
    ResumenMes,
)
from app.services.caja import FALTANTE, SOBRANTE
from app.services.liquidacion import con_zona


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


async def por_categoria(db: AsyncSession, desde: date | None, hasta: date | None) -> list[ResumenCategoria]:
    """Turnos finalizados en el período agrupados por la categoría de su tarifa (la que tenía al abrirse), con sus
    ingresos, y la ocupación actual de cada categoría.

    RN-RES-03: solo cuenta los turnos cobrados en guardias ya arqueadas. Un turno cobrado en la guardia abierta queda
    afuera hasta el cierre ciego: si no, la suma de ingresos revelaría el total de esa caja antes del recuento.
    """
    inicio, fin = limites_del_dia(desde, hasta)
    cobrado_en_guardia_abierta = (
        select(Pago.id)
        .join(Guardia, Guardia.id == Pago.guardia_id)
        .where(Pago.turno_id == Turno.id, Guardia.estado == "Abierta")
        .exists()
    )
    consulta = (
        select(Tarifa.categoria_id, Turno.hora_inicio, Turno.hora_fin, Turno.total_general, Turno.total_consumos)
        .join(Tarifa, Tarifa.id == Turno.tarifa_id)
        .where(Turno.estado == "FINALIZADO", ~cobrado_en_guardia_abierta)
    )
    if inicio:
        consulta = consulta.where(Turno.hora_fin >= inicio)
    if fin:
        consulta = consulta.where(Turno.hora_fin < fin)
    acumulado: dict[int, dict] = {}
    for categoria_id, hora_inicio, hora_fin, total, consumos in (await db.execute(consulta)).all():
        datos = acumulado.setdefault(categoria_id, {"turnos": 0, "ingresos": 0.0, "consumos": 0.0, "minutos": 0.0})
        datos["turnos"] += 1
        datos["ingresos"] += float(total)
        datos["consumos"] += float(consumos)
        if hora_fin:
            datos["minutos"] += (con_zona(hora_fin) - con_zona(hora_inicio)).total_seconds() / 60
    habitaciones = (
        await db.execute(select(Habitacion.categoria_id, Habitacion.estado).where(Habitacion.activa.is_(True)))
    ).all()
    categorias = (
        (await db.execute(select(CategoriaHabitacion).order_by(CategoriaHabitacion.orden, CategoriaHabitacion.id)))
        .scalars()
        .all()
    )
    resumen = []
    for c in categorias:
        datos = acumulado.get(c.id, {"turnos": 0, "ingresos": 0.0, "consumos": 0.0, "minutos": 0.0})
        propias = [estado for categoria_id, estado in habitaciones if categoria_id == c.id]
        if not c.activa and not datos["turnos"] and not propias:
            continue
        turnos = datos["turnos"]
        resumen.append(
            ResumenCategoria(
                categoria_id=c.id,
                nombre=c.nombre,
                color=c.color,
                turnos=turnos,
                ingresos=round(datos["ingresos"], 2),
                consumos=round(datos["consumos"], 2),
                minutos_promedio=round(datos["minutos"] / turnos) if turnos else 0,
                ticket_promedio=round(datos["ingresos"] / turnos, 2) if turnos else 0.0,
                habitaciones=len(propias),
                ocupadas=sum(1 for estado in propias if estado == "Ocupada"),
            )
        )
    return resumen


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


async def resumen_por_mes(db: AsyncSession, operador_id: int | None = None) -> list[ResumenMes]:
    """Arqueos agrupados por mes, del más reciente al más antiguo. El mes es el del día (hora local) en que se abrió
    la guardia: la de la noche del 31 cuenta en ese mes aunque se arquee el 1.º a la mañana."""
    zona = ZoneInfo(settings.ZONA_HORARIA)
    consulta = select(ArqueoCaja, Guardia.abierta_en).join(Guardia, Guardia.id == ArqueoCaja.guardia_id)
    if operador_id:
        consulta = consulta.where(ArqueoCaja.operador_id == operador_id)
    grupos: dict[tuple[int, int], list[ArqueoCaja]] = {}
    for arqueo, abierta_en in (await db.execute(consulta)).all():
        local = con_zona(abierta_en).astimezone(zona)
        grupos.setdefault((local.year, local.month), []).append(arqueo)
    resultado = []
    for (anio, mes), lista in sorted(grupos.items(), reverse=True):
        primero = date(anio, mes, 1)
        siguiente = date(anio + mes // 12, mes % 12 + 1, 1)
        resultado.append(
            ResumenMes(
                **_metrica(lista).model_dump(),
                mes=f"{anio}-{mes:02d}",
                desde=primero,
                hasta=siguiente - timedelta(days=1),
            )
        )
    return resultado


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
