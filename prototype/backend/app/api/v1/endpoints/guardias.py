"""Guardias del operador y cierre de caja ciego (RF-08, RN-RES-03)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.guardia import Guardia
from app.models.operador import Operador
from app.schemas.caja import ArqueoResultado, DeclaracionCaja, GuardiaPublica
from app.services import caja
from app.services.reportes import resultado_de_arqueo

router = APIRouter()


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


@router.post("/", response_model=GuardiaPublica, status_code=status.HTTP_201_CREATED)
async def abrir_guardia(db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)):
    guardia = await caja.abrir_guardia(db, operador)
    return await guardia_publica(db, guardia, operador)


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
