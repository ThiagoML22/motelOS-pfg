"""Dependencias de autenticación y autorización de las rutas (RNF-04)."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.seguridad import leer_token
from app.models.operador import ROL_ADMINISTRADOR, Operador

SIN_SESION = "Sesión no iniciada o vencida. Inicie sesión nuevamente."


async def operador_actual(request: Request, db: AsyncSession = Depends(get_db)) -> Operador:
    """El operador de la sesión: sale de la cookie firmada, nunca de lo que envía el cliente en el cuerpo."""
    token = request.cookies.get(settings.COOKIE_NOMBRE)
    datos = leer_token(token) if token else None
    if datos is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION)
    try:
        operador_id = int(datos["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION) from None
    operador = await db.get(Operador, operador_id)
    # Un operador desactivado o con el rol cambiado pierde la sesión aunque el token no haya vencido.
    if operador is None or not operador.activo or operador.rol != datos.get("rol"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SIN_SESION)
    return operador


def requiere_rol(*roles: str):
    async def verificar(operador: Operador = Depends(operador_actual)) -> Operador:
        if operador.rol not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Su rol no permite esta operación.")
        return operador

    return verificar


solo_administrador = requiere_rol(ROL_ADMINISTRADOR)
