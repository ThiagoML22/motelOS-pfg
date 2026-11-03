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
from app.models.configuracion import ConfiguracionCaja
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.schemas.configuracion import TarifaCreate

CENTAVO = Decimal("0.01")


async def tarifa_vigente(db: AsyncSession) -> Tarifa | None:
    return (await db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)))).scalars().first()


async def cambiar_tarifa(db: AsyncSession, datos: TarifaCreate, operador: Operador) -> Tarifa:
    """Crea la tarifa nueva y deja de usar la anterior, que no se edita: los turnos que la usaron la conservan."""
    ahora = datetime.now(UTC)
    # Bloquea la tarifa vigente: dos cambios simultáneos se ordenan y no quedan dos tarifas vigentes.
    anteriores = (await db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)).with_for_update())).scalars().all()
    for anterior in anteriores:
        anterior.vigente = False
    await db.flush()
    nueva = Tarifa(
        nombre=f"Vigente desde {ahora:%Y-%m-%d %H:%M:%S.%f}",
        tarifa_base=Decimal(str(datos.tarifa_base)).quantize(CENTAVO),
        estadia_base_min=datos.estadia_base_min,
        # El establecimiento no aplica tolerancia (catálogo, RF-03): el panel no la ofrece.
        tolerancia_min=0,
        fraccion_min=datos.fraccion_min,
        tarifa_fraccion=Decimal(str(datos.tarifa_fraccion)).quantize(CENTAVO),
        vigente=True,
        vigente_desde=ahora,
        creada_por_id=operador.id,
    )
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
    return await db.get(ConfiguracionCaja, 1)


async def fondo_de_cambio(db: AsyncSession) -> Decimal:
    """Monto con el que abre la próxima guardia.

    La migración 005 crea la fila con $25.000 (acta del 19/10/2026). Sin esa fila rige FONDO_INICIAL_CAJA, el
    valor de configuración del entorno.
    """
    configuracion = await configuracion_caja(db)
    return Decimal(str(configuracion.fondo_cambio)) if configuracion else settings.FONDO_INICIAL_CAJA


async def cambiar_fondo(db: AsyncSession, monto: float, operador: Operador) -> ConfiguracionCaja:
    """El monto nuevo lo toma la guardia siguiente; la guardia abierta conserva el suyo (fondo_inicial)."""
    configuracion = await configuracion_caja(db)
    if configuracion is None:
        # motel_app no puede crear la fila: la crea la migración 005.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La base no tiene la configuración de la caja: falta aplicar la migración 005.",
        )
    configuracion.fondo_cambio = Decimal(str(monto)).quantize(CENTAVO)
    configuracion.actualizado_en = datetime.now(UTC)
    configuracion.actualizado_por_id = operador.id
    await db.commit()
    await db.refresh(configuracion)
    return configuracion
