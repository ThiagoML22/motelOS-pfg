"""Inicio y cierre de sesión (RNF-04)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.api.v1.endpoints.guardias import guardia_publica
from app.core.config import settings
from app.core.database import get_db
from app.core.seguridad import (
    HASH_FICTICIO,
    borrar_cookie_sesion,
    crear_token,
    poner_cookie_sesion,
    verificar_clave,
)
from app.models.operador import Operador
from app.schemas.auth import LoginRequest, OperadorPublico, SesionResponse
from app.services.caja import guardia_abierta
from app.services.liquidacion import con_zona

router = APIRouter()

# Un único mensaje para usuario inexistente, inactivo o clave incorrecta: no revela cuál falló.
CREDENCIALES_INVALIDAS = "Usuario o clave incorrectos."


@router.post("/login", response_model=SesionResponse)
async def login(datos: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    ahora = datetime.now(UTC)
    usuario = datos.usuario.strip().lower()
    operador = (await db.execute(select(Operador).where(Operador.usuario == usuario))).scalars().first()

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

    poner_cookie_sesion(response, crear_token(operador.id, operador.rol, ahora))
    return await _sesion_de(db, operador)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    respuesta = Response(status_code=status.HTTP_204_NO_CONTENT)
    borrar_cookie_sesion(respuesta)
    return respuesta


@router.get("/sesion", response_model=SesionResponse)
async def sesion(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    return await _sesion_de(db, operador)


async def _sesion_de(db: AsyncSession, operador: Operador) -> SesionResponse:
    guardia = await guardia_abierta(db)
    return SesionResponse(
        operador=OperadorPublico.model_validate(operador),
        guardia=await guardia_publica(db, guardia, operador) if guardia else None,
    )
