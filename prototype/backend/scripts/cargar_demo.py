"""Datos de demostración para probar el prototipo en una máquina local.

Crea, si no existen:
- en el establecimiento predeterminado (motelcc, migración 006): la gerencia (ADMINISTRADOR) y dos conserjes;
- un segundo establecimiento, Motel Luna (código luna), con sus habitaciones, su tarifa, sus artículos y los
  mismos nombres de usuario: muestra que cada motel ve solo lo suyo (multiinquilino);
- el usuario de la plataforma, que da de alta establecimientos (código de ingreso «plataforma»).

Las claves salen de DEMO_CLAVE_GERENCIA, DEMO_CLAVE_CONSERJES y DEMO_CLAVE_PLATAFORMA (archivo .env, que no se
versiona); si no están definidas se generan al azar y se muestran una sola vez. Son cuentas de prueba: en el motel
se dan de alta las reales con scripts/crear_operador.py.

Uso (Docker): docker compose run --rm admin
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.inquilino import CLAVE, PLATAFORMA
from app.models.articulo import Articulo
from app.models.categoria import CategoriaHabitacion
from app.models.configuracion import ConfiguracionCaja
from app.models.establecimiento import Establecimiento
from app.models.franja_tarifa import FranjaTarifa
from app.models.habitacion import Habitacion
from app.models.operador import ROL_ADMINISTRADOR, ROL_OPERADOR, ROL_PLATAFORMA, Operador
from app.models.tarifa import Tarifa
from app.schemas.configuracion import ParametrosTarifa
from app.services import franjas
from app.services.configuracion import nueva_tarifa_de
from scripts.crear_operador import alta_operador

USUARIOS = [
    ("gerencia", "Gerencia", ROL_ADMINISTRADOR, "DEMO_CLAVE_GERENCIA"),
    ("conserje1", "Conserje 1", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
    ("conserje2", "Conserje 2", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
]

LUNA = {
    "codigo": "luna",
    "nombre": "Motel Luna",
    "domicilio": "Ruta 12 km 8, Garupá",
    "telefono": "3764-555000",
    "color_marca": "#6d28d9",
    "eslogan": "Noches bajo la luna",
}
# Eslogan de Motel C.C. (migración 009); su color queda el azul de MotelOS, así se ve la diferencia entre moteles.
ESLOGAN_MOTELCC = "Tu descanso, a tu manera"
LUNA_USUARIOS = [
    ("gerencia", "Gerencia Luna", ROL_ADMINISTRADOR, "DEMO_CLAVE_GERENCIA"),
    ("conserje1", "Conserje Luna", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
]
LUNA_ARTICULOS = [
    ("BEB-001", "Agua saborizada 500 ml", 1000, 20, "Bebidas"),
    ("BEB-002", "Gaseosa cola 500 ml", 1500, 15, "Bebidas"),
    ("SNA-001", "Alfajor triple", 1200, 3, "Snacks"),
]


class Claves:
    def __init__(self) -> None:
        self.generadas: dict[str, str] = {}

    def de(self, variable: str) -> str:
        clave = os.environ.get(variable) or self.generadas.get(variable)
        if not clave:
            clave = self.generadas[variable] = secrets.token_urlsafe(12)
        return clave


async def _usuarios(db: AsyncSession, usuarios, claves: Claves, etiqueta: str) -> None:
    existentes = set((await db.execute(select(Operador.usuario))).scalars().all())
    for usuario, nombre, rol, variable in usuarios:
        if usuario in existentes:
            print(f"{etiqueta} · {usuario}: ya existe, no se modifica.")
            continue
        await alta_operador(db, usuario, nombre, rol, claves.de(variable))
        print(f"{etiqueta} · {usuario}: creado ({rol}).")


async def _luna(db: AsyncSession) -> int:
    """El segundo establecimiento con su configuración inicial (lo mismo que hace la plataforma desde la pantalla)."""
    existente = (await db.execute(select(Establecimiento).where(Establecimiento.codigo == LUNA["codigo"]))).scalars()
    establecimiento = existente.first()
    if establecimiento is not None:
        return establecimiento.id
    establecimiento = Establecimiento(**LUNA, leyenda_comprobante="Motel Luna · Comprobante interno de caja.")
    db.add(establecimiento)
    await db.flush()
    db.info[CLAVE] = establecimiento.id
    ahora = datetime.now(UTC)
    simple = CategoriaHabitacion(nombre="Simple", descripcion="Habitación estándar", color="#244473", orden=1)
    db.add(simple)
    await db.flush()
    db.add_all(
        [Habitacion(numero=n, estado="Libre", activa=True, categoria_id=simple.id) for n in range(101, 109)]
        + [
            Tarifa(
                nombre=f"Simple desde {ahora:%Y-%m-%d %H:%M:%S.%f}",
                categoria_id=simple.id,
                tarifa_base=Decimal("10000"),
                estadia_base_min=120,
                tolerancia_min=0,
                fraccion_min=30,
                tarifa_fraccion=Decimal("3000"),
                vigente=True,
                vigente_desde=ahora,
            ),
            ConfiguracionCaja(
                establecimiento_id=establecimiento.id, fondo_cambio=Decimal("20000"), actualizado_en=ahora
            ),
        ]
        + [
            Articulo(codigo=c, descripcion=d, precio_unitario=Decimal(p), stock_actual=s, categoria=g)
            for c, d, p, s, g in LUNA_ARTICULOS
        ]
    )
    await db.commit()
    print("Motel Luna: creado con 8 habitaciones (101 a 108), tarifa $10.000 + $3.000 y 3 artículos.")
    return establecimiento.id


# Categorías de demostración (migración 008): nombre, descripción, color, orden, tarifa y números de habitación.
# Las habitaciones 1 a 8 de Motel C.C. quedan en Simple: los recorridos del canal usan la 1 y la 2 con $8.000.
CATEGORIAS_DEMO = {
    "motelcc": [
        (
            "Especial",
            "Hidromasaje y cama king",
            "#0f766e",
            2,
            ParametrosTarifa(tarifa_base=11000, estadia_base_min=120, fraccion_min=30, tarifa_fraccion=3500),
            [9, 10, 11],
        ),
        (
            "VIP",
            "Suite con jacuzzi, sauna y garage privado",
            "#7c3aed",
            3,
            ParametrosTarifa(
                tarifa_base=16000,
                estadia_base_min=180,
                fraccion_min=60,
                tarifa_fraccion=6000,
                tolerancia_min=10,
                tope=40000,
            ),
            [12, 13],
        ),
    ],
    "luna": [
        (
            "Suite",
            "Suite con hidromasaje",
            "#b45309",
            2,
            ParametrosTarifa(tarifa_base=14000, estadia_base_min=150, fraccion_min=30, tarifa_fraccion=4000),
            [107, 108],
        ),
    ],
}


# Tarifas especiales de demostración (migración 014): Especial sube todas las noches y VIP baja de día en la semana.
# Simple queda sin ninguna: es la que muestra la sugerencia de crear una para el pico del fin de semana.
FRANJAS_DEMO = {
    "motelcc": {
        "Especial": [
            (
                "Noche",
                franjas.TODOS_LOS_DIAS,
                time(20),
                time(6),
                ParametrosTarifa(tarifa_base=13500, estadia_base_min=120, fraccion_min=30, tarifa_fraccion=4000),
            ),
        ],
        "VIP": [
            (
                "De día en la semana",
                franjas.mascara(0, 1, 2, 3, 4),
                time(8),
                time(20),
                ParametrosTarifa(
                    tarifa_base=13500,
                    estadia_base_min=180,
                    fraccion_min=60,
                    tarifa_fraccion=5000,
                    tolerancia_min=10,
                    tope=34000,
                ),
            ),
        ],
    },
}


async def _franjas(db: AsyncSession, codigo: str) -> None:
    for categoria_nombre, lista in FRANJAS_DEMO.get(codigo, {}).items():
        consulta = select(CategoriaHabitacion).where(CategoriaHabitacion.nombre == categoria_nombre)
        categoria = (await db.execute(consulta)).scalars().first()
        if categoria is None:
            continue
        for nombre, dias, desde, hasta, tarifa in lista:
            consulta = select(FranjaTarifa).where(
                FranjaTarifa.categoria_id == categoria.id, FranjaTarifa.nombre == nombre
            )
            if (await db.execute(consulta)).first():
                continue
            franja = FranjaTarifa(categoria_id=categoria.id, nombre=nombre, dias=dias, desde=desde, hasta=hasta)
            db.add(franja)
            await db.flush()
            db.add(nueva_tarifa_de(categoria, tarifa, None, franja.id))
            await db.commit()
            regla = franjas.regla_texto(dias, desde, hasta)
            print(f"{codigo} · {categoria_nombre}: tarifa especial «{nombre}», {regla}.")


async def _categorias(db: AsyncSession, codigo: str) -> None:
    for nombre, descripcion, color, orden, tarifa, numeros in CATEGORIAS_DEMO.get(codigo, []):
        if (await db.execute(select(CategoriaHabitacion).where(CategoriaHabitacion.nombre == nombre))).first():
            continue
        categoria = CategoriaHabitacion(nombre=nombre, descripcion=descripcion, color=color, orden=orden)
        db.add(categoria)
        await db.flush()
        db.add(nueva_tarifa_de(categoria, tarifa, None))
        habitaciones = (await db.execute(select(Habitacion).where(Habitacion.numero.in_(numeros)))).scalars().all()
        for habitacion in habitaciones:
            habitacion.categoria_id = categoria.id
        await db.commit()
        print(f"{codigo} · categoría {nombre}: creada con las habitaciones {', '.join(map(str, numeros))}.")


async def cargar() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    claves = Claves()
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sesiones() as db:
            consulta = select(Establecimiento).where(Establecimiento.codigo == settings.ESTABLECIMIENTO_PREDETERMINADO)
            principal = (await db.execute(consulta)).scalars().one()
            if not principal.eslogan:
                principal.eslogan = ESLOGAN_MOTELCC
                await db.commit()
            luna_id = await _luna(db)
        async with sesiones(info={CLAVE: principal.id}) as db:
            await _usuarios(db, USUARIOS, claves, principal.nombre)
            await _categorias(db, principal.codigo)
            await _franjas(db, principal.codigo)
        async with sesiones(info={CLAVE: luna_id}) as db:
            await _usuarios(db, LUNA_USUARIOS, claves, "Motel Luna")
            await _categorias(db, "luna")
        async with sesiones(info={CLAVE: PLATAFORMA}) as db:
            await _usuarios(
                db,
                [("plataforma", "Equipo de la plataforma", ROL_PLATAFORMA, "DEMO_CLAVE_PLATAFORMA")],
                claves,
                "Plataforma",
            )
    finally:
        await engine.dispose()
    for variable, clave in claves.generadas.items():
        print(f"Clave generada para {variable}: {clave}  (guardela; no se vuelve a mostrar)")


if __name__ == "__main__":
    asyncio.run(cargar())
