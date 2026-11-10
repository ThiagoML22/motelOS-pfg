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
from app.models.actividad import ESTABLECIMIENTO, HABITACION, INVENTARIO
from app.models.articulo import Articulo
from app.models.establecimiento import Establecimiento
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.schemas.articulo import ArticuloResponse
from app.schemas.configuracion import (
    ActividadPendientes,
    ActividadResponse,
    ActividadRevision,
    ArticuloConfiguracion,
    EstablecimientoDatos,
    EstablecimientoResponse,
    FondoCambio,
    FondoCambioResponse,
    HabitacionAlta,
    HabitacionConfiguracion,
    HabitacionConfiguracionResponse,
    TarifaCreate,
    TarifaResponse,
)
from app.services import actividad
from app.services.actividad import pesos, registrar
from app.services.configuracion import cambiar_fondo, cambiar_tarifa, configuracion_caja, fondo_de_cambio

router = APIRouter()


# --- Datos del establecimiento (multiinquilino) ------------------------------------------------------------------
@router.get("/establecimiento", response_model=EstablecimientoResponse)
async def ver_establecimiento(operador: Operador = Depends(operador_actual), db: AsyncSession = Depends(get_db)):
    return await db.get(Establecimiento, operador.establecimiento_id)


@router.patch("/establecimiento", response_model=EstablecimientoResponse)
async def cambiar_establecimiento(
    datos: EstablecimientoDatos, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    """Nombre, domicilio, teléfono y leyenda del comprobante. El código y la suspensión son de la plataforma."""
    establecimiento = await db.get(Establecimiento, operador.establecimiento_id, with_for_update=True)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        valor = valor.strip() if isinstance(valor, str) else valor
        if campo == "nombre" and not valor:
            raise HTTPException(status_code=422, detail="El nombre no puede quedar vacío.")
        anterior = getattr(establecimiento, campo)
        if (anterior or None) == (valor or None):
            continue
        setattr(establecimiento, campo, valor or None)
        await registrar(
            db, operador, ESTABLECIMIENTO, "ESTABLECIMIENTO_DATOS", f"Cambio de {campo.replace('_', ' ')}",
            valor_anterior=anterior, valor_nuevo=valor or None,
        )
    await db.commit()
    await db.refresh(establecimiento)
    return establecimiento


# --- Registro de actividad (migración 007) --------------------------------------------------------------------------
@router.get("/actividad", response_model=list[ActividadResponse])
async def listar_actividad(
    categoria: str | None = None, pendientes: bool = False, db: AsyncSession = Depends(get_db)
):
    filas = await actividad.listar(db, categoria, pendientes)
    return [
        ActividadResponse(
            id=e.id,
            creado_en=e.creado_en,
            categoria=e.categoria,
            accion=e.accion,
            descripcion=e.descripcion,
            operador_id=e.operador_id,
            operador_nombre=nombre,
            guardia_id=e.guardia_id,
            articulo_id=e.articulo_id,
            cantidad=e.cantidad,
            valor_anterior=e.valor_anterior,
            valor_nuevo=e.valor_nuevo,
            requiere_revision=e.requiere_revision,
            revisado_en=e.revisado_en,
            revisado_por_nombre=revisor,
        )
        for e, nombre, revisor in filas
    ]


@router.get("/actividad/pendientes", response_model=ActividadPendientes)
async def actividad_pendiente(db: AsyncSession = Depends(get_db)):
    return ActividadPendientes(pendientes=await actividad.pendientes(db))


@router.post("/actividad/revision", response_model=ActividadPendientes)
async def revisar_actividad(
    datos: ActividadRevision, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    """Marca como vistas las entradas de los conserjes. Devuelve cuántas quedan pendientes."""
    await actividad.marcar_revisadas(db, operador, datos.ids)
    return ActividadPendientes(pendientes=await actividad.pendientes(db))


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


_ACCIONES_ARTICULO = {
    "precio_unitario": ("ARTICULO_PRECIO", "Precio", pesos),
    "stock_actual": ("ARTICULO_STOCK", "Stock corregido", lambda v: f"{v} u."),
    "descripcion": ("ARTICULO_DATOS", "Descripción", str),
    "categoria": ("ARTICULO_DATOS", "Categoría", lambda v: v or "—"),
    "activo": ("ARTICULO_ESTADO", "Estado", lambda v: "Activo" if v else "Dado de baja"),
}


@router.patch("/articulos/{articulo_id}", response_model=ArticuloResponse)
async def configurar_articulo(
    articulo_id: int,
    datos: ArticuloConfiguracion,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    # El precio nuevo rige para los consumos siguientes: cada consumo guarda su precio_unitario (RN-DER-06).
    consulta = select(Articulo).where(Articulo.id == articulo_id).with_for_update()
    articulo = (await db.execute(consulta)).scalars().first()
    if articulo is None:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if valor is None and campo != "categoria":
            raise HTTPException(status_code=422, detail=f"El campo {campo} no puede quedar vacío.")
        anterior = getattr(articulo, campo)
        if anterior == valor or (campo == "precio_unitario" and float(anterior) == float(valor)):
            continue
        setattr(articulo, campo, valor)
        accion, etiqueta, formato = _ACCIONES_ARTICULO[campo]
        await registrar(
            db, operador, INVENTARIO, accion, f"{etiqueta} de {articulo.descripcion} ({articulo.codigo})",
            articulo_id=articulo.id, valor_anterior=formato(anterior), valor_nuevo=formato(valor),
        )
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
async def alta_habitacion(
    datos: HabitacionAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    await _numero_libre(db, datos.numero)
    habitacion = Habitacion(numero=datos.numero, estado="Libre", activa=True)
    db.add(habitacion)
    await registrar(db, operador, HABITACION, "HABITACION_ALTA", f"Alta de la habitación {datos.numero}")
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe la habitación {datos.numero}.") from None
    await db.refresh(habitacion)
    return habitacion


@router.patch("/habitaciones/{habitacion_id}", response_model=HabitacionConfiguracionResponse)
async def configurar_habitacion(
    habitacion_id: int,
    datos: HabitacionConfiguracion,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
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
        await registrar(
            db, operador, HABITACION, "HABITACION_NUMERO", "Cambio de número de habitación",
            valor_anterior=str(habitacion.numero), valor_nuevo=str(datos.numero),
        )
        habitacion.numero = datos.numero
    if datos.activa is not None and datos.activa != habitacion.activa:
        habitacion.activa = datos.activa
        await registrar(
            db, operador, HABITACION, "HABITACION_ESTADO",
            f"{'Reactivación' if datos.activa else 'Baja'} de la habitación {habitacion.numero}",
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe la habitación {datos.numero}.") from None
    await db.refresh(habitacion)
    return habitacion
