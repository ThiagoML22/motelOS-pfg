"""Asistente para todo el personal: ayuda para usar el sistema y el estado de la ventanilla (services.ayuda); a la
gerencia, además, el análisis de los datos del motel (services.asistente). Todo se calcula en este servidor."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.api.v1.endpoints.inteligencia import Pregunta
from app.core.database import get_db
from app.models.operador import Operador
from app.services import asistente, ayuda, inteligencia

router = APIRouter()


@router.post("/pregunta")
async def preguntar(
    pregunta: Pregunta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    respuesta = await ayuda.responder(db, operador, pregunta.texto)
    if respuesta is not None:
        return respuesta
    # Solo llega acá la gerencia (ayuda.responder ya contestó al conserje): análisis de los datos.
    return {**asistente.responder(await inteligencia.contexto(db), pregunta.texto), "pasos": [], "acciones": []}
