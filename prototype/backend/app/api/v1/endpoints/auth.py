"""Inicio y cierre de sesión (RNF-04)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.api.v1.endpoints.guardias import guardia_publica
from app.core.config import settings
from app.core.database import get_db
from app.core.inquilino import PLATAFORMA, fijar_establecimiento
from app.core.seguridad import (
    HASH_FICTICIO,
    borrar_cookie_sesion,
    crear_token,
    poner_cookie_sesion,
    verificar_clave,
)
from app.models.establecimiento import Establecimiento
from app.models.operador import ROL_PLATAFORMA, Operador
from app.schemas.auth import EstablecimientoPublico, LoginRequest, MarcaPublica, OperadorPublico, SesionResponse
from app.services.caja import guardia_abierta
from app.services.liquidacion import con_zona

router = APIRouter()

# Un único mensaje para establecimiento o usuario inexistente, inactivo o clave incorrecta: no revela cuál falló.
CREDENCIALES_INVALIDAS = "Establecimiento, usuario o clave incorrectos."
CODIGO_PLATAFORMA = "plataforma"


async def _establecimiento_del_login(db: AsyncSession, codigo: str | None) -> int | None:
    """Id del establecimiento activo con ese código (0 para la plataforma), o None si no hay ninguno."""
    codigo = (codigo or "").strip().lower() or settings.ESTABLECIMIENTO_PREDETERMINADO
    if codigo == CODIGO_PLATAFORMA:
        return PLATAFORMA
    establecimiento = (
        await db.execute(select(Establecimiento).where(Establecimiento.codigo == codigo))
    ).scalars().first()
    return establecimiento.id if establecimiento and establecimiento.activo else None


@router.post("/login", response_model=SesionResponse)
async def login(datos: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    ahora = datetime.now(UTC)
    usuario = datos.usuario.strip().lower()
    establecimiento_id = await _establecimiento_del_login(db, datos.establecimiento)
    operador = None
    if establecimiento_id is not None:
        # Desde acá la sesión solo ve los usuarios de ese establecimiento (en PostgreSQL, también por RLS).
        await fijar_establecimiento(db, establecimiento_id)
        operador = (await db.execute(select(Operador).where(Operador.usuario == usuario))).scalars().first()
        if operador is not None and (operador.rol == ROL_PLATAFORMA) != (establecimiento_id == PLATAFORMA):
            operador = None

    if operador is None or not operador.activo:
        verificar_clave(HASH_FICTICIO, datos.clave)  # mismo tiempo de respuesta que un usuario real
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=CREDENCIALES_INVALIDAS)

    if operador.bloqueado_hasta is not None and con_zona(operador.bloqueado_hasta) > ahora:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Usuario bloqueado temporalmente por intentos fallidos. Intente más tarde o avise a la gerencia.",
        )

    if not verificar_clave(operador.hash_clave, datos.clave):
        # Incremento atómico en la base (intentos = intentos + 1): dos intentos simultáneos cuentan como dos.
        intentos = (
            await db.execute(
                update(Operador)
                .where(Operador.id == operador.id)
                .values(intentos_fallidos=Operador.intentos_fallidos + 1)
                .returning(Operador.intentos_fallidos)
            )
        ).scalar_one()
        if intentos >= settings.LOGIN_MAX_INTENTOS:
            await db.execute(
                update(Operador)
                .where(Operador.id == operador.id)
                .values(bloqueado_hasta=ahora + timedelta(minutes=settings.LOGIN_BLOQUEO_MIN), intentos_fallidos=0)
            )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=CREDENCIALES_INVALIDAS)

    operador.intentos_fallidos = 0
    operador.bloqueado_hasta = None
    operador.ultimo_acceso = ahora
    await db.commit()

    poner_cookie_sesion(response, crear_token(operador.id, operador.rol, establecimiento_id, ahora))
    return await _sesion_de(db, operador)


@router.get("/marca", response_model=MarcaPublica)
async def marca(codigo: str = Query(min_length=1, max_length=30), db: AsyncSession = Depends(get_db)):
    """Nombre y apariencia de un motel para la pantalla de ingreso (migración 009), sin sesión.

    El código identifica al comercio y no es secreto (como su nombre en el cartel); no dice nada de sus usuarios. Un
    código inexistente o suspendido responde 404.
    """
    establecimiento = (
        await db.execute(select(Establecimiento).where(Establecimiento.codigo == codigo.strip().lower()))
    ).scalars().first()
    if establecimiento is None or not establecimiento.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay un establecimiento con ese código.")
    return establecimiento


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    borrar_cookie_sesion(respuesta)
    return respuesta


@router.get("/sesion", response_model=SesionResponse)
async def sesion(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    return await _sesion_de(db, operador)


async def _sesion_de(db: AsyncSession, operador: Operador) -> SesionResponse:
    if operador.rol == ROL_PLATAFORMA:
        return SesionResponse(operador=OperadorPublico.model_validate(operador))
    establecimiento = await db.get(Establecimiento, operador.establecimiento_id)
    guardia = await guardia_abierta(db)
    return SesionResponse(
        operador=OperadorPublico.model_validate(operador),
        establecimiento=EstablecimientoPublico.model_validate(establecimiento),
        guardia=await guardia_publica(db, guardia, operador) if guardia else None,
    )
