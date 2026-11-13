"""Asistente para todo el personal: ayuda para usar el sistema, glosario y estado de la ventanilla (services.ayuda y
services.conocimiento); a la gerencia, además, el análisis de los datos del motel (services.asistente). Todo se calcula
en este servidor."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.api.v1.endpoints.inteligencia import Pregunta
from app.core.database import get_db
from app.models.operador import Operador
from app.services import asistente, ayuda, comprension, inteligencia

router = APIRouter()


async def _una(
    db: AsyncSession,
    operador: Operador,
    texto: str,
    pregunta: Pregunta,
    anterior: str | None = None,
    anterior_intencion: str | None = None,
) -> dict:
    respuesta, corregido = await ayuda.responder(db, operador, texto, anterior, anterior_intencion, pregunta.pantalla)
    if respuesta is not None:
        return respuesta
    # Solo llega acá la gerencia: análisis de los datos, con la pregunta ya corregida y la anterior para seguimientos.
    analisis = asistente.responder(await inteligencia.contexto(db), corregido, anterior)
    return {**analisis, "pasos": [], "acciones": []}


@router.post("/pregunta")
async def preguntar(
    pregunta: Pregunta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    # Dos preguntas juntas («¿cuánto facturamos ayer y cuántos turnos hubo?»): una respuesta para cada una.
    partes = comprension.dividir(comprension.preparar(asistente.normalizar(pregunta.texto)))
    if len(partes) == 1:
        return await _una(db, operador, pregunta.texto, pregunta, pregunta.anterior, pregunta.anterior_intencion)
    # La segunda parte se entiende sobre la primera: «¿cuánto facturamos ayer y cuántos turnos hubo?» es ayer también.
    respuestas = [await _una(db, operador, partes[0], pregunta, pregunta.anterior, pregunta.anterior_intencion)]
    for parte in partes[1:3]:
        previa = respuestas[-1]
        anterior = previa.get("pregunta_resuelta") or partes[0]
        respuestas.append(await _una(db, operador, f"y {parte}", pregunta, anterior, previa["intencion"]))
    if any(r.get("confirmacion") for r in respuestas):
        # Una orden se confirma sola: se responde solo la primera parte.
        return respuestas[0]
    primera = respuestas[0]
    return {
        **primera,
        "respuesta": "\n\n".join(r["respuesta"] for r in respuestas),
        "tabla": next((r["tabla"] for r in respuestas if r.get("tabla")), None),
        "detalle": " ".join(r["detalle"] for r in respuestas if r.get("detalle")) or None,
        "acciones": [a for r in respuestas for a in r.get("acciones", [])][:4],
        "entendido": " + ".join(r["entendido"] for r in respuestas if r.get("entendido")) or None,
        "pregunta_resuelta": respuestas[-1].get("pregunta_resuelta"),
    }
