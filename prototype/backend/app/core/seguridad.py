"""Claves y sesiones (RNF-04).

- Las claves se guardan solo como hash argon2id; nunca en texto ni en los registros.
- La sesión es un JWT firmado (HS256) que viaja en una cookie httpOnly: el JavaScript de la página no
  puede leerlo, de modo que un script inyectado no puede robarlo.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Response

from app.core.config import settings

_hasher = PasswordHasher(time_cost=settings.ARGON2_TIME_COST, memory_cost=settings.ARGON2_MEMORY_KIB)

# Hash de una clave que nadie tiene. Cuando el usuario no existe se verifica contra este hash para que la
# respuesta tarde lo mismo que con un usuario real y no revele qué usuarios existen.
HASH_FICTICIO = _hasher.hash("clave-ficticia-para-igualar-tiempos")


def hashear_clave(clave: str) -> str:
    return _hasher.hash(clave)


def verificar_clave(hash_clave: str, clave: str) -> bool:
    try:
        return _hasher.verify(hash_clave, clave)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def crear_token(operador_id: int, rol: str, ahora: datetime | None = None) -> str:
    emitido = ahora or datetime.now(UTC)
    datos = {
        "sub": str(operador_id),
        "rol": rol,
        "iat": emitido,
        "exp": emitido + timedelta(hours=settings.SESION_HORAS),
    }
    return jwt.encode(datos, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITMO)


def leer_token(token: str) -> dict[str, Any] | None:
    """Devuelve los datos del token si la firma es válida y no venció; si no, None."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITMO],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None


def poner_cookie_sesion(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_NOMBRE,
        value=token,
        max_age=settings.SESION_HORAS * 3600,
        path="/api",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
    )


def borrar_cookie_sesion(response: Response) -> None:
    response.delete_cookie(
        key=settings.COOKIE_NOMBRE, path="/api", httponly=True, secure=settings.COOKIE_SECURE, samesite="strict"
    )
