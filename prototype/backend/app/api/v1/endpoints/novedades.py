"""Novedades de guardia (migración 009): notas que el personal deja para el turno siguiente y para la gerencia."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.novedad import Novedad
from app.models.operador import ROL_OPERADOR, Operador
from app.services.caja import guardia_abierta

router = APIRouter()


class NovedadAlta(BaseModel):
    texto: str = Field(min_length=1, max_length=500)
    importante: bool = False
    habitacion_id: int | None = None


class NovedadResponse(BaseModel):
    id: int
    texto: str
    importante: bool
    creado_en: datetime
    operador_id: int
    operador_nombre: str
    guardia_id: int | None = None
    franja: str | None = None
    habitacion_id: int | None = None
    habitacion_numero: int | None = None


async def _respuestas(db: AsyncSession, novedades: list[Novedad]) -> list[NovedadResponse]:
    nombres = {i: n for i, n in (await db.execute(select(Operador.id, Operador.nombre_visible))).all()}
    numeros = {i: n for i, n in (await db.execute(select(Habitacion.id, Habitacion.numero))).all()}
    ids_guardia = {n.guardia_id for n in novedades if n.guardia_id}
    franjas = (
        {
            i: f
            for i, f in (await db.execute(select(Guardia.id, Guardia.franja).where(Guardia.id.in_(ids_guardia)))).all()
        }
        if ids_guardia
        else {}
    )
    return [
        NovedadResponse(
            id=n.id,
            texto=n.texto,
            importante=n.importante,
            creado_en=n.creado_en,
            operador_id=n.operador_id,
            operador_nombre=nombres.get(n.operador_id, "—"),
            guardia_id=n.guardia_id,
            franja=franjas.get(n.guardia_id),
            habitacion_id=n.habitacion_id,
            habitacion_numero=numeros.get(n.habitacion_id),
        )
        for n in novedades
    ]


@router.get("/", response_model=list[NovedadResponse])
async def listar(limite: int = Query(default=30, ge=1, le=200), db: AsyncSession = Depends(get_db)):
    novedades = list(
        (
            await db.execute(select(Novedad).order_by(Novedad.creado_en.desc(), Novedad.id.desc()).limit(limite))
        ).scalars()
    )
    return await _respuestas(db, novedades)


@router.post("/", response_model=NovedadResponse, status_code=status.HTTP_201_CREATED)
async def crear(datos: NovedadAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    texto = datos.texto.strip()
    if not texto:
        raise HTTPException(status_code=422, detail="Escriba la novedad.")
    guardia = await guardia_abierta(db)
    propia = guardia if guardia is not None and guardia.operador_id == operador.id else None
    if operador.rol == ROL_OPERADOR and propia is None:
        raise HTTPException(status_code=409, detail="Abra su guardia para dejar una novedad.")
    # Una consulta (no db.get, que puede responder desde la sesión sin el filtro de establecimiento).
    if (
        datos.habitacion_id is not None
        and not (await db.execute(select(Habitacion.id).where(Habitacion.id == datos.habitacion_id))).first()
    ):
        raise HTTPException(status_code=404, detail="La habitación no existe.")
    novedad = Novedad(
        operador_id=operador.id,
        guardia_id=propia.id if propia else None,
        habitacion_id=datos.habitacion_id,
        texto=texto,
        importante=datos.importante,
    )
    db.add(novedad)
    await db.commit()
    await db.refresh(novedad)
    return (await _respuestas(db, [novedad]))[0]
