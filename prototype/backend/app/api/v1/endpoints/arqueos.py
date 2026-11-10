"""Panel de la gerencia: arqueos confirmados, diferencias y TDC (RF-09). Solo rol ADMINISTRADOR."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.arqueo import ArqueoCaja
from app.models.establecimiento import Establecimiento
from app.models.operador import Operador
from app.schemas.caja import (
    ArqueoDetalle,
    ArqueoResultado,
    DeclaracionSupervisada,
    MetricasCaja,
    ResumenCategoria,
    ResumenMes,
)
from app.services import caja, informe_mensual, reportes, sellos
from app.services.comprobante import comprobante_arqueo

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


@router.get("/por-categoria", response_model=list[ResumenCategoria])
async def por_categoria(desde: date | None = None, hasta: date | None = None, db: AsyncSession = Depends(get_db)):
    """Turnos cobrados, ingresos y ocupación por categoría de habitación (migración 008)."""
    return await reportes.por_categoria(db, desde, hasta)


@router.get("/meses", response_model=list[ResumenMes])
async def meses(operador_id: int | None = None, db: AsyncSession = Depends(get_db)):
    """Resumen de los arqueos de cada mes (cantidad, TDC, faltantes y sobrantes), del más reciente al más antiguo."""
    return await reportes.resumen_por_mes(db, operador_id)


@router.get("/meses/{mes}/informe.pdf", response_class=Response)
async def informe_del_mes(
    mes: str = Path(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    operador_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    gerencia: Operador = Depends(operador_actual),
):
    """Informe de los arqueos del mes en PDF (resumen y cada guardia), para archivo o el contador."""
    arqueos, metrica = await informe_mensual.arqueos_del_mes(db, mes, operador_id)
    conserje = await caja.nombre_de(db, operador_id) if operador_id else None
    establecimiento = await db.get(Establecimiento, gerencia.establecimiento_id)
    return Response(
        content=informe_mensual.informe_pdf(mes, arqueos, metrica, establecimiento, conserje),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="arqueos-{mes}.pdf"'},
    )


@router.get("/integridad")
async def integridad(db: AsyncSession = Depends(get_db)) -> dict:
    """Recalcula la huella de todos los comprobantes y dice cuáles ya no coinciden (migración 012)."""
    return await sellos.verificar_cadena(db)


@router.get("/verificar/{codigo}")
async def verificar(codigo: str = Path(max_length=80), db: AsyncSession = Depends(get_db)) -> dict:
    """Busca un comprobante por el código impreso y recalcula su huella."""
    return await sellos.verificar_codigo(db, codigo)


@router.get("/{arqueo_id}", response_model=ArqueoDetalle)
async def detalle(arqueo_id: int, db: AsyncSession = Depends(get_db)):
    arqueo = await db.get(ArqueoCaja, arqueo_id)
    if arqueo is None:
        raise HTTPException(status_code=404, detail="Arqueo no encontrado")
    return await reportes.detalle_de_arqueo(db, arqueo)


@router.get("/{arqueo_id}/comprobante.pdf", response_class=Response)
async def comprobante(arqueo_id: int, db: AsyncSession = Depends(get_db)):
    """RF-10: el comprobante del arqueo en PDF, para imprimir y firmar."""
    arqueo = await db.get(ArqueoCaja, arqueo_id)
    if arqueo is None:
        raise HTTPException(status_code=404, detail="Arqueo no encontrado")
    return await respuesta_pdf(db, arqueo)


async def respuesta_pdf(db: AsyncSession, arqueo: ArqueoCaja) -> Response:
    detalle = await reportes.detalle_de_arqueo(db, arqueo)
    establecimiento = await db.get(Establecimiento, arqueo.establecimiento_id)
    return Response(
        content=comprobante_arqueo(detalle, establecimiento),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="arqueo-{arqueo.id}.pdf"'},
    )


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
