"""Perfil de cada usuario (migración 008): nombre visible, clave propia y restablecimiento por la gerencia.

motel_app no puede escribir hash_clave (migración 005). En PostgreSQL la clave la cambian dos funciones de la base que
solo actúan sobre el usuario de la sesión (app.operador_id, tomado del token) o, para la gerencia, sobre un conserje
de su establecimiento. La clave actual la verifica la aplicación con argon2id antes de llamarlas. En las pruebas
(sin esas funciones) el mismo cambio se hace con el ORM.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.inquilino import funcion_disponible
from app.core.seguridad import hashear_clave, verificar_clave
from app.models.actividad import PERFIL
from app.models.arqueo import ArqueoCaja
from app.models.establecimiento import Establecimiento
from app.models.guardia import Guardia
from app.models.operador import ROL_ADMINISTRADOR, ROL_OPERADOR, ROL_PLATAFORMA, Operador
from app.models.turno import Turno
from app.schemas.perfil import PerfilResponse
from app.services.actividad import registrar


async def perfil_de(db: AsyncSession, operador: Operador) -> PerfilResponse:
    establecimiento = (
        await db.get(Establecimiento, operador.establecimiento_id) if operador.establecimiento_id else None
    )
    desde = datetime.now(UTC) - timedelta(days=30)
    if operador.rol == ROL_PLATAFORMA:
        guardias = turnos = arqueos = 0
    else:
        guardias = (
            await db.execute(
                select(func.count()).select_from(Guardia).where(
                    Guardia.operador_id == operador.id, Guardia.abierta_en >= desde
                )
            )
        ).scalar_one()
        turnos = (
            await db.execute(
                select(func.count()).select_from(Turno).where(
                    Turno.operador_apertura_id == operador.id, Turno.hora_inicio >= desde
                )
            )
        ).scalar_one()
        arqueos = (
            await db.execute(
                select(func.count()).select_from(ArqueoCaja).where(
                    ArqueoCaja.operador_id == operador.id, ArqueoCaja.confirmado_en >= desde
                )
            )
        ).scalar_one()
    return PerfilResponse(
        id=operador.id,
        usuario=operador.usuario,
        nombre_visible=operador.nombre_visible,
        rol=operador.rol,
        establecimiento_nombre=establecimiento.nombre if establecimiento else None,
        establecimiento_codigo=establecimiento.codigo if establecimiento else None,
        creado_en=operador.creado_en,
        ultimo_acceso=operador.ultimo_acceso,
        guardias_30_dias=guardias,
        turnos_30_dias=turnos,
        arqueos_30_dias=arqueos,
    )


async def cambiar_nombre(db: AsyncSession, operador: Operador, nombre: str) -> Operador:
    nombre = nombre.strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="El nombre visible no puede quedar vacío.")
    if nombre != operador.nombre_visible:
        if operador.rol != ROL_PLATAFORMA:
            await registrar(
                db, operador, PERFIL, "PERFIL_NOMBRE", "Cambio del nombre visible",
                valor_anterior=operador.nombre_visible, valor_nuevo=nombre,
            )
        operador.nombre_visible = nombre
        await db.commit()
        await db.refresh(operador)
    return operador


async def cambiar_clave_propia(db: AsyncSession, operador: Operador, actual: str, nueva: str) -> None:
    if not verificar_clave(operador.hash_clave, actual):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La clave actual no es correcta.")
    if actual == nueva:
        raise HTTPException(status_code=422, detail="La clave nueva tiene que ser distinta de la actual.")
    hash_nuevo = hashear_clave(nueva)
    if await funcion_disponible(db, "cambiar_clave_propia(text)"):
        await db.execute(text("SELECT cambiar_clave_propia(:hash)"), {"hash": hash_nuevo})
    else:
        operador.hash_clave = hash_nuevo
        operador.intentos_fallidos = 0
        operador.bloqueado_hasta = None
    if operador.rol != ROL_PLATAFORMA:
        await registrar(db, operador, PERFIL, "CLAVE_PROPIA", "Cambio de la clave propia")
    await db.commit()


async def restablecer_clave(db: AsyncSession, gerencia: Operador, operador_id: int, nueva: str) -> Operador:
    """La gerencia pone una clave nueva a un conserje que la olvidó (y lo desbloquea). No ve la anterior."""
    if gerencia.rol != ROL_ADMINISTRADOR:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Su rol no permite esta operación.")
    conserje = await db.get(Operador, operador_id)
    if conserje is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operador no encontrado")
    if conserje.rol != ROL_OPERADOR:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se restablece la clave de un conserje. La propia se cambia desde Mi perfil.",
        )
    hash_nuevo = hashear_clave(nueva)
    if await funcion_disponible(db, "restablecer_clave_conserje(integer,text)"):
        await db.execute(
            text("SELECT restablecer_clave_conserje(:id, :hash)"), {"id": conserje.id, "hash": hash_nuevo}
        )
    else:
        conserje.hash_clave = hash_nuevo
        conserje.intentos_fallidos = 0
        conserje.bloqueado_hasta = None
    await registrar(
        db, gerencia, PERFIL, "CLAVE_RESTABLECIDA",
        f"Clave restablecida del conserje {conserje.nombre_visible} ({conserje.usuario})",
    )
    await db.commit()
    await db.refresh(conserje)
    return conserje
