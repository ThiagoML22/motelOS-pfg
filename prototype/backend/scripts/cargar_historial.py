"""Historial de demostración: semanas de operación pasada para que la gerencia y la inteligencia local tengan datos.

Por cada establecimiento de la demo genera guardias de 8 h ya arqueadas, con sus turnos, consumos y cobros:
- demanda con la forma de un motel: noches de viernes y sábado llenas, la siesta de la tarde, madrugadas tranquilas,
  y un leve crecimiento a lo largo del período;
- estadías por categoría con la tarifa vigente (sobreturnos, algún pernocte con tope) y limpieza entre turnos;
- arqueos casi siempre correctos, con más faltantes en uno de los conserjes y una habitación que se usa poco:
  así la detección de anomalías tiene algo real para mostrar;
- el historial de estados de cada habitación y los clientes que se fueron sin quedarse (no todos: el conserje no
  registra a todos), con algunas limpiezas sin turno y un par de arreglos, para la línea de tiempo y el análisis.

El pasado no se puede escribir por la aplicación: los triggers de la base (RN-RES-01 y RN-RES-02) rechazan cobros en
guardias cerradas y recalculan el arqueo con la hora actual. Por eso el script corre como dueño de las tablas y, solo
en su transacción, con session_replication_role = replica (no se disparan los triggers). Los datos se arman con las
mismas reglas que esos triggers controlan: cada cobro en la guardia abierta a la hora del cobro, el arqueo con el
total del sistema de sus cobros más el fondo, la diferencia y su categoría (RN-DER-03). Si el establecimiento ya tiene
turnos, no hace nada.

Uso (Docker): docker compose run --rm admin scripts.cargar_historial
"""

import asyncio
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.inquilino import CLAVE
from app.models.arqueo import ArqueoCaja
from app.models.articulo import Articulo
from app.models.calificacion import Calificacion
from app.models.categoria import CategoriaHabitacion
from app.models.cliente_perdido import ESPERA, PRECIO, SIN_LUGAR, ClientePerdido
from app.models.configuracion import ConfiguracionCaja
from app.models.consumo import Consumo
from app.models.establecimiento import Establecimiento
from app.models.evento_habitacion import COBRO, LIBERAR, MANUAL, TURNO, EventoHabitacion
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.novedad import Novedad
from app.models.operacion import (
    APERTURA,
    CIERRE,
    PRENDAS,
    RESUELTO,
    Arreglo,
    RopaConteo,
    RopaMovimiento,
    TrasladoTurno,
    Traspaso,
)
from app.models.operador import ROL_OPERADOR, Operador
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services import franjas, sellos
from app.services.billing_service import calcular_sobreturno
from app.services.caja import clasificar_diferencia
from app.services.liquidacion import con_zona
from app.services.ropa import cuenta_por_estado

FRANJAS = (6, 14, 22)
# Llegadas por hora (hora local) en un día promedio: la noche concentra la demanda y la tarde tiene su pico.
# fmt: off
LLEGADAS_POR_HORA = [2.2, 1.9, 1.4, 0.9, 0.5, 0.35, 0.25, 0.35, 0.5, 0.7, 0.85, 1.0,
                     1.2, 1.4, 1.55, 1.6, 1.55, 1.35, 1.2, 1.2, 1.45, 1.9, 2.4, 2.6]
# fmt: on
# Peso de cada noche de la semana (lunes = 0). La madrugada cuenta como la noche del día anterior.
PESO_DIA = [0.72, 0.74, 0.84, 0.95, 1.32, 1.55, 1.02]
# Preferencia de los clientes por categoría (las que no figuran, 0,2).
PREFERENCIA = {"simple": 0.6, "especial": 0.26, "vip": 0.14, "suite": 0.3}
# Probabilidad de quedarse más que la estadía base, por categoría (las que no figuran, 0,3).
SE_QUEDA_MAS = {"simple": 0.2, "especial": 0.45, "vip": 0.15, "suite": 0.3}
MEDIOS = (("EFECTIVO", 0.55), ("POSNET", 0.26), ("MERCADO_PAGO", 0.19))
TIPOS_CLIENTE = (("Auto", 0.7), ("Moto", 0.2), ("Peaton", 0.1))
# Probabilidad de que un arqueo tenga diferencia, por posición del conserje (el segundo, más desprolijo).
ERROR_ARQUEO = (0.05, 0.26, 0.1)
FALTANTES = (500, 1000, 1000, 1500, 2000, 3000, 5000)
SOBRANTES = (200, 500, 500, 1000)
# Días de stock que quedan al final, en rotación: algunos artículos quedan al borde de agotarse.
COBERTURA_DIAS = (1.5, 4, 9, 14, 22, 35)
# Parte de los clientes que se fueron que el conserje llega a registrar, y parte de los que entran que preguntan el
# precio y se van.
REGISTRADOS = 0.8
SE_VAN_POR_PRECIO = 0.012
# Limpiezas sin turno antes (repasos o estadías sin registrar), la mayoría del conserje más desprolijo.
LIMPIEZAS_SIN_TURNO = 7


@dataclass
class _Guardia:
    inicio: datetime
    fin: datetime
    operador: Operador
    modelo: Guardia | None = None
    pagos: list[Pago] = field(default_factory=list)


def _poisson(rng: random.Random, media: float) -> int:
    if media <= 0:
        return 0
    limite, k, p = math.exp(-media), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limite:
            return k
        k += 1


def _elegir(rng: random.Random, opciones):
    valores, pesos = zip(*opciones, strict=True)
    return rng.choices(valores, weights=pesos)[0]


def inicio_de_franja(momento: datetime, zona: ZoneInfo) -> datetime:
    """Comienzo (hora local) de la franja de 8 h que contiene `momento`."""
    local = momento.astimezone(zona)
    hora = max((h for h in FRANJAS if h <= local.hour), default=None)
    if hora is None:
        return (local - timedelta(days=1)).replace(hour=FRANJAS[-1], minute=0, second=0, microsecond=0)
    return local.replace(hour=hora, minute=0, second=0, microsecond=0)


def _duracion(rng: random.Random, tarifa: Tarifa, nocturno: bool, es_premium: bool, se_queda_mas: float) -> int:
    base = tarifa.estadia_base_min
    if nocturno and (tarifa.tope is not None or es_premium) and rng.random() < 0.12:
        return rng.randint(6 * 60, 9 * 60)  # pernocte
    if rng.random() < 0.012:
        return rng.randint(3, 9)  # turno relámpago (se abrió y se cerró enseguida)
    if rng.random() < se_queda_mas:
        return base + min(int(rng.expovariate(1 / 40)) + 1, 240)
    return int(base * rng.uniform(0.55, 1.0))


async def generar_historial(
    db: AsyncSession,
    dias: int = 60,
    hasta: datetime | None = None,
    semilla: int = 7,
    intensidad: float = 1.0,
    habitacion_poco_usada: int | None = None,
    arreglos: int = 0,
) -> dict[str, int]:
    """Genera `dias` días de operación que terminan en `hasta` (por defecto, el comienzo de la franja actual).

    La sesión debe estar asociada a un establecimiento (session.info). Devuelve cuántas filas creó de cada tipo.
    `arreglos` habitaciones pasan unas horas en mantenimiento durante la última semana.
    """
    zona = ZoneInfo(settings.ZONA_HORARIA)
    rng = random.Random(semilla)
    # Lo que se agrega por encima de la operación usa su propia secuencia: no cambia los turnos que salen de `semilla`.
    rng_extra = random.Random(semilla + 1)
    fin_periodo = inicio_de_franja(hasta or datetime.now(UTC), zona)
    inicio_periodo = fin_periodo - timedelta(days=dias)

    conserjes = list(
        (
            await db.execute(
                select(Operador)
                .where(Operador.rol == ROL_OPERADOR, Operador.activo.is_(True))
                .order_by(Operador.usuario)
            )
        ).scalars()
    )
    habitaciones = list(
        (
            await db.execute(
                select(Habitacion)
                .where(Habitacion.activa.is_(True), Habitacion.estado != "Mantenimiento")
                .order_by(Habitacion.numero)
            )
        ).scalars()
    )
    # Cada turno se liquida con lo que regía cuando entró: la tarifa especial de esa hora o la general.
    tarifario = await franjas.tarifario(db)
    tarifas = tarifario.generales
    categorias = {
        c.id: c
        for c in (await db.execute(select(CategoriaHabitacion).where(CategoriaHabitacion.activa.is_(True)))).scalars()
    }
    articulos = list(
        (await db.execute(select(Articulo).where(Articulo.activo.is_(True)).order_by(Articulo.id))).scalars()
    )
    if not conserjes or not habitaciones or not tarifas:
        return {}
    configuracion = await db.get(ConfiguracionCaja, db.info.get(CLAVE))
    fondo = Decimal(configuracion.fondo_cambio) if configuracion else settings.FONDO_INICIAL_CAJA

    if db.get_bind().dialect.name == "postgresql":
        # Solo en esta transacción y como dueño de las tablas: ver la explicación del módulo.
        await db.execute(text("SET LOCAL session_replication_role = replica"))

    # Guardias de 8 h, alternando conserjes.
    guardias: list[_Guardia] = []
    momento = inicio_periodo
    while momento < fin_periodo:
        guardias.append(_Guardia(momento, momento + timedelta(hours=8), conserjes[len(guardias) % len(conserjes)]))
        momento += timedelta(hours=8)
    for g in guardias:
        g.modelo = Guardia(
            operador_id=g.operador.id,
            franja=f"{g.inicio.hour:02d}:00",
            fondo_inicial=fondo,
            abierta_en=(g.inicio - timedelta(minutes=rng.randint(2, 15))).astimezone(UTC),
            cerrada_en=(g.fin + timedelta(minutes=rng.randint(2, 12))).astimezone(UTC),
            estado="Cerrada",
        )
        db.add(g.modelo)
    await db.flush()

    def guardia_en(instante: datetime) -> _Guardia:
        indice = int((instante - inicio_periodo).total_seconds() // (8 * 3600))
        return guardias[min(max(indice, 0), len(guardias) - 1)]

    # Llegadas hora por hora.
    llegadas: list[datetime] = []
    hora = inicio_periodo
    total_horas = dias * 24
    ruido_dia: dict[object, float] = {}
    for paso in range(total_horas):
        noche_de = (hora - timedelta(hours=6)).date()  # la madrugada es la noche del día anterior
        if noche_de not in ruido_dia:
            ruido_dia[noche_de] = rng.lognormvariate(0, 0.12)
        tendencia = 0.9 + 0.2 * paso / total_horas
        media = LLEGADAS_POR_HORA[hora.hour] * PESO_DIA[noche_de.weekday()] * tendencia * ruido_dia[noche_de]
        for _ in range(_poisson(rng, media * intensidad)):
            llegadas.append(hora + timedelta(minutes=rng.uniform(0, 59.9)))
        hora += timedelta(hours=1)
    llegadas.sort()

    libre_desde = {h.id: inicio_periodo for h in habitaciones}
    # Tramos en los que cada habitación estuvo ocupada o en limpieza: en los huecos caben las limpiezas sin turno.
    tomada: dict[int, list[tuple[datetime, datetime]]] = {h.id: [] for h in habitaciones}
    pendientes_arreglo = []
    for i in range(arreglos):
        h = habitaciones[(i * 5 + 3) % len(habitaciones)]
        desde_arreglo = fin_periodo - timedelta(days=2 + i * 2, hours=rng_extra.randint(1, 9))
        pendientes_arreglo.append((desde_arreglo, h, timedelta(hours=rng_extra.randint(4, 9))))
    por_categoria: dict[int, list[Habitacion]] = {}
    for h in habitaciones:
        if h.categoria_id in tarifas:
            por_categoria.setdefault(h.categoria_id, []).append(h)
    opciones_categoria = [
        (cid, PREFERENCIA.get(categorias[cid].nombre.lower(), 0.2) if cid in categorias else 0.2)
        for cid in por_categoria
    ]
    precio = {cid: Decimal(tarifas[cid].tarifa_base) for cid in por_categoria}
    premium = max(precio, key=precio.get) if len(precio) > 1 else None
    pesos_articulo = [1.6 if i < 3 else 0.4 + (i * 37 % 10) / 8 for i in range(len(articulos))]
    consumido = {a.id: 0 for a in articulos}
    contador = {
        "turnos": 0,
        "consumos": 0,
        "pagos": 0,
        "guardias": len(guardias),
        "arqueos": 0,
        "perdidos": 0,
        "registrados": 0,
    }

    def perdido(momento: datetime, motivo: str, categoria_id: int | None) -> None:
        guardia = guardia_en(momento)
        db.add(
            ClientePerdido(
                motivo=motivo,
                categoria_id=categoria_id,
                operador_id=guardia.operador.id,
                guardia_id=guardia.modelo.id,
                creado_en=momento.astimezone(UTC),
            )
        )
        contador["registrados"] += 1

    def evento(habitacion_id, anterior, nuevo, origen, momento, turno_id=None, operador=None) -> None:
        db.add(
            EventoHabitacion(
                habitacion_id=habitacion_id,
                estado_anterior=anterior,
                estado_nuevo=nuevo,
                origen=origen,
                turno_id=turno_id,
                operador_id=(operador or guardia_en(momento).operador).id,
                creado_en=momento.astimezone(UTC),
            )
        )

    for llegada in llegadas:
        # Un arreglo que empieza: la habitación espera a quedar libre y no se usa hasta que termine.
        while pendientes_arreglo and min(pendientes_arreglo, key=lambda p: p[0])[0] <= llegada:
            arreglo = min(pendientes_arreglo, key=lambda p: p[0])
            pendientes_arreglo.remove(arreglo)
            _, h, duracion_arreglo = arreglo
            desde_arreglo = max(libre_desde[h.id], arreglo[0])
            libre_desde[h.id] = desde_arreglo + duracion_arreglo
            evento(h.id, "Libre", "Mantenimiento", MANUAL, desde_arreglo)
            evento(h.id, "Mantenimiento", "Libre", MANUAL, min(libre_desde[h.id], fin_periodo))
            tomada[h.id].append((desde_arreglo, libre_desde[h.id]))
        nocturno = llegada.hour >= 21 or llegada.hour < 4
        preferida = _elegir(rng, opciones_categoria)
        if premium is not None and nocturno and llegada.weekday() in (4, 5) and rng.random() < 0.4:
            preferida = premium
        candidatas = [preferida] + sorted((c for c in por_categoria if c != preferida), key=lambda c: precio[c])
        elegida = None
        for categoria_id in candidatas:
            libres = [h for h in por_categoria[categoria_id] if libre_desde[h.id] <= llegada]
            if habitacion_poco_usada is not None and len(libres) > 1 and rng.random() < 0.8:
                libres = [h for h in libres if h.numero != habitacion_poco_usada] or libres
            if libres:
                elegida = rng.choice(libres)
                break
            if categoria_id == preferida and rng.random() < 0.45:
                break  # el cliente no acepta otra categoría y se va
        if elegida is None:
            contador["perdidos"] += 1
            if rng_extra.random() < REGISTRADOS:
                perdido(llegada, ESPERA if rng_extra.random() < 0.3 else SIN_LUGAR, preferida)
            continue
        if rng_extra.random() < SE_VAN_POR_PRECIO:
            perdido(llegada + timedelta(minutes=1), PRECIO, preferida)

        tarifa = tarifario.en(elegida.categoria_id, llegada).tarifa
        nombre = categorias[elegida.categoria_id].nombre.lower() if elegida.categoria_id in categorias else ""
        minutos = _duracion(rng, tarifa, nocturno, elegida.categoria_id == premium, SE_QUEDA_MAS.get(nombre, 0.3))
        salida = llegada + timedelta(minutes=minutos)
        if salida >= fin_periodo:
            continue  # quedaría en curso: el historial termina con todas las habitaciones libres
        libre_desde[elegida.id] = salida + timedelta(minutes=rng.randint(18, 40))  # limpieza
        tomada[elegida.id].append((llegada, libre_desde[elegida.id]))

        apertura, cierre = guardia_en(llegada), guardia_en(salida)
        turno_id = uuid.uuid4()
        total_consumos = Decimal("0")
        for _ in range(_poisson(rng, 0.85 * (1.4 if minutos > 180 else 1.0)) if minutos > 15 and articulos else 0):
            articulo = rng.choices(articulos, weights=pesos_articulo)[0]
            cantidad = 1 if rng.random() < 0.8 else 2
            subtotal = Decimal(articulo.precio_unitario) * cantidad
            cuando = llegada + timedelta(minutes=rng.uniform(5, max(6, minutos - 5)))
            db.add(
                Consumo(
                    turno_id=turno_id,
                    articulo_id=articulo.id,
                    cantidad=cantidad,
                    precio_unitario=articulo.precio_unitario,
                    subtotal=subtotal,
                    created_at=cuando.astimezone(UTC),
                    operador_id=guardia_en(cuando).operador.id,
                )
            )
            consumido[articulo.id] += cantidad
            total_consumos += subtotal
            contador["consumos"] += 1
        sobreturno = calcular_sobreturno(timedelta(minutes=minutos), tarifa.parametros())
        total = Decimal(tarifa.tarifa_base) + sobreturno + total_consumos
        db.add(
            Turno(
                id=turno_id,
                habitacion_id=elegida.id,
                tarifa_id=tarifa.id,
                tipo_cliente=_elegir(rng, TIPOS_CLIENTE),
                hora_inicio=llegada.astimezone(UTC),
                hora_fin=salida.astimezone(UTC),
                tarifa_base=tarifa.tarifa_base,
                total_sobreturno=sobreturno,
                total_consumos=total_consumos,
                total_general=total,
                estado="FINALIZADO",
                operador_apertura_id=apertura.operador.id,
                guardia_apertura_id=apertura.modelo.id,
                operador_cierre_id=cierre.operador.id,
            )
        )
        medio = _elegir(rng, MEDIOS)
        referencia = (
            None if medio == "EFECTIVO" else f"{'POS' if medio == 'POSNET' else 'MP'}-{rng.randint(10**6, 10**7)}"
        )
        pago = Pago(
            turno_id=turno_id,
            monto=total,
            medio_pago=medio,
            comprobante_referencia=referencia,
            created_at=salida.astimezone(UTC),
            operador_id=cierre.operador.id,
            guardia_id=cierre.modelo.id,
        )
        db.add(pago)
        cierre.pagos.append(pago)
        contador["turnos"] += 1
        contador["pagos"] += 1
        evento(elegida.id, "Libre", "Ocupada", TURNO, llegada, turno_id, apertura.operador)
        evento(elegida.id, "Ocupada", "En Limpieza", COBRO, salida, turno_id, cierre.operador)
        evento(elegida.id, "En Limpieza", "Libre", LIBERAR, min(libre_desde[elegida.id], fin_periodo))

    # Limpiezas sin un turno antes, en huecos reales de las últimas semanas.
    huecos = []
    for habitacion_id, tramos in tomada.items():
        ordenados = sorted(tramos)
        for (_, fin_tramo), (inicio_siguiente, _) in zip(ordenados, ordenados[1:], strict=False):
            if inicio_siguiente - fin_tramo >= timedelta(minutes=50) and fin_tramo >= fin_periodo - timedelta(days=25):
                huecos.append((habitacion_id, fin_tramo))
    for habitacion_id, fin_tramo in rng_extra.sample(huecos, min(LIMPIEZAS_SIN_TURNO, len(huecos))):
        inicio_limpieza = fin_tramo + timedelta(minutes=rng_extra.randint(3, 12))
        responsable = conserjes[min(1, len(conserjes) - 1)] if rng_extra.random() < 0.8 else None
        evento(habitacion_id, "Libre", "En Limpieza", MANUAL, inicio_limpieza, operador=responsable)
        evento(
            habitacion_id,
            "En Limpieza",
            "Libre",
            LIBERAR,
            inicio_limpieza + timedelta(minutes=rng_extra.randint(14, 24)),
            operador=responsable,
        )
    await db.flush()

    # Arqueos: el total del sistema sale de los cobros de cada guardia más el fondo (como calcular_arqueo).
    posicion = {c.id: i for i, c in enumerate(conserjes)}
    ultima_semana = fin_periodo - timedelta(days=7)
    faltante_grande_puesto = False
    for g in reversed(guardias):
        efectivo = fondo + sum((Decimal(p.monto) for p in g.pagos if p.medio_pago == "EFECTIVO"), Decimal("0"))
        posnet = sum((Decimal(p.monto) for p in g.pagos if p.medio_pago == "POSNET"), Decimal("0"))
        mercado_pago = sum((Decimal(p.monto) for p in g.pagos if p.medio_pago == "MERCADO_PAGO"), Decimal("0"))
        indice = posicion[g.operador.id]
        desvio = Decimal("0")
        if indice == 1 and not faltante_grande_puesto and g.inicio < ultima_semana and efectivo > 20000:
            desvio = Decimal("-12000")  # el faltante fuera de lo común que tiene que saltar en las alertas
            faltante_grande_puesto = True
        elif rng.random() < ERROR_ARQUEO[min(indice, len(ERROR_ARQUEO) - 1)]:
            desvio = Decimal(-rng.choice(FALTANTES) if rng.random() < 0.8 else rng.choice(SOBRANTES))
        declarado_efectivo = max(efectivo + desvio, Decimal("0"))
        declarado = declarado_efectivo + posnet + mercado_pago
        sistema = efectivo + posnet + mercado_pago
        diferencia, categoria = clasificar_diferencia(declarado, sistema)
        db.add(
            ArqueoCaja(
                guardia_id=g.modelo.id,
                operador_id=g.operador.id,
                confirmado_por_id=g.operador.id,
                declarado_efectivo=declarado_efectivo,
                declarado_posnet=posnet,
                declarado_mercado_pago=mercado_pago,
                total_declarado=declarado,
                sistema_efectivo=efectivo,
                sistema_posnet=posnet,
                sistema_mercado_pago=mercado_pago,
                total_sistema=sistema,
                diferencia=diferencia,
                categoria=categoria,
                confirmado_en=g.modelo.cerrada_en,
            )
        )
        contador["arqueos"] += 1
    await db.flush()
    # Comprobantes verificables: la cadena de huellas, en orden, como si cada arqueo se hubiera sellado al confirmarse.
    await sellos.sellar_pendientes(db)

    # Stock final: cada artículo queda con unos días de cobertura según lo que se vendió (algunos casi agotados).
    for i, articulo in enumerate(articulos):
        por_dia = consumido[articulo.id] / dias
        articulo.stock_actual = max(0, round(por_dia * COBERTURA_DIAS[i % len(COBERTURA_DIAS)]))
    await db.commit()
    return contador


# Opiniones de ejemplo: cuántos califican, con qué puntajes y qué marcan los que no quedaron conformes. En la habitación
# poco usada falla el aire: es lo mismo que cuenta su novedad y lo que detecta la inteligencia.
CALIFICAN = 0.22
PUNTAJES = ((5, 0.56), (4, 0.27), (3, 0.1), (2, 0.05), (1, 0.02))
PUNTAJES_CON_FALLA = ((4, 0.2), (3, 0.34), (2, 0.3), (1, 0.16))
PROBLEMAS_COMUNES = ((1, 0.28), (2, 0.24), (8, 0.2), (16, 0.16), (32, 0.12))
AIRE_Y_RUIDO = 4 | 2


async def agregar_opiniones(db: AsyncSession, semilla: int, habitacion_poco_usada: int | None = None) -> int:
    """Calificaciones de los turnos ya cobrados. Como el resto del historial, va como dueño y con replica: el trigger no
    dejaría calificar estadías viejas."""
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SET LOCAL session_replication_role = replica"))
    rng = random.Random(semilla + 2)
    numeros = {h.id: h.numero for h in (await db.execute(select(Habitacion))).scalars()}
    turnos = (
        await db.execute(
            select(Turno.id, Turno.habitacion_id, Turno.hora_fin)
            .where(Turno.estado == "FINALIZADO")
            .order_by(Turno.hora_fin, Turno.id)
        )
    ).all()
    cantidad = 0
    for turno_id, habitacion_id, hora_fin in turnos:
        if rng.random() >= CALIFICAN:
            continue
        con_falla = habitacion_poco_usada is not None and numeros.get(habitacion_id) == habitacion_poco_usada
        puntaje = _elegir(rng, PUNTAJES_CON_FALLA if con_falla else PUNTAJES)
        problemas = 0
        if con_falla and puntaje <= 3:
            problemas = AIRE_Y_RUIDO if rng.random() < 0.6 else 4
        elif puntaje <= 3:
            problemas = _elegir(rng, PROBLEMAS_COMUNES)
        db.add(
            Calificacion(
                turno_id=turno_id,
                habitacion_id=habitacion_id,
                puntaje=puntaje,
                problemas=problemas,
                creado_en=hora_fin + timedelta(minutes=rng.randint(1, 30)),
            )
        )
        cantidad += 1
    return cantidad


# Operación de ejemplo (migración 016): en la habitación poco usada vuelve a fallar el aire; es lo mismo que cuenta su
# novedad, lo que marcan sus clientes y lo que detecta la inteligencia. Los faltantes de ropa son de un solo conserje.
DIAS_DE_RECUENTOS = 30
ROPA_POR_HABITACION = {"TOALLAS": 6, "SABANAS": 4}
PIERDE_ROPA = 0.16
# Días atrás, habitación (None: la poco usada), tipo, rubro, descripción, quién lo reparó, qué se hizo y costo.
ARREGLOS_DEMO = (
    (27, None, "FALLA", "AIRE", "Hace ruido y enfría poco", "Técnico de aire", "Se ajustó el forzador", 38000),
    (19, None, "FALLA", "AIRE", "Volvió el ruido", "Técnico de aire", "Se cambió el capacitor", 52000),
    (12, 3, "FALLA", "PLOMERIA", "Pierde la canilla del baño", "Plomero", "Se cambió el cuerito", 9500),
    (9, 8, "MANTENIMIENTO", "AIRE", "Limpieza de filtros", "Personal propio", None, None),
    (5, 11, "FALLA", "TV", "No funciona el control remoto", "Personal propio", "Control nuevo", 7800),
)
ARREGLOS_ABIERTOS_DEMO = ((1, None, "FALLA", "AIRE", "Hace ruido otra vez: los clientes piden cambiarse"),)
TRASLADOS_DEMO = 3


async def _foto_historica(turnos: list, momento: datetime, numeros: dict[int, int], base: dict[int, int]) -> dict:
    """El traspaso de una guardia pasada: quiénes estaban en curso a esa hora."""
    en_curso = []
    for habitacion_id, tarifa_id, inicio, fin in turnos:
        if con_zona(inicio) <= momento < con_zona(fin):
            lleva = round((momento - con_zona(inicio)).total_seconds() / 60)
            minimo = base.get(tarifa_id, 120)
            en_curso.append(
                {
                    "numero": numeros.get(habitacion_id),
                    "lleva_min": lleva,
                    "base_min": minimo,
                    "excedido": lleva > minimo,
                }
            )
    en_curso.sort(key=lambda t: t["numero"] or 0)
    return {"turnos": en_curso, "pedidos": [], "limpieza": [], "mantenimiento": [], "arreglos": [], "novedades": []}


async def agregar_operacion(db: AsyncSession, semilla: int, habitacion_poco_usada: int | None = None) -> dict[str, int]:
    """Recuentos y traspasos de cada cambio de guardia, movimientos de ropa, arreglos y traslados.

    Como el resto del historial, va como dueño y con replica: los triggers exigen una guardia abierta y la hora actual.
    """
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SET LOCAL session_replication_role = replica"))
    rng = random.Random(semilla + 3)
    ahora = datetime.now(UTC)
    habitaciones = list((await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)))).scalars())
    numeros = {h.id: h.numero for h in habitaciones}
    por_numero = {h.numero: h for h in habitaciones}
    operadores = list(
        (
            await db.execute(
                select(Operador)
                .where(Operador.rol == ROL_OPERADOR, Operador.activo.is_(True))
                .order_by(Operador.usuario)
            )
        ).scalars()
    )
    nombres = {o.id: o.nombre_visible for o in operadores}
    # El mismo conserje que tiene más faltantes en la caja. Con uno solo no hay con quién comparar: no pierde nada.
    desprolijo = operadores[1].id if len(operadores) > 1 else None
    desde = ahora - timedelta(days=DIAS_DE_RECUENTOS)
    guardias = list(
        (
            await db.execute(
                select(Guardia)
                .where(Guardia.estado == "Cerrada", Guardia.abierta_en >= desde)
                .order_by(Guardia.abierta_en, Guardia.id)
            )
        ).scalars()
    )
    tarifas = dict((await db.execute(select(Tarifa.id, Tarifa.estadia_base_min))).all())
    turnos = (
        await db.execute(
            select(Turno.habitacion_id, Turno.tarifa_id, Turno.hora_inicio, Turno.hora_fin).where(
                Turno.hora_fin.is_not(None), Turno.hora_fin >= desde
            )
        )
    ).all()

    hay = {prenda: cantidad * len(habitaciones) for prenda, cantidad in ROPA_POR_HABITACION.items()}
    lavando = dict.fromkeys(hay, 0)
    # Cada motel cuenta a su manera (migración 017): separado por estado o todo junto.
    por_estado = await cuenta_por_estado(db)
    cantidades = {"recuentos": 0, "movimientos": 0, "traspasos": 0, "arreglos": 0, "traslados": 0}
    anterior: Guardia | None = None
    ultimo: dict[str, int] = {}

    def conteo(guardia: Guardia, momento_conteo: str, cuando: datetime) -> list[dict]:
        filas = []
        for prenda, total in hay.items():
            en_habitaciones = min(rng.randint(len(habitaciones), len(habitaciones) * 3 // 2), total)
            sucias = min(rng.randint(4, 16), total - en_habitaciones)
            fila = RopaConteo(
                guardia_id=guardia.id,
                operador_id=guardia.operador_id,
                momento=momento_conteo,
                prenda=prenda,
                limpias=total - en_habitaciones - sucias if por_estado else None,
                sucias=sucias if por_estado else None,
                en_habitaciones=en_habitaciones if por_estado else None,
                total=total,
                creado_en=cuando,
            )
            db.add(fila)
            cantidades["recuentos"] += 1
            filas.append(fila)
        return [
            {
                "prenda": f.prenda,
                "etiqueta": PRENDAS[f.prenda],
                "limpias": f.limpias,
                "sucias": f.sucias,
                "en_habitaciones": f.en_habitaciones,
                "total": f.total,
            }
            for f in filas
        ]

    dejada: list[dict] = []
    for indice, guardia in enumerate(guardias):
        apertura = con_zona(guardia.abierta_en) + timedelta(minutes=3)
        recibida = conteo(guardia, APERTURA, apertura)
        foto = await _foto_historica(turnos, apertura, numeros, tarifas)
        db.add(
            Traspaso(
                guardia_saliente_id=anterior.id if anterior else None,
                guardia_id=guardia.id,
                operador_id=guardia.operador_id,
                resumen={
                    **foto,
                    "ropa_dejada": [
                        {**d, "esperado": d["total"], "contado_por": nombres.get(anterior.operador_id, "—")}
                        for d in dejada
                    ]
                    if anterior
                    else [],
                    "ropa_recibida": [
                        {
                            "prenda": r["prenda"],
                            "etiqueta": r["etiqueta"],
                            "total": r["total"],
                            "esperado": ultimo.get(r["prenda"]),
                            "diferencia": 0 if r["prenda"] in ultimo else None,
                        }
                        for r in recibida
                    ],
                },
                creado_en=apertura,
            )
        )
        cantidades["traspasos"] += 1

        # Lo que pasa durante la guardia: la lavandería retira y devuelve, y alguna toalla se rompe.
        medio = apertura + (con_zona(guardia.cerrada_en) - apertura) / 2
        for prenda in hay:
            cantidad, tipo = 0, None
            if lavando[prenda]:
                if rng.random() < 0.5:
                    cantidad, tipo, lavando[prenda] = lavando[prenda], "LAVANDERIA_VUELVE", 0
                    hay[prenda] += cantidad
            elif rng.random() < 0.14:
                cantidad, tipo = max(hay[prenda] // rng.randint(4, 6), 1), "LAVANDERIA_SALE"
                lavando[prenda] = cantidad
                hay[prenda] -= cantidad
            elif rng.random() < 0.02:
                cantidad, tipo = 1, "BAJA"
                hay[prenda] -= 1
            if tipo:
                db.add(
                    RopaMovimiento(
                        guardia_id=guardia.id,
                        operador_id=guardia.operador_id,
                        prenda=prenda,
                        tipo=tipo,
                        cantidad=cantidad,
                        creado_en=medio,
                    )
                )
                cantidades["movimientos"] += 1
        minimo_toallas = ROPA_POR_HABITACION["TOALLAS"] * len(habitaciones) // 2
        if guardia.operador_id == desprolijo and rng.random() < PIERDE_ROPA and hay["TOALLAS"] > minimo_toallas:
            hay["TOALLAS"] -= rng.choice((1, 1, 2))
        # En el historial una guardia a veces abre antes de que se cierre la anterior: el recuento va primero igual.
        cierre = con_zona(guardia.cerrada_en) - timedelta(minutes=5)
        if indice + 1 < len(guardias):
            cierre = min(cierre, con_zona(guardias[indice + 1].abierta_en) - timedelta(minutes=1))
        dejada = conteo(guardia, CIERRE, cierre)
        ultimo = dict(hay)
        anterior = guardia

    def habitacion_de(numero: int | None) -> Habitacion | None:
        return por_numero.get(habitacion_poco_usada if numero is None else numero)

    for dias, numero, tipo, rubro, descripcion, reparo, trabajo, costo in ARREGLOS_DEMO:
        habitacion = habitacion_de(numero)
        if habitacion is None or not operadores:
            continue
        abierto = ahora - timedelta(days=dias, hours=rng.randint(1, 9))
        db.add(
            Arreglo(
                habitacion_id=habitacion.id,
                tipo=tipo,
                rubro=rubro,
                descripcion=descripcion,
                estado=RESUELTO,
                abierto_por_id=rng.choice(operadores).id,
                abierto_en=abierto,
                resuelto_por_id=rng.choice(operadores).id,
                resuelto_en=abierto + timedelta(hours=rng.randint(5, 30)),
                reparado_por=reparo,
                trabajo=trabajo,
                costo=Decimal(costo) if costo else None,
            )
        )
        cantidades["arreglos"] += 1
    for dias, numero, tipo, rubro, descripcion in ARREGLOS_ABIERTOS_DEMO:
        habitacion = habitacion_de(numero)
        if habitacion is None or not operadores:
            continue
        db.add(
            Arreglo(
                habitacion_id=habitacion.id,
                tipo=tipo,
                rubro=rubro,
                descripcion=descripcion,
                abierto_por_id=rng.choice(operadores).id,
                abierto_en=ahora - timedelta(days=dias, hours=rng.randint(1, 9)),
            )
        )
        cantidades["arreglos"] += 1

    # Clientes que pidieron irse de la habitación poco usada. Se eligen turnos que pudieron empezar en ella.
    poco_usada = por_numero.get(habitacion_poco_usada) if habitacion_poco_usada else None
    if poco_usada is not None:
        propios = [
            (con_zona(i), con_zona(f))
            for h, _, i, f in turnos
            if h == poco_usada.id
        ]
        candidatos = (
            await db.execute(
                select(Turno)
                .where(
                    Turno.estado == "FINALIZADO",
                    Turno.habitacion_id != poco_usada.id,
                    Turno.hora_inicio >= ahora - timedelta(days=20),
                    Turno.operador_apertura_id.is_not(None),
                    Turno.guardia_apertura_id.is_not(None),
                )
                .order_by(Turno.hora_inicio, Turno.id)
            )
        ).scalars()
        libres = [
            t
            for t in candidatos
            if con_zona(t.hora_fin) - con_zona(t.hora_inicio) > timedelta(minutes=40)
            and not any(
                inicio < con_zona(t.hora_inicio) + timedelta(minutes=30) and fin > con_zona(t.hora_inicio)
                for inicio, fin in propios
            )
        ]
        for turno in rng.sample(libres, min(TRASLADOS_DEMO, len(libres))):
            db.add(
                TrasladoTurno(
                    turno_id=turno.id,
                    desde_habitacion_id=poco_usada.id,
                    hacia_habitacion_id=turno.habitacion_id,
                    motivo="FALLA",
                    operador_id=turno.operador_apertura_id,
                    guardia_id=turno.guardia_apertura_id,
                    creado_en=con_zona(turno.hora_inicio) + timedelta(minutes=25),
                )
            )
            cantidades["traslados"] += 1
    return cantidades


# Artículos que se suman al catálogo de Motel C.C. para que el inventario tenga variedad.
ARTICULOS_EXTRA = {
    "motelcc": [
        ("PRE-001", "Preservativos x3", 2500, "Cuidado personal"),
        ("BEB-004", "Gaseosa cola 500 ml", 1500, "Bebidas"),
        ("BEB-005", "Espumante 750 ml", 9000, "Bebidas"),
        ("SNA-002", "Chocolate con almendras", 1800, "Snacks"),
        ("SNA-003", "Maní salado 120 g", 1100, "Snacks"),
        ("HIG-001", "Kit de higiene", 1600, "Cuidado personal"),
    ],
}
DEMO = (("motelcc", 60, 1.5, 6, 2), ("luna", 30, 0.7, None, 1))

# Novedades de guardia de ejemplo (migración 009): horas antes del fin del historial, usuario, texto, importante y
# número de habitación. La de la 6 explica por qué esa habitación se usa menos (la detecta la inteligencia).
NOVEDADES_DEMO = {
    "motelcc": [
        (
            20,
            "conserje2",
            "La 6: el aire hace ruido y los clientes piden cambiarse. Hay que llamar al técnico.",
            True,
            6,
        ),
        (11, "conserje1", "Quedan pocas aguas en el depósito; ya le avisé al proveedor.", False, None),
        (4, "conserje2", "Se rompió el control remoto de la 11, quedó uno de repuesto en recepción.", False, 11),
    ],
    "luna": [(6, "conserje1", "Cambiar las sábanas del depósito: la lavandería entrega el jueves.", False, None)],
}


async def _novedades_demo(db: AsyncSession, codigo: str, hasta: datetime) -> None:
    """Novedades con su hora en el pasado. El trigger pone la hora actual, por eso van con replica, como el resto."""
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("SET LOCAL session_replication_role = replica"))
    usuarios = {o.usuario: o.id for o in (await db.execute(select(Operador))).scalars()}
    numeros = {h.numero: h.id for h in (await db.execute(select(Habitacion))).scalars()}
    for horas, usuario, texto, importante, numero in NOVEDADES_DEMO.get(codigo, []):
        momento = (hasta - timedelta(hours=horas)).astimezone(UTC)
        guardia = (
            (
                await db.execute(
                    select(Guardia).where(
                        Guardia.operador_id == usuarios.get(usuario),
                        Guardia.abierta_en <= momento,
                        Guardia.cerrada_en > momento,
                    )
                )
            )
            .scalars()
            .first()
        )
        db.add(
            Novedad(
                operador_id=usuarios[usuario],
                guardia_id=guardia.id if guardia else None,
                habitacion_id=numeros.get(numero),
                texto=texto,
                importante=importante,
                creado_en=momento,
            )
        )
    await db.commit()


async def cargar() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for codigo, dias, intensidad, poco_usada, arreglos in DEMO:
            async with sesiones() as db:
                establecimiento = (
                    (await db.execute(select(Establecimiento).where(Establecimiento.codigo == codigo)))
                    .scalars()
                    .first()
                )
            if establecimiento is None:
                print(f"{codigo}: no existe, se omite.")
                continue
            async with sesiones(info={CLAVE: establecimiento.id}) as db:
                if (await db.execute(select(Turno.id).limit(1))).first():
                    print(f"{codigo}: ya tiene turnos, no se agrega historial.")
                    if not (await db.execute(select(Calificacion.id).limit(1))).first():
                        opiniones = await agregar_opiniones(db, 7, poco_usada)
                        await db.commit()
                        print(f"{codigo}: {opiniones} opiniones de clientes agregadas.")
                    if not (await db.execute(select(RopaConteo.id).limit(1))).first():
                        operacion = await agregar_operacion(db, 7, poco_usada)
                        await db.commit()
                        print(f"{codigo}: operación diaria de ejemplo agregada: {operacion}.")
                    continue
                existentes = set((await db.execute(select(Articulo.codigo))).scalars())
                for cod, descripcion, precio, rubro in ARTICULOS_EXTRA.get(codigo, []):
                    if cod not in existentes:
                        db.add(
                            Articulo(
                                codigo=cod,
                                descripcion=descripcion,
                                precio_unitario=Decimal(precio),
                                stock_actual=0,
                                categoria=rubro,
                            )
                        )
                await db.flush()
                resultado = await generar_historial(
                    db,
                    dias=dias,
                    intensidad=intensidad,
                    habitacion_poco_usada=poco_usada,
                    arreglos=arreglos,
                    semilla=11 if codigo == "luna" else 7,
                )
            async with sesiones(info={CLAVE: establecimiento.id}) as db:
                opiniones = await agregar_opiniones(db, 11 if codigo == "luna" else 7, poco_usada)
                await db.commit()
            async with sesiones(info={CLAVE: establecimiento.id}) as db:
                await agregar_operacion(db, 11 if codigo == "luna" else 7, poco_usada)
                await db.commit()
            async with sesiones(info={CLAVE: establecimiento.id}) as db:
                await _novedades_demo(db, codigo, inicio_de_franja(datetime.now(UTC), ZoneInfo(settings.ZONA_HORARIA)))
            print(
                f"{codigo}: {dias} días de historial · {resultado.get('turnos', 0)} turnos, "
                f"{resultado.get('consumos', 0)} consumos, {resultado.get('guardias', 0)} guardias arqueadas, "
                f"{resultado.get('registrados', 0)} clientes perdidos registrados, {opiniones} opiniones."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(cargar())
