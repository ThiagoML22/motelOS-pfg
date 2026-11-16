"""Clientes perdidos (migraciones 011 y 018): el conserje registra al cliente que se fue sin quedarse."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.categoria import CategoriaHabitacion
from app.models.cliente_perdido import LARGO_DETALLE, MOTIVOS, OTRO, SIN_LUGAR, ClientePerdido
from app.models.operador import Operador
from app.services import moderacion
from app.services.caja import guardia_del_operador

router = APIRouter()


class ClientePerdidoAlta(BaseModel):
    motivo: str = SIN_LUGAR
    categoria_id: int | None = None
    # Solo con «Otro»: por qué se fue, en pocas palabras y sin datos de la persona.
    detalle: str | None = Field(default=None, max_length=LARGO_DETALLE)


def _detalle(datos: ClientePerdidoAlta) -> str | None:
    detalle = moderacion.limpiar(datos.detalle or "")
    if datos.motivo != OTRO:
        return None
    if not detalle:
        raise HTTPException(status_code=422, detail="Contá en pocas palabras por qué se fue.")
    motivo = moderacion.revisar(detalle)
    if motivo:
        raise HTTPException(status_code=422, detail=motivo)
    return detalle


@router.post("/", status_code=status.HTTP_201_CREATED)
async def registrar(
    datos: ClientePerdidoAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    if datos.motivo not in MOTIVOS:
        raise HTTPException(status_code=422, detail="Motivo desconocido.")
    detalle = _detalle(datos)
    # Solo quien atiende la ventanilla: sin guardia propia responde 409, como el resto de la operación.
    guardia = await guardia_del_operador(db, operador)
    if (
        datos.categoria_id is not None
        and not (
            await db.execute(select(CategoriaHabitacion.id).where(CategoriaHabitacion.id == datos.categoria_id))
        ).first()
    ):
        raise HTTPException(status_code=404, detail="La categoría no existe.")
    db.add(
        ClientePerdido(
            motivo=datos.motivo,
            detalle=detalle,
            categoria_id=datos.categoria_id,
            operador_id=operador.id,
            guardia_id=guardia.id,
        )
    )
    await db.flush()
    en_la_guardia = (
        await db.execute(
            select(func.count()).select_from(ClientePerdido).where(ClientePerdido.guardia_id == guardia.id)
        )
    ).scalar_one()
    await db.commit()
    return {"en_la_guardia": en_la_guardia}
