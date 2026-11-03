"""Dependencias de autenticación y autorización de las rutas (RNF-04)."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.inquilino import PLATAFORMA, fijar_establecimiento
from app.core.seguridad import leer_token
from app.models.establecimiento import Establecimiento
from app.models.operador import ROL_ADMINISTRADOR, ROL_PLATAFORMA, Operador

SIN_SESION = "Sesión no iniciada o vencida. Inicie sesión nuevamente."
SUSPENDIDO = "El establecimiento está suspendido. Comuníquese con la plataforma."


async def operador_actual(request: Request, db: AsyncSession = Depends(get_db)) -> Operador:
    """El operador de la sesión: sale de la cookie firmada, nunca de lo que envía el cliente en el cuerpo.

    También fija el establecimiento de la sesión de base de datos (multiinquilino): todas las consultas de la
    petición quedan limitadas a él. FastAPI reutiliza la misma sesión (get_db) en toda la petición.
    """
    token = request.cookies.get(settings.COOKIE_NOMBRE)
    datos = leer_token(token) if token else None
    if datos is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION)
    try:
        operador_id = int(datos["sub"])
        establecimiento_id = int(datos["est"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION) from None
    if establecimiento_id != PLATAFORMA:
        establecimiento = await db.get(Establecimiento, establecimiento_id)
        if establecimiento is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION)
        if not establecimiento.activo:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SUSPENDIDO)
    await fijar_establecimiento(db, establecimiento_id)
    operador = await db.get(Operador, operador_id)
    # Un operador desactivado o con el rol cambiado pierde la sesión aunque el token no haya vencido.
    if (
        operador is None
        or not operador.activo
        or operador.rol != datos.get("rol")
        or (operador.establecimiento_id or PLATAFORMA) != establecimiento_id
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION)
    return operador


async def operador_de_establecimiento(operador: Operador = Depends(operador_actual)) -> Operador:
    """Las rutas de la ventanilla y de la gerencia no son para la plataforma, que no opera ningún motel."""
    if operador.rol == ROL_PLATAFORMA:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="La plataforma no opera la ventanilla de un establecimiento."
        )
    return operador


def requiere_rol(*roles: str):
    async def verificar(operador: Operador = Depends(operador_actual)) -> Operador:
        if operador.rol not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Su rol no permite esta operación.")
        return operador

    return verificar


solo_administrador = requiere_rol(ROL_ADMINISTRADOR)
solo_plataforma = requiere_rol(ROL_PLATAFORMA)
