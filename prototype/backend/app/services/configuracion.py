"""Tarifa y fondo de cambio que configura la gerencia (RF-11, RN-DER-06).

Un cambio rige hacia adelante: la tarifa nueva la toman los turnos que se abren después y el fondo nuevo, las
guardias que se abren después. Lo ya registrado conserva su valor porque el turno guarda su tarifa (tarifa_id y
tarifa_base) y la guardia su fondo (fondo_inicial) en el momento en que se abren.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.inquilino import establecimiento_de
from app.models.actividad import CAJA, TARIFA
from app.models.categoria import CategoriaHabitacion
from app.models.configuracion import ConfiguracionCaja
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.schemas.configuracion import ParametrosTarifa, TarifaCreate
from app.services.actividad import pesos, registrar

CENTAVO = Decimal("0.01")


def _resumen_tarifa(base, base_min, fraccion, fraccion_min) -> str:
    return f"{pesos(base)}/{base_min} min + {pesos(fraccion)}/{fraccion_min} min"


def _importe(valor) -> Decimal | None:
    return None if valor is None else Decimal(str(valor)).quantize(CENTAVO)


async def tarifa_vigente(db: AsyncSession, categoria_id: int | None = None) -> Tarifa | None:
    """La tarifa vigente de una categoría (migración 008); sin categoría, la de la primera."""
    if categoria_id is None:
        categoria = await categoria_por_defecto(db)
        if categoria is None:
            return None
        categoria_id = categoria.id
    consulta = select(Tarifa).where(Tarifa.vigente.is_(True), Tarifa.categoria_id == categoria_id)
    return (await db.execute(consulta)).scalars().first()


async def categoria_por_defecto(db: AsyncSession) -> CategoriaHabitacion | None:
    consulta = (
        select(CategoriaHabitacion)
        .where(CategoriaHabitacion.activa.is_(True))
        .order_by(CategoriaHabitacion.orden, CategoriaHabitacion.id)
    )
    return (await db.execute(consulta)).scalars().first()


async def categoria_activa(db: AsyncSession, categoria_id: int | None) -> CategoriaHabitacion:
    """La categoría indicada, que debe existir y estar activa; sin indicar, la primera del establecimiento."""
    categoria = await (categoria_por_defecto(db) if categoria_id is None else db.get(CategoriaHabitacion, categoria_id))
    if categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría de habitación no encontrada")
    if not categoria.activa:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"La categoría {categoria.nombre} está dada de baja."
        )
    return categoria


def nueva_tarifa_de(categoria: CategoriaHabitacion, datos: ParametrosTarifa, operador_id: int | None) -> Tarifa:
    ahora = datetime.now(UTC)
    return Tarifa(
        nombre=f"{categoria.id}·{ahora:%Y-%m-%d %H:%M:%S.%f}",
        categoria_id=categoria.id,
        tarifa_base=_importe(datos.tarifa_base),
        estadia_base_min=datos.estadia_base_min,
        # El catálogo vigente fija tolerancia 0 (RF-03); la demostración la deja configurable por categoría.
        tolerancia_min=datos.tolerancia_min,
        fraccion_min=datos.fraccion_min,
        tarifa_fraccion=_importe(datos.tarifa_fraccion),
        tope=_importe(datos.tope),
        vigente=True,
        vigente_desde=ahora,
        creada_por_id=operador_id,
    )


async def cambiar_tarifa(db: AsyncSession, datos: TarifaCreate, operador: Operador) -> Tarifa:
    """Crea la tarifa nueva de la categoría y deja de usar la anterior, que no se edita: los turnos que la usaron
    la conservan (RN-DER-06)."""
    categoria = await categoria_activa(db, datos.categoria_id)
    # Bloquea la tarifa vigente: dos cambios simultáneos se ordenan y no quedan dos tarifas vigentes.
    consulta = select(Tarifa).where(Tarifa.vigente.is_(True), Tarifa.categoria_id == categoria.id).with_for_update()
    anteriores = (await db.execute(consulta)).scalars().all()
    for anterior in anteriores:
        anterior.vigente = False
    await db.flush()
    previa = anteriores[0] if anteriores else None
    await registrar(
        db, operador, TARIFA, "TARIFA_NUEVA",
        f"Tarifa nueva de {categoria.nombre}: {datos.estadia_base_min} min por {pesos(datos.tarifa_base)}, fracción "
        f"de {datos.fraccion_min} min por {pesos(datos.tarifa_fraccion)}"
        + (f", tolerancia {datos.tolerancia_min} min" if datos.tolerancia_min else "")
        + (f", tope {pesos(datos.tope)}" if datos.tope else ""),
        valor_anterior=_resumen_tarifa(previa.tarifa_base, previa.estadia_base_min, previa.tarifa_fraccion,
                                       previa.fraccion_min) if previa else None,
        valor_nuevo=_resumen_tarifa(datos.tarifa_base, datos.estadia_base_min, datos.tarifa_fraccion,
                                    datos.fraccion_min),
    )
    nueva = nueva_tarifa_de(categoria, datos, operador.id)
    db.add(nueva)
    try:
        await db.commit()
    except IntegrityError:
        # El índice tarifas_una_vigente rechazó un cambio simultáneo: gana el primero.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Otro cambio de tarifa se registró al mismo tiempo."
        ) from None
    await db.refresh(nueva)
    return nueva


async def configuracion_caja(db: AsyncSession) -> ConfiguracionCaja | None:
    """La fila del establecimiento de la sesión (una por establecimiento desde la migración 006)."""
    establecimiento_id = establecimiento_de(db)
    return await db.get(ConfiguracionCaja, establecimiento_id) if establecimiento_id else None


async def fondo_de_cambio(db: AsyncSession) -> Decimal:
    """Monto con el que abre la próxima guardia.

    La migración 005 crea la fila con $25.000 (acta del 19/10/2026) y la plataforma crea la de cada establecimiento
    nuevo. Sin esa fila rige FONDO_INICIAL_CAJA, el valor de configuración del entorno.
    """
    configuracion = await configuracion_caja(db)
    return Decimal(str(configuracion.fondo_cambio)) if configuracion else settings.FONDO_INICIAL_CAJA


async def cambiar_fondo(db: AsyncSession, monto: float, operador: Operador) -> ConfiguracionCaja:
    """El monto nuevo lo toma la guardia siguiente; la guardia abierta conserva el suyo (fondo_inicial)."""
    configuracion = await configuracion_caja(db)
    if configuracion is None:
        # La fila la crea la migración 005 (establecimiento 1) o la plataforma al dar de alta el establecimiento.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El establecimiento no tiene la configuración de la caja.",
        )
    anterior = Decimal(str(configuracion.fondo_cambio))
    configuracion.fondo_cambio = Decimal(str(monto)).quantize(CENTAVO)
    configuracion.actualizado_en = datetime.now(UTC)
    configuracion.actualizado_por_id = operador.id
    await registrar(
        db, operador, CAJA, "FONDO_CAMBIO", "Cambio del fondo de cambio de la caja",
        valor_anterior=pesos(anterior), valor_nuevo=pesos(configuracion.fondo_cambio),
    )
    await db.commit()
    await db.refresh(configuracion)
    return configuracion
