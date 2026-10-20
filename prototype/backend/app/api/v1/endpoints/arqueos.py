"""Panel de la gerencia: arqueos confirmados, diferencias y TDC (RF-09). Solo rol ADMINISTRADOR."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.arqueo import ArqueoCaja
from app.models.operador import Operador
from app.schemas.caja import ArqueoDetalle, ArqueoResultado, DeclaracionSupervisada, MetricasCaja
from app.services import caja, reportes

router = APIRouter()


@router.get("/", response_model=list[ArqueoResultado])
async def listar(
    desde: date | None = Query(default=None, description="Día inicial (hora local), inclusive"),
    hasta: date | None = Query(default=None, description="Día final (hora local), inclusive"),
    operador_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    arqueos = await reportes.listar_arqueos(db, desde, hasta, operador_id)
    return [await reportes.resultado_de_arqueo(db, a) for a in arqueos]


@router.get("/metricas", response_model=MetricasCaja)
async def metricas(
    desde: date | None = None,
    hasta: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await reportes.metricas(db, desde, hasta)


@router.get("/{arqueo_id}", response_model=ArqueoDetalle)
async def detalle(arqueo_id: int, db: AsyncSession = Depends(get_db)):
    arqueo = await db.get(ArqueoCaja, arqueo_id)
    if arqueo is None:
        raise HTTPException(status_code=404, detail="Arqueo no encontrado")
    return await reportes.detalle_de_arqueo(db, arqueo)


@router.post(
    "/guardias/{guardia_id}/cierre-supervisado",
    response_model=ArqueoResultado,
    status_code=status.HTTP_201_CREATED,
)
async def cierre_supervisado(
    guardia_id: int,
    declaracion: DeclaracionSupervisada,
    db: AsyncSession = Depends(get_db),
    gerencia: Operador = Depends(operador_actual),
):
    """Cierre de una guardia abandonada. La gerencia cuenta la gaveta sin ver el total (RN-RES-03)."""
    arqueo = await caja.cierre_supervisado(
        db,
        gerencia,
        guardia_id,
        declaracion.efectivo,
        declaracion.posnet,
        declaracion.mercado_pago,
        declaracion.observacion,
    )
    return await reportes.resultado_de_arqueo(db, arqueo)
