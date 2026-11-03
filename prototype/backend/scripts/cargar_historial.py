"""Historial de demostración: semanas de operación pasada para que la gerencia y la inteligencia local tengan datos.

Por cada establecimiento de la demo genera guardias de 8 h ya arqueadas, con sus turnos, consumos y cobros:
- demanda con la forma de un motel: noches de viernes y sábado llenas, la siesta de la tarde, madrugadas tranquilas,
  y un leve crecimiento a lo largo del período;
- estadías por categoría con la tarifa vigente (sobreturnos, algún pernocte con tope) y limpieza entre turnos;
- arqueos casi siempre correctos, con más faltantes en uno de los conserjes y una habitación que se usa poco:
  así la detección de anomalías tiene algo real para mostrar.

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
from app.models.categoria import CategoriaHabitacion
from app.models.configuracion import ConfiguracionCaja
from app.models.consumo import Consumo
from app.models.establecimiento import Establecimiento
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.operador import ROL_OPERADOR, Operador
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services.billing_service import calcular_sobreturno
from app.services.caja import clasificar_diferencia

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
) -> dict[str, int]:
    """Genera `dias` días de operación que terminan en `hasta` (por defecto, el comienzo de la franja actual).

    La sesión debe estar asociada a un establecimiento (session.info). Devuelve cuántas filas creó de cada tipo.
    """
    zona = ZoneInfo(settings.ZONA_HORARIA)
    rng = random.Random(semilla)
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
    tarifas = {t.categoria_id: t for t in (await db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)))).scalars()}
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
    contador = {"turnos": 0, "consumos": 0, "pagos": 0, "guardias": len(guardias), "arqueos": 0, "perdidos": 0}

    for llegada in llegadas:
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
            continue

        tarifa = tarifas[elegida.categoria_id]
        nombre = categorias[elegida.categoria_id].nombre.lower() if elegida.categoria_id in categorias else ""
        minutos = _duracion(rng, tarifa, nocturno, elegida.categoria_id == premium, SE_QUEDA_MAS.get(nombre, 0.3))
        salida = llegada + timedelta(minutes=minutos)
        if salida >= fin_periodo:
            continue  # quedaría en curso: el historial termina con todas las habitaciones libres
        libre_desde[elegida.id] = salida + timedelta(minutes=rng.randint(18, 40))  # limpieza

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

    # Stock final: cada artículo queda con unos días de cobertura según lo que se vendió (algunos casi agotados).
    for i, articulo in enumerate(articulos):
        por_dia = consumido[articulo.id] / dias
        articulo.stock_actual = max(0, round(por_dia * COBERTURA_DIAS[i % len(COBERTURA_DIAS)]))
    await db.commit()
    return contador


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
DEMO = (("motelcc", 60, 1.5, 6), ("luna", 30, 0.7, None))


async def cargar() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for codigo, dias, intensidad, poco_usada in DEMO:
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
                    semilla=11 if codigo == "luna" else 7,
                )
            print(
                f"{codigo}: {dias} días de historial · {resultado.get('turnos', 0)} turnos, "
                f"{resultado.get('consumos', 0)} consumos, {resultado.get('guardias', 0)} guardias arqueadas."
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(cargar())
