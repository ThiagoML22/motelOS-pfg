"""Guardias del operador y cierre de caja ciego (RF-08, RN-RES-03)."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual, requiere_rol
from app.api.v1.endpoints.arqueos import respuesta_pdf
from app.core.config import settings
from app.core.database import get_db
from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.operador import ROL_OPERADOR, Operador
from app.schemas.caja import ArqueoResultado, DeclaracionCaja, GuardiaPublica
from app.services import caja, ropa, traspasos
from app.services.reportes import resultado_de_arqueo

router = APIRouter()
solo_conserje = requiere_rol(ROL_OPERADOR)


class ConteoPrenda(BaseModel):
    """Toda la ropa del motel: limpia, sucia y puesta en las habitaciones."""

    prenda: Literal["TOALLAS", "SABANAS"]
    limpias: int = Field(ge=0, le=100000)
    sucias: int = Field(ge=0, le=100000)
    en_habitaciones: int = Field(ge=0, le=100000)


class RecuentoRopa(BaseModel):
    conteos: list[ConteoPrenda] = Field(min_length=1, max_length=4)


class AperturaGuardia(RecuentoRopa):
    """Lo que confirma quien entra: lo vio en el traspaso y lo contó."""


async def guardia_publica(db: AsyncSession, guardia: Guardia, operador: Operador) -> GuardiaPublica:
    return GuardiaPublica(
        id=guardia.id,
        franja=guardia.franja,
        estado=guardia.estado,
        abierta_en=guardia.abierta_en,
        cerrada_en=guardia.cerrada_en,
        operador_id=guardia.operador_id,
        operador_nombre=await caja.nombre_de(db, guardia.operador_id),
        fondo_inicial=float(guardia.fondo_inicial),
        es_propia=guardia.operador_id == operador.id,
    )


@router.get("/actual", response_model=GuardiaPublica | None)
async def guardia_actual(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    """La guardia abierta en la ventanilla, sin importes: ni el operador ni la gerencia ven su total."""
    guardia = await caja.guardia_abierta(db)
    return await guardia_publica(db, guardia, operador) if guardia else None


@router.get("/traspaso")
async def traspaso(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)) -> dict:
    """Lo que deja o recibe el conserje, sin importes ni patentes. La ropa no se muestra a quien cierra."""
    return await traspasos.para_la_pantalla(db, operador)


@router.post("/", response_model=GuardiaPublica, status_code=status.HTTP_201_CREATED)
async def abrir_guardia(
    datos: AperturaGuardia | None = None,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(solo_conserje),
):
    """Solo un conserje abre una guardia: la gerencia hace el control de caja (acta del 19/10/2026, punto 3). Quien
    entra confirma lo que recibe, en la misma transacción."""
    if datos is None and settings.EXIGIR_RECUENTO_ROPA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Para abrir la guardia hay que confirmar lo que se recibe."
        )

    async def recibir(guardia: Guardia) -> None:
        if datos is not None:
            await traspasos.registrar_recepcion(db, guardia, operador, [c.model_dump() for c in datos.conteos])

    guardia = await caja.abrir_guardia(db, operador, al_abrir=recibir)
    return await guardia_publica(db, guardia, operador)


@router.post("/actual/ropa", status_code=status.HTTP_201_CREATED)
async def recuento_de_ropa(
    datos: RecuentoRopa, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    """El recuento de cierre, a ciegas: recién esta respuesta dice si coincide con lo que debería haber."""
    return {"prendas": await ropa.recuento_de_cierre(db, operador, [c.model_dump() for c in datos.conteos])}


@router.post("/actual/arqueo", response_model=ArqueoResultado, status_code=status.HTTP_201_CREATED)
async def confirmar_arqueo(
    declaracion: DeclaracionCaja,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    """RF-08: el operador confirma su recuento físico. Recién esta respuesta incluye el total del sistema."""
    arqueo = await caja.confirmar_arqueo(
        db, operador, declaracion.efectivo, declaracion.posnet, declaracion.mercado_pago
    )
    return await resultado_de_arqueo(db, arqueo)


@router.get("/arqueos/{arqueo_id}/comprobante.pdf", response_class=Response)
async def comprobante_propio(
    arqueo_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    """RF-10: el conserje descarga el comprobante de su propio arqueo (ya confirmado: no expone una caja abierta)."""
    arqueo = await db.get(ArqueoCaja, arqueo_id)
    if arqueo is None or arqueo.operador_id != operador.id:
        raise HTTPException(status_code=404, detail="Arqueo no encontrado")
    return await respuesta_pdf(db, arqueo)
