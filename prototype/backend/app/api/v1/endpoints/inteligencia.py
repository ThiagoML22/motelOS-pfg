"""Inteligencia local de la gerencia: tablero (resumen, alertas, pronóstico, demanda, sugerencias y reposición) y el
asistente que responde preguntas. Todo se calcula en este servidor; solo ve lo ya arqueado (RN-RES-03)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import asistente, inteligencia

router = APIRouter()


class Pregunta(BaseModel):
    texto: str = Field(min_length=1, max_length=300)


@router.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db)) -> dict:
    return await inteligencia.tablero(db)


@router.post("/pregunta")
async def preguntar(pregunta: Pregunta, db: AsyncSession = Depends(get_db)) -> dict:
    return asistente.responder(await inteligencia.contexto(db), pregunta.texto)
