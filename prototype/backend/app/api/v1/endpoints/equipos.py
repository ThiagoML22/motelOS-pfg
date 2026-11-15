"""Equipos autorizados (migración 019): lo que ve y decide la gerencia. Solo el rol ADMINISTRADOR (main.py)."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.operador import Operador
from app.services import equipos

router = APIRouter()


class Nombre(BaseModel):
    nombre: str = Field(min_length=1, max_length=40)


class Ajustes(BaseModel):
    control: bool | None = None
    # Texto libre: «192.168.0.0/24, 192.168.0.10». Vacío quita la restricción de red.
    redes: str | None = Field(default=None, max_length=200)


@router.get("/")
async def panel(request: Request, db: AsyncSession = Depends(get_db)):
    return await equipos.panel(db, request)


@router.get("/intentos")
async def intentos(db: AsyncSession = Depends(get_db)):
    """Los intentos del último día, para la campanita."""
    return await equipos.intentos_recientes(db)


@router.patch("/ajustes")
async def ajustes(datos: Ajustes, db: AsyncSession = Depends(get_db), gerencia: Operador = Depends(operador_actual)):
    return await equipos.cambiar_ajustes(db, gerencia, datos.control, datos.redes)


@router.post("/este-equipo")
async def autorizar_este(
    datos: Nombre,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    gerencia: Operador = Depends(operador_actual),
):
    return await equipos.autorizar_este(db, request, response, gerencia, datos.nombre)


@router.post("/{equipo_id}/autorizar")
async def autorizar(
    equipo_id: int, datos: Nombre, db: AsyncSession = Depends(get_db), gerencia: Operador = Depends(operador_actual)
):
    return await equipos.autorizar(db, gerencia, equipo_id, datos.nombre)


@router.post("/{equipo_id}/bloquear")
async def bloquear(equipo_id: int, db: AsyncSession = Depends(get_db), gerencia: Operador = Depends(operador_actual)):
    return await equipos.bloquear(db, gerencia, equipo_id)
