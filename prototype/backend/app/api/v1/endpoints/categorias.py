"""Categorías de habitación para la ventanilla (migración 008): nombre, color y tarifa vigente de cada una.

Las da de alta y las cambia la gerencia desde el panel de configuración; acá solo se leen las activas.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.configuracion import CategoriaResponse
from app.services import categorias

router = APIRouter()


@router.get("/", response_model=list[CategoriaResponse])
async def listar(db: AsyncSession = Depends(get_db)):
    return await categorias.listar(db, solo_activas=True)
