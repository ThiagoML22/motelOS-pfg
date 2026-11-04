"""Inteligencia local para la gerencia: pronóstico de demanda, alertas, sugerencias de tarifa, reposición y resumen.

Todo se calcula en el servidor del motel con estadística simple y explicable (promedios estacionales ponderados,
una prueba binomial, medianas y una simulación de la tarifa sobre las estadías reales): no hay modelos externos ni
servicios en internet, y cada resultado dice cómo se obtuvo.

RN-RES-03: trabaja solo con lo cerrado. El corte es la apertura de la guardia en curso (o el momento actual, si no hay
ninguna): los turnos que terminaron después todavía no pasaron por un arqueo y no se miran, ni en cantidades ni en
importes. La ocupación «ahora» sale del estado de las habitaciones, que la grilla ya muestra.
"""

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from statistics import mean, median, pstdev
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.arqueo import ArqueoCaja
from app.models.articulo import Articulo
from app.models.calificacion import PROBLEMAS, Calificacion
from app.models.categoria import CategoriaHabitacion
from app.models.cliente_perdido import MOTIVOS, SIN_LUGAR, ClientePerdido
from app.models.consumo import Consumo
from app.models.franja_tarifa import FranjaTarifa
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services import franjas
from app.services.billing_service import ParametrosTarifa, calcular_sobreturno
from app.services.caja import FALTANTE, SOBRANTE, guardia_abierta
from app.services.liquidacion import con_zona
from app.services.rotacion import LIMPIEZA, Tramo, eventos_de, tramos_en_estado

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
HISTORIA_DIAS = 120
SEMANAS_ESTACIONALES = 8
# Cada semana hacia atrás pesa 0,75 de la siguiente: lo reciente manda, sin olvidar el patrón.
PESO_SEMANA = 0.75
# Supuestos de las sugerencias de tarifa (elasticidad precio-demanda): se muestran junto a cada sugerencia.
ELASTICIDAD_PICO = -0.5
ELASTICIDAD_VALLE = -1.6


@dataclass(frozen=True)
class ReglaSugerida:
    """La tarifa especial que se propone crear: cobrar distinto solo cuando la demanda lo justifica."""

    nombre: str
    dias: int
    desde: time
    hasta: time


REGLA_PICO = ReglaSugerida("Noche de fin de semana", franjas.mascara(4, 5), time(20), time(6))
REGLA_VALLE = ReglaSugerida("De día en la semana", franjas.mascara(0, 1, 2, 3), time(8), time(18))
# El viernes a las 23: si una tarifa especial rige ahí, el pico ya tiene la suya.
MINUTO_DEL_PICO = 4 * franjas.MINUTOS_DIA + 23 * 60


# --- Formato ------------------------------------------------------------------------------------------------------


def pesos(valor: float) -> str:
    entero = round(valor)
    texto = f"{abs(entero):,}".replace(",", ".")
    return f"-${texto}" if entero < 0 else f"${texto}"


def porcentaje(valor: float, decimales: int = 0) -> str:
    return f"{valor * 100:.{decimales}f}%".replace(".", ",")


def variacion(actual: float, anterior: float) -> float | None:
    return None if not anterior else actual / anterior - 1


def con_signo(valor: float | None) -> str:
    if valor is None:
        return "—"
    if round(abs(valor) * 100) == 0:
        return "0%"
    return f"{'+' if valor >= 0 else '−'}{abs(valor) * 100:.0f}%"


def fecha_corta(dia: date) -> str:
    return f"{DIAS[dia.weekday()]} {dia.day}/{dia.month}"


def hora_texto(hora: int) -> str:
    return f"{hora} h"


def minutos_texto(minutos: float) -> str:
    horas, resto = divmod(round(minutos), 60)
    if not horas:
        return f"{resto} min"
    return f"{horas} h {resto:02d} min" if resto else f"{horas} h"


# --- Datos ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnoCerrado:
    inicio: datetime
    fin: datetime
    habitacion_id: int
    categoria_id: int
    total: float
    consumos: float
    sobreturno: float
    tarifa_id: int
    cobrado_por: int | None

    @property
    def minutos(self) -> float:
        return (self.fin - self.inicio).total_seconds() / 60


@dataclass(frozen=True)
class ArqueoCerrado:
    momento: datetime
    operador_id: int
    diferencia: float
    categoria: str
    franja: str


@dataclass(frozen=True)
class Venta:
    momento: datetime
    articulo_id: int
    cantidad: int
    subtotal: float


@dataclass(frozen=True)
class Cobro:
    momento: datetime
    medio: str
    monto: float


@dataclass(frozen=True)
class Perdido:
    momento: datetime
    motivo: str
    categoria_id: int | None
    operador_id: int


@dataclass(frozen=True)
class Opinion:
    momento: datetime
    habitacion_id: int
    puntaje: int
    problemas: int


@dataclass
class Contexto:
    zona: ZoneInfo
    ahora: datetime
    corte: datetime
    hay_guardia_abierta: bool
    turnos: list[TurnoCerrado]
    arqueos: list[ArqueoCerrado]
    ventas: list[Venta]
    cobros: list[Cobro]
    habitaciones: list[Habitacion]
    categorias: dict[int, CategoriaHabitacion]
    tarifas: dict[int, Tarifa]
    tarifas_por_id: dict[int, Tarifa]
    articulos: list[Articulo]
    nombres: dict[int, str]
    perdidos: list[Perdido] = field(default_factory=list)
    limpiezas: list[Tramo] = field(default_factory=list)
    # Todas, también las dadas de baja: lo cobrado con ellas sigue en el historial.
    franjas: list[FranjaTarifa] = field(default_factory=list)
    opiniones: list[Opinion] = field(default_factory=list)

    def franjas_de(self, categoria_id: int) -> list[FranjaTarifa]:
        return [f for f in self.franjas if f.activa and f.categoria_id == categoria_id]

    def tarifa_de_franja(self, franja_id: int) -> Tarifa | None:
        return next((t for t in self.tarifas_por_id.values() if t.franja_id == franja_id and t.vigente), None)

    def inicio_dia(self, dia: date) -> datetime:
        return datetime.combine(dia, time.min, self.zona)

    @property
    def ultimo_dia_completo(self) -> date:
        return self.corte.date() - timedelta(days=1)

    def cobrados_entre(self, desde: datetime, hasta: datetime) -> list[TurnoCerrado]:
        return [t for t in self.turnos if desde <= t.fin < hasta]

    def numero(self, habitacion_id: int) -> int | None:
        return next((h.numero for h in self.habitaciones if h.id == habitacion_id), None)

    def nombre_categoria(self, categoria_id: int) -> str:
        categoria = self.categorias.get(categoria_id)
        return categoria.nombre if categoria else "Sin categoría"


async def contexto(db: AsyncSession, ahora: datetime | None = None) -> Contexto:
    zona = ZoneInfo(settings.ZONA_HORARIA)
    ahora_utc = con_zona(ahora) if ahora else datetime.now(UTC)
    abierta = await guardia_abierta(db)
    corte_utc = con_zona(abierta.abierta_en) if abierta else ahora_utc
    desde_utc = corte_utc - timedelta(days=HISTORIA_DIAS)

    def local(valor: datetime) -> datetime:
        return con_zona(valor).astimezone(zona)

    filas = (
        await db.execute(
            select(
                Turno.hora_inicio,
                Turno.hora_fin,
                Turno.habitacion_id,
                Tarifa.categoria_id,
                Turno.total_general,
                Turno.total_consumos,
                Turno.total_sobreturno,
                Turno.tarifa_id,
                Turno.operador_cierre_id,
            )
            .join(Tarifa, Tarifa.id == Turno.tarifa_id)
            .where(
                Turno.estado == "FINALIZADO",
                Turno.hora_fin.is_not(None),
                Turno.hora_fin < corte_utc,
                Turno.hora_fin >= desde_utc,
            )
        )
    ).all()
    turnos = sorted(
        (
            TurnoCerrado(local(i), local(f), h, c, float(t), float(cons), float(s), tid, op)
            for i, f, h, c, t, cons, s, tid, op in filas
        ),
        key=lambda t: t.inicio,
    )
    arqueos = [
        ArqueoCerrado(local(m), op, float(dif), cat, franja)
        for m, op, dif, cat, franja in (
            await db.execute(
                select(
                    ArqueoCaja.confirmado_en,
                    ArqueoCaja.operador_id,
                    ArqueoCaja.diferencia,
                    ArqueoCaja.categoria,
                    Guardia.franja,
                )
                .join(Guardia, Guardia.id == ArqueoCaja.guardia_id)
                .where(ArqueoCaja.confirmado_en >= desde_utc)
            )
        ).all()
    ]
    ventas = [
        Venta(local(m), a, c, float(s))
        for m, a, c, s in (
            await db.execute(
                select(Consumo.created_at, Consumo.articulo_id, Consumo.cantidad, Consumo.subtotal).where(
                    Consumo.created_at < corte_utc, Consumo.created_at >= desde_utc
                )
            )
        ).all()
    ]
    cobros = [
        Cobro(local(m), medio, float(monto))
        for m, medio, monto in (
            await db.execute(
                select(Pago.created_at, Pago.medio_pago, Pago.monto).where(
                    Pago.created_at < corte_utc, Pago.created_at >= desde_utc
                )
            )
        ).all()
    ]
    habitaciones = list(
        (await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))).scalars()
    )
    categorias = {
        c.id: c for c in (await db.execute(select(CategoriaHabitacion).order_by(CategoriaHabitacion.orden))).scalars()
    }
    todas_las_tarifas = list((await db.execute(select(Tarifa))).scalars())
    todas_las_franjas = list((await db.execute(select(FranjaTarifa).order_by(FranjaTarifa.id))).scalars())
    articulos = list(
        (await db.execute(select(Articulo).where(Articulo.activo.is_(True)).order_by(Articulo.descripcion))).scalars()
    )
    nombres = {i: n for i, n in (await db.execute(select(Operador.id, Operador.nombre_visible))).all()}
    perdidos = [
        Perdido(local(m), motivo, categoria_id, operador_id)
        for m, motivo, categoria_id, operador_id in (
            await db.execute(
                select(
                    ClientePerdido.creado_en,
                    ClientePerdido.motivo,
                    ClientePerdido.categoria_id,
                    ClientePerdido.operador_id,
                ).where(ClientePerdido.creado_en >= desde_utc, ClientePerdido.creado_en < corte_utc)
            )
        ).all()
    ]
    # Las opiniones no dicen nada de la caja: no esperan al arqueo.
    opiniones = [
        Opinion(local(m), h, p, problemas)
        for m, h, p, problemas in (
            await db.execute(
                select(
                    Calificacion.creado_en, Calificacion.habitacion_id, Calificacion.puntaje, Calificacion.problemas
                ).where(Calificacion.creado_en >= desde_utc)
            )
        ).all()
    ]
    limpiezas = [
        t
        for t in tramos_en_estado(await eventos_de(db, LIMPIEZA, desde_utc), LIMPIEZA)
        if t.fin is not None and t.fin < corte_utc
    ]
    return Contexto(
        zona=zona,
        ahora=local(ahora_utc),
        corte=local(corte_utc),
        hay_guardia_abierta=abierta is not None,
        turnos=turnos,
        arqueos=sorted(arqueos, key=lambda a: a.momento),
        ventas=ventas,
        cobros=cobros,
        habitaciones=habitaciones,
        categorias=categorias,
        tarifas={t.categoria_id: t for t in todas_las_tarifas if t.vigente and t.franja_id is None},
        tarifas_por_id={t.id: t for t in todas_las_tarifas},
        articulos=articulos,
        nombres=nombres,
        perdidos=perdidos,
        limpiezas=limpiezas,
        franjas=todas_las_franjas,
        opiniones=opiniones,
    )


# --- Indicadores y series -------------------------------------------------------------------------------------------


def ocupacion(turnos: list[TurnoCerrado], ventanas: list[tuple[datetime, datetime]], habitaciones: int) -> float | None:
    """Fracción de los minutos-habitación de las ventanas que estuvieron ocupados."""
    disponible = sum((b - a).total_seconds() for a, b in ventanas) * habitaciones
    if not disponible:
        return None
    usado = 0.0
    for t in turnos:
        for a, b in ventanas:
            if t.fin > a and t.inicio < b:
                usado += (min(t.fin, b) - max(t.inicio, a)).total_seconds()
    return min(usado / disponible, 1.0)


def indicadores(ctx: Contexto) -> dict:
    fin = ctx.inicio_dia(ctx.corte.date())
    semana = ctx.cobrados_entre(fin - timedelta(days=7), fin)
    anterior = ctx.cobrados_entre(fin - timedelta(days=14), fin - timedelta(days=7))
    ingresos, ingresos_ant = sum(t.total for t in semana), sum(t.total for t in anterior)
    arqueos = [a for a in ctx.arqueos if a.momento >= ctx.corte - timedelta(days=30)]
    con_diferencia = sum(1 for a in arqueos if a.categoria in (FALTANTE, SOBRANTE))
    return {
        "ocupadas_ahora": sum(1 for h in ctx.habitaciones if h.estado == "Ocupada"),
        "habitaciones": len(ctx.habitaciones),
        "turnos_7d": len(semana),
        "turnos_7d_variacion": variacion(len(semana), len(anterior)),
        "ingresos_7d": round(ingresos, 2),
        "ingresos_7d_variacion": variacion(ingresos, ingresos_ant),
        "ticket_7d": round(ingresos / len(semana), 2) if semana else 0.0,
        "ocupacion_7d": ocupacion(
            [t for t in ctx.turnos if t.fin > fin - timedelta(days=7)],
            [(fin - timedelta(days=7), fin)],
            len(ctx.habitaciones),
        ),
        "tdc_30d": con_diferencia / len(arqueos) if arqueos else None,
        "arqueos_30d": len(arqueos),
    }


def serie_diaria(ctx: Contexto, dias: int = 30) -> list[dict]:
    """Turnos cobrados e ingresos por día (días completos anteriores al corte)."""
    ultimo = ctx.ultimo_dia_completo
    primero = ultimo - timedelta(days=dias - 1)
    por_dia = {primero + timedelta(days=i): [0, 0.0] for i in range(dias)}
    for t in ctx.turnos:
        if t.fin.date() in por_dia:
            por_dia[t.fin.date()][0] += 1
            por_dia[t.fin.date()][1] += t.total
    return [
        {"fecha": d.isoformat(), "dia": DIAS_CORTOS[d.weekday()], "turnos": n, "ingresos": round(i, 2)}
        for d, (n, i) in por_dia.items()
    ]


def mapa_demanda(ctx: Contexto, semanas: int = SEMANAS_ESTACIONALES) -> dict:
    """Llegadas promedio por día de la semana y hora (hora local), de las últimas `semanas` semanas."""
    desde = ctx.corte - timedelta(weeks=semanas)
    turnos = [t for t in ctx.turnos if t.inicio >= desde]
    conteo = [[0] * 24 for _ in range(7)]
    for t in turnos:
        conteo[t.inicio.weekday()][t.inicio.hour] += 1
    primero = max(desde.date(), turnos[0].inicio.date()) if turnos else ctx.corte.date()
    dias = Counter((primero + timedelta(days=i)).weekday() for i in range((ctx.corte.date() - primero).days))
    valores = [[round(conteo[d][h] / dias[d], 2) if dias[d] else 0.0 for h in range(24)] for d in range(7)]
    maximo = max((v for fila in valores for v in fila), default=0.0)
    pico_dia, pico_hora = max(((d, h) for d in range(7) for h in range(24)), key=lambda p: valores[p[0]][p[1]])
    por_dia = [round(sum(fila), 1) for fila in valores]
    return {
        "dias": DIAS_CORTOS,
        "valores": valores,
        "maximo": maximo,
        "semanas": round(sum(dias.values()) / 7, 1),
        "pico": {"dia": DIAS[pico_dia], "hora": pico_hora, "llegadas": valores[pico_dia][pico_hora]},
        "dia_mas_fuerte": DIAS[max(range(7), key=lambda d: por_dia[d])],
        "dia_mas_flojo": DIAS[min(range(7), key=lambda d: por_dia[d])],
        "por_dia": por_dia,
    }


# --- Opiniones de los clientes ---------------------------------------------------------------------------------

# Una habitación se compara con las demás recién con esta cantidad de opiniones: con menos, una sola la movería mucho.
MINIMO_OPINIONES = 3


def problemas_de(mascara: int) -> list[str]:
    return [etiqueta for valor, etiqueta in PROBLEMAS.items() if mascara & valor]


def opiniones(ctx: Contexto, dias: int = 30) -> dict:
    """Promedio, lo que más falla y cómo está cada habitación. Solo totales: una opinión suelta con su hora dejaría de
    ser anónima."""
    desde = ctx.ahora - timedelta(days=dias)
    propias = [o for o in ctx.opiniones if o.momento >= desde]
    if not propias:
        return {
            "dias": dias,
            "cantidad": 0,
            "promedio": None,
            "parte": 0.0,
            "puntajes": [],
            "problemas": [],
            "habitaciones": [],
        }
    por_habitacion: dict[int, list[Opinion]] = defaultdict(list)
    problemas: Counter[str] = Counter()
    for o in propias:
        por_habitacion[o.habitacion_id].append(o)
        problemas.update(problemas_de(o.problemas))
    filas = []
    for habitacion_id, lista in por_habitacion.items():
        if len(lista) < MINIMO_OPINIONES:
            continue
        propios: Counter[str] = Counter()
        for o in lista:
            propios.update(problemas_de(o.problemas))
        principal = propios.most_common(1)[0] if propios else None
        filas.append(
            {
                "habitacion_id": habitacion_id,
                "numero": ctx.numero(habitacion_id),
                "promedio": round(mean(o.puntaje for o in lista), 2),
                "cantidad": len(lista),
                "problema": principal[0] if principal else None,
                "problema_veces": principal[1] if principal else 0,
            }
        )
    filas = [f for f in filas if f["numero"] is not None]
    filas.sort(key=lambda f: (f["promedio"], -f["cantidad"]))
    turnos = sum(1 for t in ctx.turnos if t.fin >= desde)
    puntajes = Counter(o.puntaje for o in propias)
    return {
        "dias": dias,
        "cantidad": len(propias),
        "promedio": round(mean(o.puntaje for o in propias), 2),
        "parte": round(min(len(propias) / turnos, 1.0), 4) if turnos else 0.0,
        "puntajes": [{"puntaje": p, "cantidad": puntajes[p]} for p in range(5, 0, -1)],
        "problemas": [{"problema": p, "cantidad": c} for p, c in problemas.most_common()],
        "habitaciones": filas,
    }


# --- Clientes perdidos y rotación -------------------------------------------------------------------------------


def clientes_perdidos(ctx: Contexto, dias: int = 30) -> dict:
    """Los clientes que se fueron sin quedarse: cuántos, por qué, cuándo y cuánto representan.

    El valor es una estimación: cada cliente, al ticket promedio de la categoría que buscaba (o al general).
    """
    desde = ctx.corte - timedelta(days=dias)
    perdidos = [p for p in ctx.perdidos if p.momento >= desde]
    atendidos = [t for t in ctx.turnos if t.inicio >= desde]
    por_hora = [0] * 24
    semana = [0] * 168
    for p in perdidos:
        por_hora[p.momento.hour] += 1
        semana[p.momento.weekday() * 24 + p.momento.hour] += 1
    horas = [{"hora": h, "etiqueta": hora_texto(h), "cantidad": por_hora[h]} for h in range(24)]
    if not perdidos:
        return {
            "dias": dias,
            "total": 0,
            "parte": 0.0,
            "valor_estimado": 0.0,
            "motivos": [],
            "categorias": [],
            "horas": horas,
            "franja": None,
            "esperados_24h": 0.0,
        }
    general = mean(t.total for t in atendidos) if atendidos else 0.0
    tickets: dict[int, list[float]] = defaultdict(list)
    for t in atendidos:
        tickets[t.categoria_id].append(t.total)
    valor = sum(mean(tickets[p.categoria_id]) if p.categoria_id in tickets else general for p in perdidos)
    motivos = Counter(p.motivo for p in perdidos)
    categorias = Counter(p.categoria_id for p in perdidos if p.categoria_id is not None)
    # Las cuatro horas seguidas de la semana con más clientes perdidos.
    suma, inicio = max((sum(semana[(i + j) % 168] for j in range(4)), i) for i in range(168))
    momentos = [ctx.ahora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=i) for i in range(24)]
    por_fecha = Counter((p.momento.date(), p.momento.hour) for p in ctx.perdidos)
    primero = min(p.momento.date() for p in ctx.perdidos)
    return {
        "dias": dias,
        "total": len(perdidos),
        "parte": round(len(perdidos) / (len(perdidos) + len(atendidos)), 4),
        "valor_estimado": round(valor, 2),
        "motivos": [
            {"motivo": m, "etiqueta": MOTIVOS.get(m, m), "cantidad": c, "parte": round(c / len(perdidos), 4)}
            for m, c in motivos.most_common()
        ],
        "categorias": [
            {
                "categoria_id": c,
                "categoria": ctx.nombre_categoria(c),
                "color": ctx.categorias[c].color if c in ctx.categorias else "#244473",
                "cantidad": n,
            }
            for c, n in categorias.most_common()
        ],
        "horas": horas,
        "franja": {
            "dia": DIAS[inicio // 24],
            "desde": inicio % 24,
            "hasta": (inicio + 4) % 24,
            "cantidad": suma,
            "parte": round(suma / len(perdidos), 4),
        },
        "esperados_24h": round(sum(estacional(por_fecha, primero, m.date(), m.hour) or 0.0 for m in momentos), 1),
    }


FRANJAS_DEL_DIA = (("Mañana", 6, 14), ("Tarde", 14, 22), ("Noche", 22, 6))


def _en_franja(hora: int, desde: int, hasta: int) -> bool:
    return desde <= hora < hasta if desde < hasta else hora >= desde or hora < hasta


def rotacion(ctx: Contexto, dias: int = 30) -> dict:
    """Cuánto tardan las limpiezas después de un turno, y las que no vinieron de un turno."""
    desde = ctx.corte - timedelta(days=dias)
    limpiezas = [t for t in ctx.limpiezas if t.inicio >= desde]
    tras_turno = [t for t in limpiezas if t.tras_un_turno]
    minutos = sorted(t.minutos for t in tras_turno)
    por_franja = []
    for nombre, inicio, fin in FRANJAS_DEL_DIA:
        propias = [t.minutos for t in tras_turno if _en_franja(t.inicio.astimezone(ctx.zona).hour, inicio, fin)]
        if propias:
            por_franja.append({"franja": nombre, "mediana": round(median(propias)), "cantidad": len(propias)})
    por_habitacion: dict[int, list[float]] = defaultdict(list)
    for t in tras_turno:
        por_habitacion[t.habitacion_id].append(t.minutos)
    lentas = sorted(
        ((median(v), h, len(v)) for h, v in por_habitacion.items() if len(v) >= 5 and ctx.numero(h) is not None),
        reverse=True,
    )[:3]
    return {
        "dias": dias,
        "cantidad": len(tras_turno),
        "mediana": round(median(minutos)) if minutos else None,
        "p90": round(minutos[int(len(minutos) * 0.9)]) if minutos else None,
        "por_franja": por_franja,
        "mas_lentas": [{"numero": ctx.numero(h), "mediana": round(m), "cantidad": n} for m, h, n in lentas],
        "sin_turno": len(limpiezas) - len(tras_turno),
    }


# --- Pronóstico -----------------------------------------------------------------------------------------------------


def _llegadas(turnos: list[TurnoCerrado]) -> Counter:
    return Counter((t.inicio.date(), t.inicio.hour) for t in turnos)


def estacional(conteo: Counter, inicio_historia: date, dia: date, hora: int) -> float | None:
    """Llegadas esperadas en (día, hora): promedio ponderado de la misma hora del mismo día en semanas anteriores."""
    suma = peso_total = 0.0
    for k in range(1, SEMANAS_ESTACIONALES + 1):
        anterior = dia - timedelta(weeks=k)
        if anterior < inicio_historia:
            break
        peso = PESO_SEMANA ** (k - 1)
        suma += peso * conteo.get((anterior, hora), 0)
        peso_total += peso
    return suma / peso_total if peso_total else None


def _tendencia(ctx: Contexto) -> float:
    recientes = sum(1 for t in ctx.turnos if ctx.corte - timedelta(days=14) <= t.inicio < ctx.corte)
    previos = sum(1 for t in ctx.turnos if ctx.corte - timedelta(days=28) <= t.inicio < ctx.corte - timedelta(days=14))
    if recientes < 20 or previos < 20:
        return 1.0
    return min(max(recientes / previos, 0.85), 1.2) ** 0.5


def _supervivencia(turnos: list[TurnoCerrado]) -> list[float]:
    """S[j]: probabilidad de que una estadía siga a las j horas de haber llegado (S[0] = 0,5: llega en algún momento
    de la hora)."""
    minutos = [t.minutos for t in turnos]
    if not minutos:
        return [0.0] * 14
    return [0.5] + [sum(1 for m in minutos if m > j * 60) / len(minutos) for j in range(1, 14)]


def _franjas(horas: list[int]) -> list[tuple[int, int]]:
    """Agrupa índices consecutivos en tramos [desde, hasta]."""
    tramos: list[tuple[int, int]] = []
    for i in horas:
        if tramos and i == tramos[-1][1] + 1:
            tramos[-1] = (tramos[-1][0], i)
        else:
            tramos.append((i, i))
    return tramos


def precision(ctx: Contexto, dias: int = 7) -> dict | None:
    """Error del método en los últimos `dias` días completos, pronosticando cada uno solo con lo anterior."""
    if not ctx.turnos:
        return None
    conteo = _llegadas(ctx.turnos)
    inicio = ctx.turnos[0].inicio.date()
    errores = []
    for k in range(dias):
        dia = ctx.ultimo_dia_completo - timedelta(days=k)
        if (dia - inicio).days < 14:
            continue
        real = sum(conteo.get((dia, h), 0) for h in range(24))
        estimado = sum(estacional(conteo, inicio, dia, h) or 0 for h in range(24))
        if real:
            errores.append(abs(estimado - real) / real)
    return {"error_medio": round(mean(errores), 4), "dias": len(errores)} if errores else None


def pronostico(ctx: Contexto, horas: int = 24) -> dict:
    """Llegadas y ocupación esperadas hora por hora desde ahora, con los tramos en que cada categoría se llena."""
    conteo = _llegadas(ctx.turnos)
    if not ctx.turnos:
        return {
            "horas": [],
            "total": 0,
            "minimo": 0,
            "maximo": 0,
            "saturacion": [],
            "precision": None,
            "tendencia": 1.0,
            "pico": None,
        }
    inicio_historia = ctx.turnos[0].inicio.date()
    tendencia = _tendencia(ctx)
    base = ctx.ahora.replace(minute=0, second=0, microsecond=0)
    momentos = [base + timedelta(hours=i) for i in range(horas)]
    llegadas = [(estacional(conteo, inicio_historia, m.date(), m.hour) or 0.0) * tendencia for m in momentos]

    recientes = [t for t in ctx.turnos if t.inicio >= ctx.corte - timedelta(weeks=SEMANAS_ESTACIONALES)]
    capacidad = Counter(h.categoria_id for h in ctx.habitaciones)
    ocupadas = Counter(h.categoria_id for h in ctx.habitaciones if h.estado == "Ocupada")
    parte = Counter(t.categoria_id for t in recientes)
    total_recientes = sum(parte.values()) or 1

    def ocupacion_esperada(supervivencia: list[float], ocupadas_ahora: int, proporcion: float) -> list[float]:
        resultado = []
        sigue = supervivencia[1] or 1.0
        for i in range(horas):
            valor = ocupadas_ahora * min(supervivencia[min(i + 1, 13)] / sigue, 1.0)
            for j in range(min(i, 13) + 1):
                valor += llegadas[i - j] * proporcion * supervivencia[j]
            resultado.append(valor)
        return resultado

    total_hab = len(ctx.habitaciones)
    general = ocupacion_esperada(_supervivencia(recientes), sum(ocupadas.values()), 1.0)
    saturacion = []
    for categoria_id, cupo in capacidad.items():
        propios = [t for t in recientes if t.categoria_id == categoria_id]
        if not propios or not cupo:
            continue
        esperada = ocupacion_esperada(
            _supervivencia(propios), ocupadas[categoria_id], parte[categoria_id] / total_recientes
        )
        llenas = [i for i, v in enumerate(esperada) if v >= 0.9 * cupo]
        for desde, hasta in _franjas(llenas):
            saturacion.append(
                {
                    "categoria_id": categoria_id,
                    "categoria": ctx.nombre_categoria(categoria_id),
                    "color": ctx.categorias[categoria_id].color if categoria_id in ctx.categorias else "#244473",
                    "desde": momentos[desde].isoformat(),
                    "hasta": (momentos[hasta] + timedelta(hours=1)).isoformat(),
                    "habitaciones": cupo,
                }
            )
    filas = []
    for momento, esperadas, ocup in zip(momentos, llegadas, general, strict=True):
        filas.append(
            {
                "hora": momento.isoformat(),
                "etiqueta": hora_texto(momento.hour),
                "llegadas": round(esperadas, 2),
                "minimo": round(max(esperadas - 1.28 * math.sqrt(esperadas), 0), 2),
                "maximo": round(esperadas + 1.28 * math.sqrt(esperadas), 2),
                "ocupacion": round(min(ocup, total_hab), 2),
                "ocupacion_pct": round(min(ocup / total_hab, 1.0), 4) if total_hab else 0.0,
            }
        )
    total = sum(llegadas)
    pico = max(filas, key=lambda f: f["llegadas"]) if filas else None
    return {
        "horas": filas,
        "total": round(total, 1),
        "minimo": round(max(total - 1.64 * math.sqrt(total), 0)),
        "maximo": round(total + 1.64 * math.sqrt(total)),
        "saturacion": saturacion,
        "precision": precision(ctx),
        "tendencia": round(tendencia, 3),
        "pico": pico,
    }


def llegadas_del_dia(ctx: Contexto, dia: date) -> float:
    """Turnos esperados para un día completo (para el asistente: «¿cuántos turnos mañana?»)."""
    if not ctx.turnos:
        return 0.0
    conteo = _llegadas(ctx.turnos)
    inicio = ctx.turnos[0].inicio.date()
    return sum(estacional(conteo, inicio, dia, h) or 0.0 for h in range(24)) * _tendencia(ctx)


# --- Alertas --------------------------------------------------------------------------------------------------------


def cola_binomial(k: int, n: int, p: float) -> float:
    """P(X >= k) para X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def _alerta(
    tipo: str,
    severidad: str,
    titulo: str,
    detalle: str,
    sugerencia: str | None = None,
    evidencia: list[tuple[str, str]] | None = None,
) -> dict:
    return {
        "tipo": tipo,
        "severidad": severidad,
        "titulo": titulo,
        "detalle": detalle,
        "sugerencia": sugerencia,
        "evidencia": [{"etiqueta": e, "valor": v} for e, v in (evidencia or [])],
    }


def _alertas_de_caja(ctx: Contexto, dias: int) -> list[dict]:
    arqueos = [a for a in ctx.arqueos if a.momento >= ctx.corte - timedelta(days=dias)]
    alertas = []
    por_operador: dict[int, list[ArqueoCerrado]] = defaultdict(list)
    for a in arqueos:
        por_operador[a.operador_id].append(a)
    for operador_id, propios in por_operador.items():
        n, k = len(propios), sum(1 for a in propios if a.categoria == FALTANTE)
        resto = [a for a in arqueos if a.operador_id != operador_id]
        if n < 6 or not resto:
            continue
        p0 = (sum(1 for a in resto if a.categoria == FALTANTE) + 1) / (len(resto) + 2)
        if k / n <= p0:
            continue
        probabilidad = cola_binomial(k, n, p0)
        if probabilidad >= 0.05:
            continue
        nombre = ctx.nombres.get(operador_id, "Un conserje")
        faltante = -sum(a.diferencia for a in propios if a.categoria == FALTANTE)
        alertas.append(
            _alerta(
                "caja",
                "alta" if probabilidad < 0.01 else "media",
                f"{nombre}: faltantes por encima de lo normal",
                f"{k} faltantes en {n} arqueos ({porcentaje(k / n)}), contra {porcentaje(p0)} del resto del personal. "
                f"Que sea casualidad tiene una probabilidad de {porcentaje(probabilidad, 1)}.",
                "Revisar sus cierres en Control de caja y conversarlo; si se repite, hacer un cierre supervisado.",
                [("Faltante acumulado", pesos(faltante)), ("Período", f"últimos {dias} días")],
            )
        )
    diferencias = [abs(a.diferencia) for a in arqueos if a.diferencia]
    if diferencias:
        tipico = median(diferencias)
        umbral = max(4 * tipico, 8000)
        raros = sorted((a for a in arqueos if abs(a.diferencia) >= umbral), key=lambda a: a.diferencia)[:3]
        for a in raros:
            es_faltante = a.diferencia < 0
            alertas.append(
                _alerta(
                    "caja",
                    "alta" if es_faltante else "media",
                    f"{'Faltante' if es_faltante else 'Sobrante'} de {pesos(abs(a.diferencia))} "
                    f"el {fecha_corta(a.momento.date())}",
                    f"Guardia de las {a.franja} de {ctx.nombres.get(a.operador_id, '—')}: "
                    f"{abs(a.diferencia) / tipico:.0f} veces la diferencia típica ({pesos(tipico)}).",
                    "Abrir el arqueo en Control de caja y revisar sus cobros uno por uno.",
                )
            )
    return alertas


def _alertas_de_habitaciones(ctx: Contexto, dias: int) -> list[dict]:
    desde = ctx.corte - timedelta(days=dias)
    usos = Counter(t.habitacion_id for t in ctx.turnos if t.inicio >= desde)
    alertas = []
    por_categoria: dict[int, list[Habitacion]] = defaultdict(list)
    for h in ctx.habitaciones:
        if h.estado != "Mantenimiento":
            por_categoria[h.categoria_id].append(h)
    for categoria_id, habitaciones in por_categoria.items():
        if len(habitaciones) < 3:
            continue
        for h in habitaciones:
            otras = [usos[o.id] for o in habitaciones if o.id != h.id]
            referencia = median(otras)
            if referencia >= 10 and usos[h.id] < 0.6 * referencia:
                menos = 1 - usos[h.id] / referencia
                alertas.append(
                    _alerta(
                        "habitacion",
                        "media",
                        f"La habitación {h.numero} se usa {porcentaje(menos)} menos que las otras "
                        f"{ctx.nombre_categoria(categoria_id)}",
                        f"{usos[h.id]} turnos en {dias} días, contra {referencia:.0f} de mediana en su categoría.",
                        "¿Tiene algún desperfecto (aire, ducha, olor, ruido) que haga que se elija menos? "
                        "Conviene revisarla.",
                    )
                )
    return alertas


def _alertas_de_turnos(ctx: Contexto, dias: int) -> list[dict]:
    desde = ctx.corte - timedelta(days=dias)
    relampago = [t for t in ctx.turnos if t.inicio >= desde and t.minutos < 10]
    alertas = []
    if len(relampago) >= 3:
        quienes = Counter(t.cobrado_por for t in relampago)
        operador_id, cantidad = quienes.most_common(1)[0]
        concentrado = cantidad >= 3 and cantidad / len(relampago) >= 0.7
        alertas.append(
            _alerta(
                "turnos",
                "media" if concentrado else "info",
                f"{len(relampago)} turnos de menos de 10 minutos",
                (f"{cantidad} los cerró {ctx.nombres.get(operador_id, '—')}. " if concentrado else "")
                + "Pueden ser aperturas por error o habitaciones que el cliente rechazó.",
                "Si se repiten, conviene revisar con el personal cómo se registran.",
            )
        )
    # Cambio de la demanda: última semana contra el promedio de las tres anteriores.
    fin = ctx.inicio_dia(ctx.corte.date())
    semanas = [
        sum(1 for t in ctx.turnos if fin - timedelta(days=7 * (k + 1)) <= t.inicio < fin - timedelta(days=7 * k))
        for k in range(4)
    ]
    if all(semanas[1:]) and min(semanas[1:]) >= 20:
        cambio = semanas[0] / mean(semanas[1:]) - 1
        if cambio <= -0.2:
            alertas.append(
                _alerta(
                    "demanda",
                    "media",
                    f"La demanda bajó {porcentaje(-cambio)} en la última semana",
                    f"{semanas[0]} turnos contra {mean(semanas[1:]):.0f} de promedio en las tres semanas anteriores.",
                    "Mirá las sugerencias de tarifa: una promoción en las horas flojas puede ayudar.",
                )
            )
        elif cambio >= 0.15:
            alertas.append(
                _alerta(
                    "demanda",
                    "info",
                    f"La demanda creció {porcentaje(cambio)} en la última semana",
                    f"{semanas[0]} turnos contra {mean(semanas[1:]):.0f} de promedio en las tres semanas anteriores.",
                )
            )
    return alertas


def _alertas_de_inventario(ctx: Contexto, reposiciones: list[dict]) -> list[dict]:
    alertas = []
    criticos = [r for r in reposiciones if r["urgencia"] == "alta"]
    if criticos:
        nombres = ", ".join(r["descripcion"] for r in criticos[:4])
        alertas.append(
            _alerta(
                "inventario",
                "alta" if any(r["stock"] == 0 for r in criticos) else "media",
                f"{len(criticos)} {'artículo se agota' if len(criticos) == 1 else 'artículos se agotan'} "
                "en menos de 3 días",
                f"{nombres}.",
                "Ver la lista de reposición sugerida más abajo.",
            )
        )
    # Picos de venta: el último día completo contra el promedio de los 28 anteriores.
    ultimo = ctx.ultimo_dia_completo
    por_dia: dict[int, Counter] = defaultdict(Counter)
    for v in ctx.ventas:
        por_dia[v.articulo_id][v.momento.date()] += v.cantidad
    descripcion = {a.id: a.descripcion for a in ctx.articulos}
    for articulo_id, dias in por_dia.items():
        historia = [dias.get(ultimo - timedelta(days=k), 0) for k in range(1, 29)]
        hoy = dias.get(ultimo, 0)
        umbral = mean(historia) + 3 * pstdev(historia)
        if hoy >= 6 and hoy > umbral and articulo_id in descripcion:
            alertas.append(
                _alerta(
                    "inventario",
                    "info",
                    f"Pico de venta: {descripcion[articulo_id]}",
                    f"{hoy} unidades el {fecha_corta(ultimo)}, contra {mean(historia):.1f} por día de promedio.",
                    "Confirmá que el stock cargado coincide con el real.",
                )
            )
    return alertas


def _alertas_de_rotacion(ctx: Contexto, dias: int) -> list[dict]:
    alertas = []
    perdidos = clientes_perdidos(ctx, dias)
    if perdidos["total"] >= 5:
        franja = perdidos["franja"]
        sin_lugar = next((m for m in perdidos["motivos"] if m["motivo"] == SIN_LUGAR), None)
        alertas.append(
            _alerta(
                "demanda",
                "media" if perdidos["parte"] >= 0.03 else "info",
                f"Se fueron {perdidos['total']} clientes sin quedarse",
                f"Son {porcentaje(perdidos['parte'], 1)} de los que llegaron, unos "
                f"{pesos(perdidos['valor_estimado'])} al ticket promedio. El {porcentaje(franja['parte'])} se "
                f"concentra el {franja['dia']} de {franja['desde']} a {franja['hasta']} h.",
                "En esa franja ayudan una limpieza más rápida y subir la tarifa: el que llega igual paga más y la "
                "habitación se libera antes."
                if sin_lugar and sin_lugar["parte"] >= 0.5
                else "Revisá el motivo: si es el precio, mirá las sugerencias de tarifa.",
            )
        )
    desde = ctx.corte - timedelta(days=dias)
    sin_turno = [t for t in ctx.limpiezas if t.inicio >= desde and not t.tras_un_turno]
    if len(sin_turno) >= 3:
        operador_id, cantidad = Counter(t.operador_id for t in sin_turno).most_common(1)[0]
        concentrado = cantidad >= 3 and cantidad / len(sin_turno) >= 0.6
        alertas.append(
            _alerta(
                "habitacion",
                "media" if concentrado else "info",
                f"{len(sin_turno)} limpiezas sin un turno antes",
                (f"{cantidad} las marcó {ctx.nombres.get(operador_id, '—')}. " if concentrado else "")
                + "Puede ser un repaso de rutina o una estadía que no se registró.",
                "Cruzalas con las novedades de esas guardias y con el stock del minibar antes de sacar conclusiones.",
            )
        )
    return alertas


def _alertas_de_opiniones(ctx: Contexto, dias: int) -> list[dict]:
    """Una habitación que varios clientes marcan por lo mismo: es un arreglo pendiente, no una mala racha."""
    alertas = []
    for fila in opiniones(ctx, dias)["habitaciones"]:
        veces = fila["problema_veces"]
        if veces >= MINIMO_OPINIONES and veces / fila["cantidad"] >= 0.3:
            alertas.append(
                _alerta(
                    "habitacion",
                    "media",
                    f"Habitación {fila['numero']}: {veces} clientes marcaron «{fila['problema']}»",
                    f"Tiene {str(fila['promedio']).replace('.', ',')} de promedio en {fila['cantidad']} opiniones "
                    f"de los últimos {dias} días.",
                    "Revisala antes de que se note en la ocupación.",
                )
            )
    return alertas


ORDEN_SEVERIDAD = {"alta": 0, "media": 1, "info": 2}


def alertas(ctx: Contexto, reposiciones: list[dict] | None = None, dias: int = 30) -> list[dict]:
    lista = (
        _alertas_de_caja(ctx, dias)
        + _alertas_de_habitaciones(ctx, dias)
        + _alertas_de_turnos(ctx, dias)
        + _alertas_de_rotacion(ctx, dias)
        + _alertas_de_opiniones(ctx, dias)
        + _alertas_de_inventario(ctx, reposiciones if reposiciones is not None else reposicion(ctx))
    )
    return sorted(lista, key=lambda a: ORDEN_SEVERIDAD[a["severidad"]])


# --- Reposición -----------------------------------------------------------------------------------------------------


def reposicion(ctx: Contexto, dias: int = 28, objetivo_dias: int = 14) -> list[dict]:
    """Ritmo de venta de cada artículo (la última semana pesa el doble), días hasta agotarse y cuánto pedir."""
    desde, ultima_semana = ctx.corte - timedelta(days=dias), ctx.corte - timedelta(days=7)
    unidades, recientes = Counter(), Counter()
    for v in ctx.ventas:
        if v.momento >= desde:
            unidades[v.articulo_id] += v.cantidad
            if v.momento >= ultima_semana:
                recientes[v.articulo_id] += v.cantidad
    resultado = []
    for a in ctx.articulos:
        por_dia = (unidades[a.id] + recientes[a.id]) / (dias + 7)
        restantes = a.stock_actual / por_dia if por_dia > 0 else None
        faltan = max(0.0, por_dia * objetivo_dias - a.stock_actual)
        sugerido = int(math.ceil(faltan / 6) * 6) if faltan > 0 else 0
        if unidades[a.id] == 0:
            urgencia = "sin_movimiento"
        elif restantes is not None and restantes < 3:
            urgencia = "alta"
        elif restantes is not None and restantes < 7:
            urgencia = "media"
        else:
            urgencia = "baja"
        resultado.append(
            {
                "articulo_id": a.id,
                "codigo": a.codigo,
                "descripcion": a.descripcion,
                "stock": a.stock_actual,
                "vendidas_28d": unidades[a.id],
                "por_dia": round(por_dia, 2),
                "dias_restantes": round(restantes, 1) if restantes is not None else None,
                "agota_el": (ctx.ahora + timedelta(days=restantes)).date().isoformat()
                if restantes is not None
                else None,
                "sugerido": sugerido,
                "urgencia": urgencia,
            }
        )
    orden = {"alta": 0, "media": 1, "baja": 2, "sin_movimiento": 3}
    return sorted(resultado, key=lambda r: (orden[r["urgencia"]], r["dias_restantes"] or 0))


# --- Sugerencias de tarifa ------------------------------------------------------------------------------------------


def _ventanas(ctx: Contexto, dias: int, dias_semana: tuple[int, ...], hora: int, duracion: int):
    resultado, dia = [], (ctx.corte - timedelta(days=dias)).date()
    while dia < ctx.corte.date():
        if dia.weekday() in dias_semana:
            inicio = datetime.combine(dia, time(hora), ctx.zona)
            if inicio + timedelta(hours=duracion) <= ctx.corte:
                resultado.append((inicio, inicio + timedelta(hours=duracion)))
        dia += timedelta(days=1)
    return resultado


def _redondear(valor: float, paso: int = 500) -> int:
    return max(paso, int(round(valor / paso) * paso))


def _simular(
    turnos: list[TurnoCerrado], parametros: ParametrosTarifa, cambio_precio: float, elasticidad: float
) -> float:
    """Ingreso por estadías (sin consumos) si los mismos clientes hubieran pagado con `parametros`, con la cantidad
    de turnos ajustada por la elasticidad supuesta."""
    estadias = sum(
        float(parametros.tarifa_base) + float(calcular_sobreturno(timedelta(minutes=t.minutos), parametros))
        for t in turnos
    )
    return estadias * (1 + elasticidad * cambio_precio)


def _parametros(tarifa: Tarifa) -> dict:
    return {
        "tarifa_base": float(tarifa.tarifa_base),
        "estadia_base_min": tarifa.estadia_base_min,
        "fraccion_min": tarifa.fraccion_min,
        "tarifa_fraccion": float(tarifa.tarifa_fraccion),
        "tolerancia_min": tarifa.tolerancia_min,
        "tope": float(tarifa.tope) if tarifa.tope is not None else None,
    }


def _supuesto(turnos: int, dias: int, elasticidad: float) -> str:
    base = f"Simulado con las {turnos} estadías reales de los últimos {dias} días"
    if not elasticidad:
        return base + ", suponiendo que vienen los mismos clientes (reciben más tiempo por el precio mayor)."
    return (
        f"{base} y una elasticidad de {str(elasticidad).replace('.', ',')}: si el precio cambia 10%, los turnos "
        f"cambian {abs(elasticidad) * 10:.0f}% en sentido contrario."
    )


def _estadia_mas_larga(turnos: list[TurnoCerrado], actual: ParametrosTarifa) -> ParametrosTarifa | None:
    """Estadía base 30 minutos más larga con la menor suba de la base que, simulada sobre las mismas estadías, no
    cobra menos que la tarifa actual. None si ninguna suba razonable lo logra."""
    ingreso_actual = _simular(turnos, actual, 0, 0)
    for factor in (1.1, 1.15, 1.2, 1.25):
        propuesta = ParametrosTarifa(
            tarifa_base=Decimal(_redondear(float(actual.tarifa_base) * factor)),
            estadia_base_min=actual.estadia_base_min + 30,
            tolerancia_min=actual.tolerancia_min,
            fraccion_min=actual.fraccion_min,
            tarifa_fraccion=actual.tarifa_fraccion,
            tope=actual.tope,
        )
        if _simular(turnos, propuesta, 0, 0) >= ingreso_actual:
            return propuesta
    return None


def _ajustada(parametros: ParametrosTarifa, factor: float, con_fraccion: bool) -> ParametrosTarifa:
    """La misma tarifa con el precio cambiado por `factor`, redondeado."""
    fraccion = float(parametros.tarifa_fraccion)
    return replace(
        parametros,
        tarifa_base=Decimal(_redondear(float(parametros.tarifa_base) * factor)),
        tarifa_fraccion=Decimal(_redondear(fraccion * factor)) if con_fraccion else parametros.tarifa_fraccion,
    )


def _abiertos_en(turnos: list[TurnoCerrado], dias: int, desde: time, hasta: time) -> list[TurnoCerrado]:
    """Los turnos que se abrieron dentro de una regla: los que habrían pagado esa tarifa."""
    rangos = franjas.tramos(dias, desde, hasta)
    return [t for t in turnos if any(a <= franjas.minuto_de_semana(t.inicio) < b for a, b in rangos)]


def _regla_libre(regla: ReglaSugerida, propias: list[FranjaTarifa]) -> ReglaSugerida | None:
    """La regla, si no se pisa con ninguna tarifa especial de la categoría."""
    rangos = franjas.tramos(regla.dias, regla.desde, regla.hasta)
    pisa = any(franjas.primer_cruce(rangos, franjas.tramos(f.dias, f.desde, f.hasta)) is not None for f in propias)
    return None if pisa else regla


def _rendimiento(ctx: Contexto, turnos: list[TurnoCerrado]) -> list[dict]:
    """Cuánto rindió cada tarifa especial: turnos y lo cobrado por estadías."""
    por_franja: dict[int, list[TurnoCerrado]] = defaultdict(list)
    for t in turnos:
        tarifa = ctx.tarifas_por_id.get(t.tarifa_id)
        if tarifa is not None and tarifa.franja_id is not None:
            por_franja[tarifa.franja_id].append(t)
    nombres = {f.id: f.nombre for f in ctx.franjas}
    return [
        {
            "franja": nombres.get(franja_id, "Tarifa especial"),
            "turnos": len(lista),
            "ingresos": round(sum(t.total - t.consumos for t in lista), 2),
        }
        for franja_id, lista in sorted(por_franja.items(), key=lambda p: -len(p[1]))
    ]


def sugerencias_de_tarifa(ctx: Contexto, dias: int = 28) -> list[dict]:
    pico = _ventanas(ctx, dias, (4, 5), 22, 4)  # viernes y sábado de 22 a 2
    valle = _ventanas(ctx, dias, (0, 1, 2, 3), 6, 12)  # lunes a jueves de 6 a 18
    todo = [(ctx.corte - timedelta(days=dias), ctx.corte)]
    capacidad = Counter(h.categoria_id for h in ctx.habitaciones if h.estado != "Mantenimiento")
    resultado = []
    for categoria_id, cupo in sorted(
        capacidad.items(), key=lambda p: ctx.categorias[p[0]].orden if p[0] in ctx.categorias else 0
    ):
        tarifa = ctx.tarifas.get(categoria_id)
        if tarifa is None:
            continue
        propios = [t for t in ctx.turnos if t.categoria_id == categoria_id and t.fin > todo[0][0]]
        en_periodo = [t for t in propios if t.fin >= todo[0][0]]
        # La tarifa general solo la pagó quien no entró en una especial: sobre ellos se simula un cambio de la general.
        generales = [
            t
            for t in en_periodo
            if (pagada := ctx.tarifas_por_id.get(t.tarifa_id)) is None or pagada.franja_id is None
        ]
        o_pico, o_valle, o_total = (ocupacion(propios, v, cupo) for v in (pico, valle, todo))
        con_sobreturno = sum(1 for t in en_periodo if t.sobreturno > 0) / len(en_periodo) if en_periodo else 0.0
        actual = tarifa.parametros()
        accion, propuesta, elasticidad, cambio = "mantener", None, 0.0, 0.0
        # Lo que se compara con la propuesta, quiénes la pagarían y, si es una tarifa especial, cuál.
        referencia, afectados = actual, generales
        franja, regla_nueva = None, None
        propias_franjas = ctx.franjas_de(categoria_id)
        if len(en_periodo) < 15:
            titulo = "Pocos datos todavía"
            explicacion = f"Solo {len(en_periodo)} turnos en {dias} días: se necesitan más para sugerir un cambio."
        elif o_pico is not None and o_pico >= 0.7:
            accion, cambio, elasticidad = "subir", 0.10, ELASTICIDAD_PICO
            ocupada = f"Las noches de viernes y sábado (de 22 a 2 h) está ocupada el {porcentaje(o_pico)} del tiempo"
            franja = franjas.franja_en(propias_franjas, MINUTO_DEL_PICO)
            tarifa_pico = ctx.tarifa_de_franja(franja.id) if franja else None
            regla_nueva = None if franja else _regla_libre(REGLA_PICO, propias_franjas)
            if franja is not None and tarifa_pico is not None:
                referencia = tarifa_pico.parametros()
                afectados = _abiertos_en(en_periodo, franja.dias, franja.desde, franja.hasta)
                propuesta = _ajustada(referencia, 1.1, True)
                titulo = f"Subir «{franja.nombre}» un 10%"
                explicacion = (
                    f"{ocupada}, aun con su tarifa especial: los clientes siguen llegando. Hay margen para cobrar más."
                )
            elif regla_nueva is not None:
                afectados = _abiertos_en(generales, regla_nueva.dias, regla_nueva.desde, regla_nueva.hasta)
                propuesta = _ajustada(actual, 1.1, True)
                titulo = "Cobrar 10% más las noches de fin de semana"
                explicacion = (
                    f"{ocupada}: en el pico casi no hay lugar y los clientes que llegan se van a otro lado. Una tarifa "
                    "especial cobra más solo cuando hay demanda, sin tocar el resto de la semana."
                )
            else:
                franja = None
                propuesta = _ajustada(actual, 1.1, True)
                titulo = "Subir la tarifa un 10%"
                explicacion = (
                    f"{ocupada}: en el pico casi no hay lugar y los clientes que llegan se van a otro lado. Hay margen "
                    "para cobrar más."
                )
        elif con_sobreturno >= 0.35 and (larga := _estadia_mas_larga(generales, actual)) is not None:
            accion, propuesta = "estadia", larga
            titulo = "Alargar la estadía base 30 minutos"
            explicacion = (
                f"{porcentaje(con_sobreturno)} de los turnos paga sobreturno: los clientes quieren quedarse más. Con "
                f"{minutos_texto(larga.estadia_base_min)} a {pesos(float(larga.tarifa_base))} la cuenta es más simple "
                "para el cliente y el motel cobra lo mismo o más."
            )
        elif o_total is not None and o_total < 0.25 and (o_valle or 0) < 0.2:
            accion, cambio, elasticidad = "bajar", -0.10, ELASTICIDAD_VALLE
            propuesta = _ajustada(actual, 0.9, False)
            regla_nueva = _regla_libre(REGLA_VALLE, propias_franjas)
            ocupada = (
                f"Está ocupada solo el {porcentaje(o_total)} del tiempo (de lunes a jueves de día, el "
                f"{porcentaje(o_valle or 0)})"
            )
            if regla_nueva is not None:
                afectados = _abiertos_en(generales, regla_nueva.dias, regla_nueva.desde, regla_nueva.hasta)
                titulo = "Bajar 10% de lunes a jueves de día"
                explicacion = (
                    f"{ocupada}. Una tarifa especial para esos horarios atrae más turnos sin tocar las noches ni el "
                    "fin de semana."
                )
            else:
                titulo = "Bajar la tarifa un 10%"
                explicacion = f"{ocupada}. Con la demanda tan floja, un precio menor atrae más turnos."
        else:
            titulo = "La tarifa está en equilibrio"
            explicacion = (
                f"Ocupación de {porcentaje(o_total or 0)} en el período y {porcentaje(o_pico or 0)} en el pico del "
                "fin de semana: no hay una señal clara para cambiarla."
            )
        impacto = None
        if propuesta is not None:
            if propuesta.tope is not None and propuesta.tope < propuesta.tarifa_base:
                propuesta = ParametrosTarifa(**{**propuesta.__dict__, "tope": propuesta.tarifa_base})
            ingreso_nuevo = _simular(afectados, propuesta, cambio, elasticidad)
            impacto = round((ingreso_nuevo - _simular(afectados, referencia, 0, 0)) * 30 / dias, -2)
        categoria = ctx.categorias.get(categoria_id)
        resultado.append(
            {
                "categoria_id": categoria_id,
                "categoria": ctx.nombre_categoria(categoria_id),
                "color": categoria.color if categoria else "#244473",
                "habitaciones": cupo,
                "turnos": len(en_periodo),
                "ocupacion_pico": o_pico,
                "ocupacion_valle": o_valle,
                "ocupacion_total": o_total,
                "con_sobreturno": round(con_sobreturno, 4),
                "accion": accion,
                "titulo": titulo,
                "explicacion": explicacion,
                "impacto_mensual": impacto,
                "supuesto": _supuesto(len(afectados), dias, elasticidad) if propuesta is not None else None,
                "actual": _parametros(referencia),
                # Si la propuesta es sobre una tarifa especial que ya existe, o una nueva para crear.
                "franja_id": franja.id if franja is not None else None,
                "franja_nombre": franja.nombre if franja is not None else None,
                "franja_nueva": (
                    {
                        "nombre": regla_nueva.nombre,
                        "dias": regla_nueva.dias,
                        "desde": franjas.hora_texto(regla_nueva.desde),
                        "hasta": franjas.hora_texto(regla_nueva.hasta),
                        "regla": franjas.regla_texto(regla_nueva.dias, regla_nueva.desde, regla_nueva.hasta),
                    }
                    if regla_nueva is not None
                    else None
                ),
                "rendimiento": _rendimiento(ctx, en_periodo),
                "propuesta": (
                    {
                        "tarifa_base": float(propuesta.tarifa_base),
                        "estadia_base_min": propuesta.estadia_base_min,
                        "fraccion_min": propuesta.fraccion_min,
                        "tarifa_fraccion": float(propuesta.tarifa_fraccion),
                        "tolerancia_min": propuesta.tolerancia_min,
                        "tope": float(propuesta.tope) if propuesta.tope is not None else None,
                    }
                    if propuesta is not None
                    else None
                ),
            }
        )
    return resultado


# --- Resumen en lenguaje natural ------------------------------------------------------------------------------------


def resumen(
    ctx: Contexto,
    kpis: dict,
    pron: dict,
    lista_alertas: list[dict],
    mapa: dict,
    reposiciones: list[dict],
    perdidos: dict | None = None,
) -> dict:
    puntos: list[dict] = []
    if not ctx.turnos:
        return {
            "titular": "Todavía no hay turnos cerrados para analizar.",
            "puntos": [
                {"icono": "info", "texto": "El análisis aparece cuando se arquea la primera guardia con turnos."}
            ],
        }
    ayer = ctx.ultimo_dia_completo
    del_dia = ctx.cobrados_entre(ctx.inicio_dia(ayer), ctx.inicio_dia(ayer + timedelta(days=1)))
    previos = [
        ctx.cobrados_entre(
            ctx.inicio_dia(ayer - timedelta(weeks=k)), ctx.inicio_dia(ayer - timedelta(weeks=k) + timedelta(days=1))
        )
        for k in range(1, 5)
    ]
    previos = [p for p in previos if p]
    ingresos_ayer = sum(t.total for t in del_dia)
    comparado = ""
    if previos:
        referencia = mean(sum(t.total for t in p) for p in previos)
        cambio = variacion(ingresos_ayer, referencia)
        if cambio is not None:
            comparado = (
                f", {porcentaje(abs(cambio))} {'más' if cambio >= 0 else 'menos'} que el promedio de los "
                f"{DIAS[ayer.weekday()]} anteriores"
            )
    puntos.append(
        {
            "icono": "calendar",
            "texto": f"El {fecha_corta(ayer)} se cobraron {len(del_dia)} turnos por {pesos(ingresos_ayer)}{comparado}.",
        }
    )

    cambio_semana = kpis["ingresos_7d_variacion"]
    puntos.append(
        {
            "icono": "trending-up" if (cambio_semana or 0) >= 0 else "trending-down",
            "texto": (
                f"Últimos 7 días: {kpis['turnos_7d']} turnos y {pesos(kpis['ingresos_7d'])} "
                f"({con_signo(cambio_semana)} contra la semana anterior), con un ticket promedio de "
                f"{pesos(kpis['ticket_7d'])}."
            ),
        }
    )

    fin = ctx.inicio_dia(ctx.corte.date())
    por_categoria = []
    for categoria_id in {t.categoria_id for t in ctx.turnos}:
        ahora_c = sum(
            t.total for t in ctx.cobrados_entre(fin - timedelta(days=7), fin) if t.categoria_id == categoria_id
        )
        antes_c = sum(
            t.total
            for t in ctx.cobrados_entre(fin - timedelta(days=14), fin - timedelta(days=7))
            if t.categoria_id == categoria_id
        )
        cambio = variacion(ahora_c, antes_c)
        if cambio is not None and antes_c >= 50000:
            por_categoria.append((cambio, categoria_id))
    if por_categoria:
        cambio, categoria_id = max(por_categoria)
        if cambio > 0.05:
            puntos.append(
                {
                    "icono": "sparkles",
                    "texto": f"La categoría que más creció es {ctx.nombre_categoria(categoria_id)}: "
                    f"{con_signo(cambio)} en "
                    "ingresos contra la semana anterior.",
                }
            )

    if kpis["ocupacion_7d"] is not None:
        puntos.append(
            {
                "icono": "bed",
                "texto": (
                    f"Ocupación promedio de la semana: {porcentaje(kpis['ocupacion_7d'])}. El día más fuerte es el "
                    f"{mapa['dia_mas_fuerte']} y el pico de llegadas, el {mapa['pico']['dia']} "
                    f"a las {mapa['pico']['hora']} h."
                ),
            }
        )

    de_caja = [a for a in lista_alertas if a["tipo"] == "caja"]
    puntos.append(
        {
            "icono": "wallet" if not de_caja else "alert",
            "texto": (
                "Caja: sin alertas en los últimos 30 días."
                if not de_caja
                else f"Caja: {len(de_caja)} {'alerta' if len(de_caja) == 1 else 'alertas'} para revisar "
                f"({de_caja[0]['titulo']})."
            ),
        }
    )

    if pron["horas"]:
        pico = pron["pico"]
        texto = (
            f"Próximas 24 h: se esperan unos {pron['total']:.0f} turnos (entre {pron['minimo']} y {pron['maximo']}), "
            f"con el pico a las {pico['etiqueta']}."
        )
        if pron["saturacion"]:
            primera = pron["saturacion"][0]
            desde = datetime.fromisoformat(primera["desde"])
            texto += f" {primera['categoria']} se llenaría desde las {desde.hour} h."
        puntos.append({"icono": "sparkles", "texto": texto})

    if perdidos and perdidos["total"]:
        puntos.append(
            {
                "icono": "alert",
                "texto": f"Últimos {perdidos['dias']} días: se fueron {perdidos['total']} clientes sin quedarse, unos "
                f"{pesos(perdidos['valor_estimado'])} al ticket promedio.",
            }
        )

    urgentes = [r for r in reposiciones if r["urgencia"] in ("alta", "media")]
    if urgentes:
        puntos.append(
            {
                "icono": "package",
                "texto": f"Reponer pronto: {', '.join(r['descripcion'] for r in urgentes[:3])}"
                + (f" y {len(urgentes) - 3} más." if len(urgentes) > 3 else "."),
            }
        )

    altas = sum(1 for a in lista_alertas if a["severidad"] == "alta")
    if altas:
        titular = f"Hay {altas} {'alerta importante' if altas == 1 else 'alertas importantes'} para revisar."
    elif (cambio_semana or 0) >= 0.05:
        titular = f"Buena semana: los ingresos crecieron {porcentaje(cambio_semana)}."
    elif (cambio_semana or 0) <= -0.05:
        titular = f"Semana más floja: los ingresos bajaron {porcentaje(-cambio_semana)}."
    else:
        titular = "Semana estable, sin sobresaltos."
    return {"titular": titular, "puntos": puntos}


def medios_de_pago(ctx: Contexto, dias: int = 30) -> list[dict]:
    desde = ctx.corte - timedelta(days=dias)
    totales = Counter()
    for c in ctx.cobros:
        if c.momento >= desde:
            totales[c.medio] += c.monto
    suma = sum(totales.values()) or 1
    etiqueta = {"EFECTIVO": "Efectivo", "POSNET": "POSNET", "MERCADO_PAGO": "Mercado Pago"}
    return [
        {"medio": m, "etiqueta": etiqueta.get(m, m), "monto": round(v, 2), "parte": round(v / suma, 4)}
        for m, v in totales.most_common()
    ]


def articulos_mas_vendidos(ctx: Contexto, dias: int = 30, cantidad: int = 6) -> list[dict]:
    desde = ctx.corte - timedelta(days=dias)
    unidades, importe = Counter(), Counter()
    for v in ctx.ventas:
        if v.momento >= desde:
            unidades[v.articulo_id] += v.cantidad
            importe[v.articulo_id] += v.subtotal
    descripcion = {a.id: a.descripcion for a in ctx.articulos}
    return [
        {
            "articulo_id": a,
            "descripcion": descripcion.get(a, f"Artículo {a}"),
            "unidades": u,
            "importe": round(importe[a], 2),
        }
        for a, u in unidades.most_common(cantidad)
    ]


async def tablero(db: AsyncSession, ahora: datetime | None = None) -> dict:
    ctx = await contexto(db, ahora)
    kpis = indicadores(ctx)
    reposiciones = reposicion(ctx)
    lista_alertas = alertas(ctx, reposiciones)
    pron = pronostico(ctx)
    mapa = mapa_demanda(ctx)
    perdidos = clientes_perdidos(ctx)
    return {
        "generado_en": ctx.ahora.isoformat(),
        "corte": ctx.corte.isoformat(),
        "guardia_abierta": ctx.hay_guardia_abierta,
        "indicadores": kpis,
        "resumen": resumen(ctx, kpis, pron, lista_alertas, mapa, reposiciones, perdidos),
        "alertas": lista_alertas,
        "pronostico": pron,
        "demanda": mapa,
        "serie": serie_diaria(ctx),
        "sugerencias": sugerencias_de_tarifa(ctx),
        "reposicion": reposiciones,
        "medios_de_pago": medios_de_pago(ctx),
        "mas_vendidos": articulos_mas_vendidos(ctx),
        "clientes_perdidos": perdidos,
        "rotacion": rotacion(ctx),
        "opiniones": opiniones(ctx),
    }
