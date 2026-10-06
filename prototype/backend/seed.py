"""Carga de datos iniciales, idempotente.

Replica lo que db/init.sql ya inserta (13 habitaciones, la tarifa Estandar y 4 articulos) para las
bases que se crean sin ese script. Solo agrega lo que falta: ejecutado sobre una base inicializada
con init.sql no duplica ni falla.
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.articulo import Articulo
from app.models.habitacion import Habitacion
from app.models.tarifa import Tarifa

CANTIDAD_HABITACIONES = 13

TARIFA_ESTANDAR = {
    "nombre": "Estandar",
    "tarifa_base": Decimal("8000"),
    "estadia_base_min": 120,
    "tolerancia_min": 0,
    "fraccion_min": 30,
    "tarifa_fraccion": Decimal("2500"),
    "vigente": True,
}

ARTICULOS = [
    ("MIN-001", "Agua Mineral 500ml", Decimal("800"), 10, "Bebidas"),
    ("MIN-002", "Bebida Energética", Decimal("1200"), 8, "Bebidas"),
    ("MIN-003", "Cerveza Lata 473ml", Decimal("1800"), 12, "Bebidas"),
    ("SNA-001", "Papas Fritas Lays 90g", Decimal("1500"), 5, "Snacks"),
]


async def seed_data() -> dict[str, int]:
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    creados = {"habitaciones": 0, "tarifas": 0, "articulos": 0}

    async with async_session() as session:
        numeros = set((await session.execute(select(Habitacion.numero))).scalars().all())
        for numero in range(1, CANTIDAD_HABITACIONES + 1):
            if numero not in numeros:
                session.add(Habitacion(numero=numero, estado="Libre"))
                creados["habitaciones"] += 1

        nombres = set((await session.execute(select(Tarifa.nombre))).scalars().all())
        if TARIFA_ESTANDAR["nombre"] not in nombres:
            session.add(Tarifa(**TARIFA_ESTANDAR))
            creados["tarifas"] += 1

        codigos = set((await session.execute(select(Articulo.codigo))).scalars().all())
        for codigo, descripcion, precio, stock, categoria in ARTICULOS:
            if codigo not in codigos:
                session.add(
                    Articulo(
                        codigo=codigo,
                        descripcion=descripcion,
                        precio_unitario=precio,
                        stock_actual=stock,
                        categoria=categoria,
                    )
                )
                creados["articulos"] += 1

        await session.commit()

    await engine.dispose()
    return creados


if __name__ == "__main__":
    resultado = asyncio.run(seed_data())
    print(
        "Seed finalizado: "
        f"{resultado['habitaciones']} habitaciones, {resultado['tarifas']} tarifa y "
        f"{resultado['articulos']} articulos agregados (lo ya existente no se modifica)."
    )
