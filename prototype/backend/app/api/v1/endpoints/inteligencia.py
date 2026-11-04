"""Inteligencia local de la gerencia: tablero (resumen, alertas, pronóstico, demanda, sugerencias y reposición) y el
asistente que responde preguntas. Todo se calcula en este servidor; solo ve lo ya arqueado (RN-RES-03)."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services import asistente, gemelo, inteligencia

router = APIRouter()


class Pregunta(BaseModel):
    texto: str = Field(min_length=1, max_length=300)
    # La pregunta anterior de la conversación y su intención, para entender seguimientos («¿y la semana pasada?»).
    anterior: str | None = Field(default=None, max_length=300)
    anterior_intencion: str | None = Field(default=None, max_length=60)
    # La pantalla en la que está quien pregunta: «¿qué hago acá?» se responde según la sección abierta.
    pantalla: str | None = Field(default=None, max_length=30)


class EscenarioGemelo(BaseModel):
    limpieza_min: float | None = Field(default=None, ge=1, le=180)
    # Habitaciones que se suman (o se sacan) por categoría.
    habitaciones: dict[int, int] = Field(default_factory=dict)
    precio_pct: float = Field(default=0, ge=-50, le=50)
    precio_cuando: Literal["siempre", "pico", "floja"] = "siempre"
    dias: int = Field(default=30, ge=7, le=90)


@router.post("/gemelo")
async def probar_escenario(datos: EscenarioGemelo, db: AsyncSession = Depends(get_db)) -> dict:
    """Repite las llegadas reales con otra limpieza, otras habitaciones u otro precio. No cambia nada."""
    escenario = gemelo.Escenario(datos.limpieza_min, datos.habitaciones, datos.precio_pct, datos.precio_cuando)
    return gemelo.simular(await inteligencia.contexto(db), escenario, datos.dias)


@router.get("/tablero")
async def tablero(db: AsyncSession = Depends(get_db)) -> dict:
    return await inteligencia.tablero(db)


@router.post("/pregunta")
async def preguntar(pregunta: Pregunta, db: AsyncSession = Depends(get_db)) -> dict:
    return asistente.responder(await inteligencia.contexto(db), pregunta.texto)
