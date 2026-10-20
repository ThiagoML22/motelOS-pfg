"""Operadores de demostración para probar el prototipo en una máquina local.

Crea, si no existen, la cuenta de la gerencia (ADMINISTRADOR) y dos conserjes (OPERADOR). Las claves
salen de DEMO_CLAVE_GERENCIA y DEMO_CLAVE_CONSERJES (archivo .env, que no se versiona); si no están
definidas se generan al azar y se muestran una sola vez. Son cuentas de prueba: en el motel se dan de
alta las reales con scripts/crear_operador.py.

Uso (Docker): docker compose run --rm admin
"""

import asyncio
import os
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.operador import ROL_ADMINISTRADOR, ROL_OPERADOR, Operador
from scripts.crear_operador import alta_operador

DEMO = [
    ("gerencia", "Gerencia", ROL_ADMINISTRADOR, "DEMO_CLAVE_GERENCIA"),
    ("conserje1", "Conserje 1", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
    ("conserje2", "Conserje 2", ROL_OPERADOR, "DEMO_CLAVE_CONSERJES"),
]


async def cargar() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    generadas: dict[str, str] = {}
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            existentes = set((await db.execute(select(Operador.usuario))).scalars().all())
            for usuario, nombre, rol, variable in DEMO:
                if usuario in existentes:
                    print(f"{usuario}: ya existe, no se modifica.")
                    continue
                clave = os.environ.get(variable) or generadas.get(variable) or secrets.token_urlsafe(12)
                if not os.environ.get(variable):
                    generadas[variable] = clave
                await alta_operador(db, usuario, nombre, rol, clave)
                print(f"{usuario}: creado ({rol}).")
    finally:
        await engine.dispose()
    for variable, clave in generadas.items():
        print(f"Clave generada para {variable}: {clave}  (guardela; no se vuelve a mostrar)")


if __name__ == "__main__":
    asyncio.run(cargar())
