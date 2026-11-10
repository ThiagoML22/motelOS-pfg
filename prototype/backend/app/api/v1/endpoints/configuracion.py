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
from app.models.categoria import CategoriaHabitacion
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
    CategoriaAlta,
    CategoriaCambio,
    CategoriaResponse,
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
from app.services import actividad, categorias
from app.services.actividad import pesos, registrar
from app.services.configuracion import (
    cambiar_fondo,
    cambiar_tarifa,
    categoria_activa,
    configuracion_caja,
    fondo_de_cambio,
)

router = APIRouter()


# --- Datos del establecimiento (multiinquilino) ------------------------------------------------------------------
CAMPOS_ESTABLECIMIENTO = {
    "color_marca": "color de marca",
    "aviso_por_vencer_min": "aviso «por vencer» (minutos)",
    "alertas_sonoras": "alertas sonoras",
}


def _como_texto(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


@router.get("/establecimiento", response_model=EstablecimientoResponse)
async def ver_establecimiento(operador: Operador = Depends(operador_actual), db: AsyncSession = Depends(get_db)):
    return await db.get(Establecimiento, operador.establecimiento_id)


@router.patch("/establecimiento", response_model=EstablecimientoResponse)
async def cambiar_establecimiento(
    datos: EstablecimientoDatos, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    """Nombre, domicilio, teléfono, leyenda del comprobante, apariencia y avisos (migración 009). El código y la
    suspensión son de la plataforma."""
    establecimiento = await db.get(Establecimiento, operador.establecimiento_id, with_for_update=True)
    for campo, valor in datos.model_dump(exclude_unset=True).items():
        if isinstance(valor, str):
            valor = valor.strip() or None
        if campo == "color_marca" and valor:
            valor = valor.lower()
        if campo == "nombre" and not valor:
            raise HTTPException(status_code=422, detail="El nombre no puede quedar vacío.")
        if valor is None and campo in ("aviso_por_vencer_min", "alertas_sonoras"):
            continue  # no admiten vacío
        anterior = getattr(establecimiento, campo)
        if anterior == valor:
            continue
        setattr(establecimiento, campo, valor)
        await registrar(
            db, operador, ESTABLECIMIENTO, "ESTABLECIMIENTO_DATOS",
            f"Cambio de {CAMPOS_ESTABLECIMIENTO.get(campo, campo.replace('_', ' '))}",
            valor_anterior=_como_texto(anterior), valor_nuevo=_como_texto(valor),
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
async def listar_tarifas(categoria_id: int | None = None, db: AsyncSession = Depends(get_db)):
    """Las vigentes primero y después las anteriores, de la más nueva a la más vieja; opcionalmente de una categoría."""
    consulta = select(Tarifa).order_by(Tarifa.vigente.desc(), Tarifa.id.desc())
    if categoria_id is not None:
        consulta = consulta.where(Tarifa.categoria_id == categoria_id)
    return (await db.execute(consulta)).scalars().all()


@router.post("/tarifas", response_model=TarifaResponse, status_code=status.HTTP_201_CREATED)
async def nueva_tarifa(
    datos: TarifaCreate, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    return await cambiar_tarifa(db, datos, operador)


# --- Categorías de habitación (migración 008) -----------------------------------------------------------------------
@router.get("/categorias", response_model=list[CategoriaResponse])
async def listar_categorias(db: AsyncSession = Depends(get_db)):
    """Todas, también las dadas de baja, con su tarifa vigente y cuántas habitaciones activas tienen."""
    return await categorias.listar(db, solo_activas=False)


@router.post("/categorias", response_model=CategoriaResponse, status_code=status.HTTP_201_CREATED)
async def alta_categoria(
    datos: CategoriaAlta, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    nueva = await categorias.crear(db, datos, operador)
    return next(c for c in await categorias.listar(db, solo_activas=False) if c.id == nueva.id)


@router.patch("/categorias/{categoria_id}", response_model=CategoriaResponse)
async def cambiar_categoria(
    categoria_id: int,
    datos: CategoriaCambio,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    await categorias.cambiar(db, categoria_id, datos, operador)
    return next(c for c in await categorias.listar(db, solo_activas=False) if c.id == categoria_id)


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
    categoria = await categoria_activa(db, datos.categoria_id)
    habitacion = Habitacion(numero=datos.numero, estado="Libre", activa=True, categoria_id=categoria.id)
    db.add(habitacion)
    await registrar(
        db, operador, HABITACION, "HABITACION_ALTA", f"Alta de la habitación {datos.numero} ({categoria.nombre})"
    )
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
    if datos.categoria_id is not None and datos.categoria_id != habitacion.categoria_id:
        # El turno en curso, si lo hay, conserva su tarifa: la categoría nueva rige desde el turno siguiente.
        nueva = await categoria_activa(db, datos.categoria_id)
        anterior = await db.get(CategoriaHabitacion, habitacion.categoria_id)
        habitacion.categoria_id = nueva.id
        await registrar(
            db, operador, HABITACION, "HABITACION_CATEGORIA", f"Categoría de la habitación {habitacion.numero}",
            valor_anterior=anterior.nombre if anterior else None, valor_nuevo=nueva.nombre,
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Ya existe la habitación {datos.numero}.") from None
    await db.refresh(habitacion)
    return habitacion
