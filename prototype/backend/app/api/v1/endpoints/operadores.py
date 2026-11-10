"""Operadores para la gerencia: consulta, y alta y baja de conserjes desde el panel (RF-11, acta del 27/10/2026).

El alta crea siempre un conserje: la aplicación no elige el rol (migración 005). Los gerentes y el cambio de
claves siguen a cargo del dueño de las tablas, con scripts/crear_operador.py. La baja es lógica: las guardias,
los arqueos y los turnos a nombre del conserje quedan intactos, y su sesión deja de valer (deps.operador_actual).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.core.seguridad import hashear_clave
from app.models.actividad import PERSONAL
from app.models.guardia import Guardia
from app.models.operador import ROL_ADMINISTRADOR, Operador
from app.schemas.auth import OperadorPublico
from app.schemas.configuracion import ConserjeAlta, OperadorActivo
from app.schemas.perfil import ClaveRestablecida
from app.services import perfil
from app.services.actividad import registrar

router = APIRouter()


class OperadorEstado(OperadorPublico):
    activo: bool
    ultimo_acceso: datetime | None = None
    bloqueado_hasta: datetime | None = None


@router.get("/", response_model=list[OperadorEstado])
async def listar(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Operador).order_by(Operador.nombre_visible))).scalars().all()


@router.post("/", response_model=OperadorEstado, status_code=status.HTTP_201_CREATED)
async def alta_conserje(
    datos: ConserjeAlta, db: AsyncSession = Depends(get_db), gerencia: Operador = Depends(operador_actual)
):
    existente = (await db.execute(select(Operador).where(Operador.usuario == datos.usuario))).scalars().first()
    if existente is not None:
        raise HTTPException(status_code=409, detail=f"El usuario {datos.usuario} ya existe.")
    # Sin rol: lo pone la base (OPERADOR). motel_app no tiene permiso sobre esa columna.
    conserje = Operador(
        usuario=datos.usuario, nombre_visible=datos.nombre_visible.strip(), hash_clave=hashear_clave(datos.clave)
    )
    db.add(conserje)
    await registrar(
        db, gerencia, PERSONAL, "CONSERJE_ALTA", f"Alta del conserje {conserje.nombre_visible} ({datos.usuario})"
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"El usuario {datos.usuario} ya existe.") from None
    await db.refresh(conserje)
    return conserje


@router.post("/{operador_id}/clave", response_model=OperadorEstado)
async def restablecer_clave(
    operador_id: int,
    datos: ClaveRestablecida,
    db: AsyncSession = Depends(get_db),
    gerencia: Operador = Depends(operador_actual),
):
    """La gerencia pone una clave nueva a un conserje (migración 008) y le quita el bloqueo por intentos."""
    return await perfil.restablecer_clave(db, gerencia, operador_id, datos.nueva)


@router.patch("/{operador_id}", response_model=OperadorEstado)
async def cambiar_activo(
    operador_id: int,
    datos: OperadorActivo,
    db: AsyncSession = Depends(get_db),
    gerencia: Operador = Depends(operador_actual),
):
    operador = await db.get(Operador, operador_id)
    if operador is None:
        raise HTTPException(status_code=404, detail="Operador no encontrado")
    # La base aplica las mismas dos reglas (trigger_operador_baja, migración 005).
    if operador.rol == ROL_ADMINISTRADOR:
        raise HTTPException(status_code=409, detail="La gerencia no se da de alta ni de baja desde el panel.")
    if not datos.activo:
        abierta = (
            await db.execute(select(Guardia).where(Guardia.operador_id == operador.id, Guardia.estado == "Abierta"))
        ).scalars().first()
        if abierta is not None:
            raise HTTPException(
                status_code=409,
                detail="El conserje tiene su guardia abierta: se cierra (o se usa el cierre supervisado) antes de "
                "darlo de baja.",
            )
    if operador.activo != datos.activo:
        await registrar(
            db, gerencia, PERSONAL, "CONSERJE_ESTADO",
            f"{'Reactivación' if datos.activo else 'Baja'} del conserje {operador.nombre_visible} ({operador.usuario})",
        )
    operador.activo = datos.activo
    await db.commit()
    await db.refresh(operador)
    return operador
