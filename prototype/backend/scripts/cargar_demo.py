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
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.inquilino import CLAVE, PLATAFORMA
from app.models.articulo import Articulo
from app.models.configuracion import ConfiguracionCaja
from app.models.establecimiento import Establecimiento
from app.models.habitacion import Habitacion
from app.models.operador import ROL_ADMINISTRADOR, ROL_OPERADOR, ROL_PLATAFORMA, Operador
from app.models.tarifa import Tarifa
from scripts.crear_operador import alta_operador

USUARIOS = [
    ("gerencia", "Gerencia", ROL_ADMINISTRADOR, "DEMO_CLAVE_GERENCIA"),
    ("conserje1", "Conserje 1", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
    ("conserje2", "Conserje 2", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
]

LUNA = {"codigo": "luna", "nombre": "Motel Luna", "domicilio": "Ruta 12 km 8, Garupá", "telefono": "3764-555000"}
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
    db.add_all(
        [Habitacion(numero=n, estado="Libre", activa=True) for n in range(101, 109)]
        + [
            Tarifa(nombre=f"Vigente desde {ahora:%Y-%m-%d %H:%M:%S.%f}", tarifa_base=Decimal("10000"),
                   estadia_base_min=120, tolerancia_min=0, fraccion_min=30, tarifa_fraccion=Decimal("3000"),
                   vigente=True, vigente_desde=ahora),
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


async def cargar() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    claves = Claves()
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sesiones() as db:
            consulta = select(Establecimiento).where(Establecimiento.codigo == settings.ESTABLECIMIENTO_PREDETERMINADO)
            principal = (await db.execute(consulta)).scalars().one()
            luna_id = await _luna(db)
        async with sesiones(info={CLAVE: principal.id}) as db:
            await _usuarios(db, USUARIOS, claves, principal.nombre)
        async with sesiones(info={CLAVE: luna_id}) as db:
            await _usuarios(db, LUNA_USUARIOS, claves, "Motel Luna")
        async with sesiones(info={CLAVE: PLATAFORMA}) as db:
            await _usuarios(
                db, [("plataforma", "Equipo de la plataforma", ROL_PLATAFORMA, "DEMO_CLAVE_PLATAFORMA")], claves,
                "Plataforma",
            )
    finally:
        await engine.dispose()
    for variable, clave in claves.generadas.items():
        print(f"Clave generada para {variable}: {clave}  (guardela; no se vuelve a mostrar)")


if __name__ == "__main__":
    asyncio.run(cargar())
