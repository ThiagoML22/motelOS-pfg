"""Panel de configuración de la gerencia (RF-11 ampliado, acta del 27/10/2026).

Se monta solo para el rol ADMINISTRADOR (main.py). Los conserjes se dan de alta y de baja en operadores.py.
Ningún cambio borra historia: las tarifas se reemplazan y los artículos y las habitaciones se dan de baja.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.articulo import Articulo
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.schemas.articulo import ArticuloResponse
from app.schemas.configuracion import (
    ArticuloConfiguracion,
    FondoCambio,
    FondoCambioResponse,
    HabitacionAlta,
    HabitacionConfiguracion,
    HabitacionConfiguracionResponse,
    TarifaCreate,
    TarifaResponse,
)
from app.services.configuracion import cambiar_fondo, cambiar_tarifa, configuracion_caja, fondo_de_cambio

router = APIRouter()


# --- Tarifa y fracción -----------------------------------------------------------------------------------------
@router.get("/tarifas", response_model=list[TarifaResponse])
async def listar_tarifas(db: AsyncSession = Depends(get_db)):
    """La vigente primero y después las anteriores, de la más nueva a la más vieja."""
    return (await db.execute(select(Tarifa).order_by(Tarifa.vigente.desc(), Tarifa.id.desc()))).scalars().all()


@router.post("/tarifas", response_model=TarifaResponse, status_code=status.HTTP_201_CREATED)
async def nueva_tarifa(
    datos: TarifaCreate, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    return await cambiar_tarifa(db, datos, operador)


# --- Fondo de cambio ---------------------------------------------------------------------------------------------
@router.get("/caja", response_model=FondoCambioResponse)
async def ver_fondo(db: AsyncSession = Depends(get_db)):
    configuracion = await configuracion_caja(db)
    if configuracion is None:
        return FondoCambioResponse(fondo_cambio=float(await fondo_de_cambio(db)))
    return configuracion


@router.patch("/caja", response_model=FondoCambioResponse)
async def nuevo_fondo(
    datos: FondoCambio, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    return await cambiar_fondo(db, datos.fondo_cambio, operador)


# --- Artículos y precios -----------------------------------------------------------------------------------------
@router.get("/articulos", response_model=list[ArticuloResponse])
async def listar_articulos(db: AsyncSession = Depends(get_db)):
    """Todos los artículos, también los dados de baja (la ventanilla solo ve los activos)."""
    return (await db.execute(select(Articulo).order_by(Articulo.descripcion))).scalars().all()


@router.patch("/articulos/{articulo_id}", response_model=ArticuloResponse)
async def configurar_articulo(articulo_id: int, datos: ArticuloConfiguracion, db: AsyncSession = Depends(get_db)):
    # El precio nuevo rige para los consumos siguientes: cada consumo guarda su precio_unitario (RN-DER-06).
    consulta = select(Articulo).where(Articulo.id == articulo_id).with_for_update()
    articulo = (await db.execute(consulta)).scalars().first()
    if articulo is None:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is None and campo != "categoria":
            raise HTTPException(status_code=422, detail=f"El campo {campo} no puede quedar vacío.")
        setattr(articulo, campo, valor)
    await db.commit()
    await db.refresh(articulo)
    return articulo


# --- Habitaciones ------------------------------------------------------------------------------------------------
@router.get("/habitaciones", response_model=list[HabitacionConfiguracionResponse])
async def listar_habitaciones(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(Habitacion).order_by(Habitacion.numero))).scalars().all()


async def _numero_libre(db: AsyncSession, numero: int, salvo_id: int | None = None) -> None:
    existente = (await db.execute(select(Habitacion).where(Habitacion.numero == numero))).scalars().first()
    if existente is not None and existente.id != salvo_id:
        raise HTTPException(status_code=409, detail=f"Ya existe la habitación {numero}.")


@router.post("/habitaciones", response_model=HabitacionConfiguracionResponse, status_code=status.HTTP_201_CREATED)
async def alta_habitacion(datos: HabitacionAlta, db: AsyncSession = Depends(get_db)):
    await _numero_libre(db, datos.numero)
    habitacion = Habitacion(numero=datos.numero, estado="Libre", activa=True)
    db.add(habitacion)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe la habitación {datos.numero}.") from None
    await db.refresh(habitacion)
    return habitacion


@router.patch("/habitaciones/{habitacion_id}", response_model=HabitacionConfiguracionResponse)
async def configurar_habitacion(
    habitacion_id: int, datos: HabitacionConfiguracion, db: AsyncSession = Depends(get_db)
):
    # Bloquea la habitación: no se abre un turno en ella mientras se cambia (la apertura también la bloquea).
    habitacion = (
        await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id).with_for_update())
    ).scalars().first()
    if habitacion is None:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
    cambia_numero = datos.numero is not None and datos.numero != habitacion.numero
    se_da_de_baja = datos.activa is False and habitacion.activa
    # La base aplica la misma regla (trigger_habitacion_configuracion, migración 005).
    if (cambia_numero or se_da_de_baja) and habitacion.estado == "Ocupada":
        raise HTTPException(status_code=409, detail="La habitación tiene un turno en curso.")
    if cambia_numero:
        await _numero_libre(db, datos.numero, salvo_id=habitacion.id)
        habitacion.numero = datos.numero
    if datos.activa is not None:
        habitacion.activa = datos.activa
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe la habitación {datos.numero}.") from None
    await db.refresh(habitacion)
    return habitacion
