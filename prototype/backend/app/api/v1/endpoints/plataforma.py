"""Rutas de la plataforma (multiinquilino): solo el rol PLATAFORMA (main.py)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.configuracion import (
    EstablecimientoAlta,
    EstablecimientoEstado,
    EstablecimientoResponse,
    EstablecimientoResumen,
)
from app.services import plataforma

router = APIRouter()


@router.get("/establecimientos", response_model=list[EstablecimientoResumen])
async def listar(db: AsyncSession = Depends(get_db)):
    return await plataforma.resumen(db)


@router.post("/establecimientos", response_model=EstablecimientoResponse, status_code=status.HTTP_201_CREATED)
async def alta(datos: EstablecimientoAlta, db: AsyncSession = Depends(get_db)):
    return await plataforma.alta_establecimiento(db, datos)


@router.patch("/establecimientos/{establecimiento_id}", response_model=EstablecimientoResponse)
async def cambiar_estado(establecimiento_id: int, datos: EstablecimientoEstado, db: AsyncSession = Depends(get_db)):
    return await plataforma.cambiar_estado(db, establecimiento_id, datos.activo)
