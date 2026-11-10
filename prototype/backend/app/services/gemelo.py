"""Gemelo del motel: repite las llegadas reales de los últimos días con otras condiciones.

Toma cada turno cobrado con su hora de llegada, su duración, su limpieza y lo que pagó, más los clientes que se fueron,
y los hace pasar otra vez por un motel con otra limpieza, otras habitaciones u otro precio: quien llega cuando hay una
habitación libre de su categoría entra, y el que no, se va. Así un cambio se puede probar antes de hacerlo.

Lo que se compara son dos corridas del mismo modelo (las condiciones de hoy contra las nuevas), para que los errores
del modelo se cancelen, y cada resultado dice cuánto del pasado real reproduce. El azar (qué estadía se le asigna a un
cliente perdido, quién reacciona a un cambio de precio) está fijo: los mismos parámetros dan siempre el mismo resultado.

RN-RES-03: trabaja con el contexto de la inteligencia, que solo ve lo ya arqueado.
"""

import heapq
import random
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from statistics import mean, median

from app.models.cliente_perdido import PRECIO
from app.services import inteligencia as ia
from app.services.rotacion import LIMPIEZA_POR_DEFECTO_MIN

SEMILLA = 20261103
# Una limpieza se empareja con el turno que la originó aunque el cobro y el evento difieran unos segundos.
TOLERANCIA_S = 300
# El cuarto de las horas de la semana con más llegadas es «pico»; el resto, «floja».
PARTE_PICO = 0.25
CAMBIO_MAXIMO_HABITACIONES = 20


@dataclass(frozen=True)
class Llegada:
    momento: datetime
    categoria_id: int | None
    minutos: float
    limpieza: float
    estadia: float
    consumos: float
    # Si de verdad se atendió (un turno cobrado) o se fue (un cliente perdido).
    real: bool
    azar: float


@dataclass(frozen=True)
class Escenario:
    limpieza_min: float | None = None
    habitaciones: dict[int, int] = field(default_factory=dict)
    precio_pct: float = 0.0
    precio_cuando: str = "siempre"  # siempre, pico o floja


@dataclass
class Corrida:
    turnos: int = 0
    reales_atendidos: int = 0
    perdidos: int = 0
    ingresos: float = 0.0
    minutos_ocupados: float = 0.0
    perdidos_por_hora: list[int] = field(default_factory=lambda: [0] * 24)


def llegadas_de(ctx: ia.Contexto, dias: int) -> tuple[list[Llegada], float]:
    """Las llegadas de los últimos `dias` días y la limpieza típica. Los clientes perdidos por el precio no se repiten:
    no se fueron por falta de lugar."""
    rng = random.Random(SEMILLA)
    desde = ctx.corte - timedelta(days=dias)
    turnos = [t for t in ctx.turnos if t.inicio >= desde]
    medidas: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for limpieza in ctx.limpiezas:
        if limpieza.tras_un_turno and limpieza.minutos is not None:
            medidas[limpieza.habitacion_id].append((limpieza.inicio.timestamp(), limpieza.minutos))
    for lista in medidas.values():
        lista.sort()
    tipicas = [m for lista in medidas.values() for _, m in lista]
    tipica = median(tipicas) if tipicas else float(LIMPIEZA_POR_DEFECTO_MIN)

    def limpieza_de(habitacion_id: int, fin: datetime) -> float:
        lista = medidas.get(habitacion_id, [])
        i = bisect_left(lista, (fin.timestamp() - TOLERANCIA_S,))
        if i < len(lista) and abs(lista[i][0] - fin.timestamp()) <= TOLERANCIA_S:
            return lista[i][1]
        return tipica

    llegadas = [
        Llegada(
            t.inicio,
            t.categoria_id,
            t.minutos,
            limpieza_de(t.habitacion_id, t.fin),
            t.total - t.consumos,
            t.consumos,
            True,
            rng.random(),
        )
        for t in turnos
    ]
    por_categoria: dict[int, list[ia.TurnoCerrado]] = defaultdict(list)
    for t in turnos:
        por_categoria[t.categoria_id].append(t)
    for p in sorted(ctx.perdidos, key=lambda x: x.momento):
        if p.momento < desde or p.motivo == PRECIO or not turnos:
            continue
        categoria = p.categoria_id if p.categoria_id in por_categoria else None
        modelo = rng.choice(por_categoria[categoria] if categoria is not None else turnos)
        llegadas.append(
            Llegada(
                p.momento,
                categoria,
                modelo.minutos,
                tipica,
                modelo.total - modelo.consumos,
                modelo.consumos,
                False,
                rng.random(),
            )
        )
    return sorted(llegadas, key=lambda x: x.momento), tipica


def horas_pico(llegadas: list[Llegada]) -> set[tuple[int, int]]:
    """Las horas de la semana (día, hora) con más llegadas."""
    conteo = Counter((x.momento.weekday(), x.momento.hour) for x in llegadas)
    cantidad = max(round(168 * PARTE_PICO), 1)
    return {hora for hora, _ in conteo.most_common(cantidad)}


def aplicar_precio(llegadas: list[Llegada], escenario: Escenario, pico: set[tuple[int, int]]) -> list[Llegada]:
    """Un cambio de precio mueve lo que paga cada uno y, según la elasticidad, cuántos llegan: si sube, algunos no
    entran; si baja, aparecen clientes nuevos. Sobre la estadía; los consumos no cambian."""
    if not escenario.precio_pct:
        return llegadas
    cambio_precio = escenario.precio_pct / 100
    resultado = []
    for llegada in llegadas:
        en_pico = (llegada.momento.weekday(), llegada.momento.hour) in pico
        if escenario.precio_cuando == "pico" and not en_pico or escenario.precio_cuando == "floja" and en_pico:
            resultado.append(llegada)
            continue
        cambio_demanda = (ia.ELASTICIDAD_PICO if en_pico else ia.ELASTICIDAD_VALLE) * cambio_precio
        nueva = replace(llegada, estadia=llegada.estadia * (1 + cambio_precio))
        if cambio_demanda < 0:
            if llegada.azar < 1 + cambio_demanda:
                resultado.append(nueva)
            continue
        resultado.append(nueva)
        if llegada.azar < cambio_demanda:
            # Un cliente nuevo, parecido a este, que llega un rato después.
            retraso = 30 + 30 * llegada.azar / cambio_demanda
            resultado.append(replace(nueva, momento=llegada.momento + timedelta(minutes=retraso), real=False))
    return sorted(resultado, key=lambda x: x.momento)


def repetir(
    llegadas: list[Llegada], capacidad: dict[int, int], inicio: datetime, factor_limpieza: float = 1.0
) -> Corrida:
    """Pasa las llegadas por el motel: cada categoría es una cola de los momentos en que se libera cada habitación."""
    libres = {c: [inicio] * n for c, n in capacidad.items()}
    corrida = Corrida()
    for llegada in llegadas:
        categoria = llegada.categoria_id
        if categoria is None:
            categoria = next((c for c, cola in libres.items() if cola and cola[0] <= llegada.momento), None)
        cola = libres.get(categoria)
        if not cola or cola[0] > llegada.momento:
            corrida.perdidos += 1
            corrida.perdidos_por_hora[llegada.momento.hour] += 1
            continue
        fin = llegada.momento + timedelta(minutes=llegada.minutos + llegada.limpieza * factor_limpieza)
        heapq.heapreplace(cola, fin)
        corrida.turnos += 1
        corrida.reales_atendidos += llegada.real
        corrida.ingresos += llegada.estadia + llegada.consumos
        corrida.minutos_ocupados += llegada.minutos
    return corrida


def _capacidad(ctx: ia.Contexto) -> dict[int, int]:
    capacidad = Counter(h.categoria_id for h in ctx.habitaciones)
    return dict(capacidad)


def _foto(corrida: Corrida, habitaciones: int, dias: int) -> dict:
    disponibles = habitaciones * dias * 24 * 60
    return {
        "turnos": corrida.turnos,
        "perdidos": corrida.perdidos,
        "ingresos": round(corrida.ingresos, 2),
        "ocupacion": round(min(corrida.minutos_ocupados / disponibles, 1.0), 4) if disponibles else 0.0,
    }


def _plural(cantidad: int, singular: str, plural: str) -> str:
    return f"{abs(cantidad)} {singular if abs(cantidad) == 1 else plural}"


def _conclusion(base: Corrida, nueva: Corrida, por_mes: float, hay_cambios: bool) -> str:
    if not hay_cambios:
        return "Estas son las condiciones de hoy. Mové algo para ver qué cambiaría."
    turnos = nueva.turnos - base.turnos
    perdidos = nueva.perdidos - base.perdidos
    partes = []
    if turnos:
        partes.append(f"se atenderían {_plural(turnos, 'turno', 'turnos')} {'más' if turnos > 0 else 'menos'}")
    if perdidos:
        partes.append(f"se perderían {_plural(perdidos, 'cliente', 'clientes')} {'más' if perdidos > 0 else 'menos'}")
    inicio = ("En el período " + " y ".join(partes) + ".") if partes else "La cantidad de turnos no cambiaría."
    diferencia = (nueva.ingresos - base.ingresos) * por_mes
    if abs(diferencia) < 1:
        return f"{inicio} Los ingresos quedarían igual."
    verbo = "subirían" if diferencia > 0 else "bajarían"
    return f"{inicio} Los ingresos {verbo} unos {ia.pesos(abs(diferencia))} por mes."


def simular(ctx: ia.Contexto, escenario: Escenario, dias: int = 30) -> dict:
    llegadas, limpieza = llegadas_de(ctx, dias)
    capacidad = _capacidad(ctx)
    categorias = [
        {
            "categoria_id": c,
            "nombre": ctx.nombre_categoria(c),
            "color": ctx.categorias[c].color if c in ctx.categorias else "#244473",
            "actuales": n,
            "cambio": escenario.habitaciones.get(c, 0),
        }
        for c, n in sorted(capacidad.items(), key=lambda p: ctx.categorias[p[0]].orden if p[0] in ctx.categorias else 0)
    ]
    if not llegadas:
        return {
            "disponible": False,
            "dias": dias,
            "limpieza_actual": round(limpieza),
            "categorias": categorias,
            "conclusion": "Todavía no hay turnos cerrados para repetir.",
        }

    inicio = llegadas[0].momento - timedelta(days=1)
    base = repetir(llegadas, capacidad, inicio)
    nueva_capacidad = {
        c: max(
            n + max(min(escenario.habitaciones.get(c, 0), CAMBIO_MAXIMO_HABITACIONES), -CAMBIO_MAXIMO_HABITACIONES), 0
        )
        for c, n in capacidad.items()
    }
    factor = escenario.limpieza_min / limpieza if escenario.limpieza_min else 1.0
    nueva = repetir(aplicar_precio(llegadas, escenario, horas_pico(llegadas)), nueva_capacidad, inicio, factor)

    habitaciones_base, habitaciones_nuevas = sum(capacidad.values()), sum(nueva_capacidad.values())
    por_mes = 30 / dias
    hay_cambios = bool(
        escenario.precio_pct or factor != 1.0 or any(nueva_capacidad[c] != capacidad[c] for c in capacidad)
    )
    reales = sum(1 for x in llegadas if x.real)
    perdidas = len(llegadas) - reales
    supuestos = [
        f"Repite las {reales} llegadas reales de los últimos {dias} días y {perdidas} clientes que se fueron, cada uno "
        "con su duración y su consumo.",
        "Solo cuentan los clientes perdidos que se registraron: la mejora real puede ser mayor.",
        "Un cliente solo entra a la categoría que buscaba.",
        "No descuenta costos: ni lo que sale acelerar la limpieza ni construir una habitación.",
    ]
    if escenario.precio_pct:
        supuestos.append(
            f"Precio: se supone que la demanda reacciona {abs(ia.ELASTICIDAD_PICO):g} veces el cambio en horas pico y "
            f"{abs(ia.ELASTICIDAD_VALLE):g} en las flojas. Es un supuesto, no una medición."
        )
    return {
        "disponible": True,
        "dias": dias,
        "limpieza_actual": round(limpieza),
        "categorias": categorias,
        "base": _foto(base, habitaciones_base, dias),
        "escenario": _foto(nueva, habitaciones_nuevas, dias),
        "diferencia": {
            "turnos": nueva.turnos - base.turnos,
            "perdidos": nueva.perdidos - base.perdidos,
            "ingresos": round(nueva.ingresos - base.ingresos, 2),
            "ingresos_por_mes": round((nueva.ingresos - base.ingresos) * por_mes, 2),
        },
        "por_hora": [
            {
                "hora": h,
                "etiqueta": ia.hora_texto(h),
                "base": base.perdidos_por_hora[h],
                "escenario": nueva.perdidos_por_hora[h],
            }
            for h in range(24)
        ],
        # Cuánto del pasado reproduce el modelo: de los turnos que se atendieron de verdad, cuántos atiende él.
        "calibracion": {
            "turnos_reales": reales,
            "turnos_modelo": base.reales_atendidos,
            "coincidencia": round(base.reales_atendidos / reales, 4) if reales else None,
            "ticket": round(mean(x.estadia + x.consumos for x in llegadas if x.real), 2) if reales else 0.0,
        },
        "conclusion": _conclusion(base, nueva, por_mes, hay_cambios),
        "supuestos": supuestos,
    }
