from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.actividad import INVENTARIO
from app.models.articulo import Articulo
from app.models.operador import Operador
from app.schemas.articulo import ArticuloCreate, ArticuloResponse, Reposicion
from app.services.actividad import pesos, registrar

router = APIRouter()


@router.get("/", response_model=list[ArticuloResponse])
async def get_articulos(db: AsyncSession = Depends(get_db)):
    # Los artículos dados de baja solo se ven en el panel de configuración (RF-11).
    result = await db.execute(select(Articulo).where(Articulo.activo.is_(True)).order_by(Articulo.descripcion))
    return result.scalars().all()


# El alta de artículos la hace cualquier operador con sesión: el conserje no depende de la gerencia para cargar
# un artículo nuevo que llega a la ventanilla (decisión del autor, 27/10/2026). Modificar el precio y dar de
# baja un artículo es de la gerencia, desde el panel de configuración (RF-11). Lo que carga un conserje queda en
# el registro de actividad, «por revisar», hasta que la gerencia lo ve (migración 007).
@router.post("/", response_model=ArticuloResponse, status_code=status.HTTP_201_CREATED)
async def create_articulo(
    articulo_in: ArticuloCreate, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    query = await db.execute(select(Articulo).where(Articulo.codigo == articulo_in.codigo))
    if query.scalars().first():
        raise HTTPException(status_code=400, detail="El código de artículo ya existe.")

    nuevo_articulo = Articulo(**articulo_in.model_dump())
    db.add(nuevo_articulo)
    await db.flush()
    await registrar(
        db, operador, INVENTARIO, "ARTICULO_ALTA",
        f"Alta de {nuevo_articulo.descripcion} ({nuevo_articulo.codigo}) con {nuevo_articulo.stock_actual} "
        f"unidades a {pesos(nuevo_articulo.precio_unitario)}",
        articulo_id=nuevo_articulo.id, cantidad=nuevo_articulo.stock_actual,
        valor_nuevo=pesos(nuevo_articulo.precio_unitario),
    )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="El código de artículo ya existe.") from None
    await db.refresh(nuevo_articulo)
    return nuevo_articulo


@router.post("/{articulo_id}/reposicion", response_model=ArticuloResponse)
async def reponer(
    articulo_id: int,
    datos: Reposicion,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    """Suma unidades al stock de un artículo activo. El precio no cambia: eso es de la gerencia."""
    # Bloquea el artículo: una reposición y un consumo simultáneos no se pisan el stock.
    articulo = (
        await db.execute(select(Articulo).where(Articulo.id == articulo_id).with_for_update())
    ).scalars().first()
    if articulo is None or not articulo.activo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    anterior = articulo.stock_actual
    articulo.stock_actual = anterior + datos.cantidad
    await registrar(
        db, operador, INVENTARIO, "ARTICULO_REPOSICION",
        f"Reposición de {datos.cantidad} u. de {articulo.descripcion} ({articulo.codigo})",
        articulo_id=articulo.id, cantidad=datos.cantidad,
        valor_anterior=f"{anterior} u.", valor_nuevo=f"{articulo.stock_actual} u.",
    )
    await db.commit()
    await db.refresh(articulo)
    return articulo
