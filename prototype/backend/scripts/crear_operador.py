"""Alta de un operador o restablecimiento de su clave (RNF-04).

Corre con el usuario dueño de las tablas (DATABASE_URL de administración), porque el rol de la
aplicación no puede crear operadores ni cambiar claves o roles. La clave se pide por teclado o se
toma de la variable OPERADOR_CLAVE; nunca se pasa como argumento (quedaría en el historial).

Uso (Docker):
    docker compose run --rm admin scripts.crear_operador --usuario conserje3 --nombre "Conserje Tres"
    docker compose run --rm admin scripts.crear_operador --usuario conserje3 --restablecer-clave
"""

import argparse
import asyncio
import getpass
import os
import re
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.seguridad import hashear_clave
from app.models.operador import ROL_ADMINISTRADOR, ROL_OPERADOR, Operador

LARGO_MINIMO_CLAVE = 10
PATRON_USUARIO = re.compile(r"^[a-z0-9._-]{3,40}$")


def validar_clave(clave: str) -> None:
    if len(clave) < LARGO_MINIMO_CLAVE:
        raise ValueError(f"La clave debe tener al menos {LARGO_MINIMO_CLAVE} caracteres.")


async def alta_operador(db: AsyncSession, usuario: str, nombre: str, rol: str, clave: str) -> Operador:
    usuario = usuario.strip().lower()
    if not PATRON_USUARIO.match(usuario):
        raise ValueError("El usuario admite de 3 a 40 letras minúsculas, números, punto, guion o guion bajo.")
    if rol not in (ROL_OPERADOR, ROL_ADMINISTRADOR):
        raise ValueError(f"Rol desconocido: {rol}")
    validar_clave(clave)
    existente = (await db.execute(select(Operador).where(Operador.usuario == usuario))).scalars().first()
    if existente is not None:
        raise ValueError(f"El usuario {usuario} ya existe.")
    operador = Operador(usuario=usuario, nombre_visible=nombre.strip(), rol=rol, hash_clave=hashear_clave(clave))
    db.add(operador)
    await db.commit()
    return operador


async def restablecer_clave(db: AsyncSession, usuario: str, clave: str) -> None:
    validar_clave(clave)
    operador = (await db.execute(select(Operador).where(Operador.usuario == usuario.strip().lower()))).scalars().first()
    if operador is None:
        raise ValueError(f"No existe el usuario {usuario}.")
    operador.hash_clave = hashear_clave(clave)
    operador.intentos_fallidos = 0
    operador.bloqueado_hasta = None
    await db.commit()


def pedir_clave() -> str:
    clave = os.environ.get("OPERADOR_CLAVE")
    if clave:
        return clave
    clave = getpass.getpass("Clave nueva: ")
    if clave != getpass.getpass("Repetir clave: "):
        raise ValueError("Las claves no coinciden.")
    return clave


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--nombre", help="Nombre visible (obligatorio para el alta)")
    parser.add_argument("--rol", default=ROL_OPERADOR, choices=[ROL_OPERADOR, ROL_ADMINISTRADOR])
    parser.add_argument("--restablecer-clave", action="store_true", help="Cambia la clave y quita el bloqueo")
    args = parser.parse_args(argv)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            if args.restablecer_clave:
                await restablecer_clave(db, args.usuario, pedir_clave())
                print(f"Clave de {args.usuario} restablecida.")
            else:
                if not args.nombre:
                    parser.error("--nombre es obligatorio para dar de alta un operador")
                operador = await alta_operador(db, args.usuario, args.nombre, args.rol, pedir_clave())
                print(f"Operador {operador.usuario} ({operador.rol}) creado.")
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
