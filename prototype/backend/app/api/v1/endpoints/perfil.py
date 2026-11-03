"""Mi perfil (migración 008): cualquier usuario con sesión, también la plataforma."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.operador import Operador
from app.schemas.perfil import ClavePropia, PerfilCambio, PerfilResponse
from app.services import perfil

router = APIRouter()


@router.get("/", response_model=PerfilResponse)
async def ver(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    return await perfil.perfil_de(db, operador)


@router.patch("/", response_model=PerfilResponse)
async def cambiar(
    datos: PerfilCambio, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    await perfil.cambiar_nombre(db, operador, datos.nombre_visible)
    return await perfil.perfil_de(db, operador)


@router.post("/clave", status_code=status.HTTP_204_NO_CONTENT)
async def cambiar_clave(
    datos: ClavePropia, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    """La sesión sigue abierta: el token no depende de la clave."""
    await perfil.cambiar_clave_propia(db, operador, datos.actual, datos.nueva)
