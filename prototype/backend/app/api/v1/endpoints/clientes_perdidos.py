"""Clientes perdidos (migración 011): el conserje registra al cliente que se fue sin quedarse."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.categoria import CategoriaHabitacion
from app.models.cliente_perdido import MOTIVOS, SIN_LUGAR, ClientePerdido
from app.models.operador import Operador
from app.services.caja import guardia_del_operador

router = APIRouter()


class ClientePerdidoAlta(BaseModel):
    motivo: str = SIN_LUGAR
    categoria_id: int | None = None


@router.post("/", status_code=status.HTTP_201_CREATED)
async def registrar(
    datos: ClientePerdidoAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    if datos.motivo not in MOTIVOS:
        raise HTTPException(status_code=422, detail="Motivo desconocido.")
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
            motivo=datos.motivo, categoria_id=datos.categoria_id, operador_id=operador.id, guardia_id=guardia.id
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
