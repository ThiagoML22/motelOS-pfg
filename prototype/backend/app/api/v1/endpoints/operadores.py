"""Consulta de operadores para la gerencia (solo lectura: el alta se hace con scripts/crear_operador.py)."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.operador import Operador
from app.schemas.auth import OperadorPublico

router = APIRouter()


class OperadorEstado(OperadorPublico):
    activo: bool
    ultimo_acceso: datetime | None = None
    bloqueado_hasta: datetime | None = None


@router.get("/", response_model=list[OperadorEstado])
async def listar(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Operador).order_by(Operador.nombre_visible))).scalars().all()
