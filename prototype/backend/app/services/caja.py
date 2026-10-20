"""Guardias y cierre de caja ciego (RF-08, RF-09).

Reglas:
- RN-RES-03: ninguna respuesta muestra el total del sistema de una guardia abierta. El total se calcula
  recién al confirmar el recuento físico, dentro de la misma transacción que guarda el arqueo.
- RN-DER-03: diferencia = total declarado - total del sistema; 0 es «Correcto», negativa «Faltante» y
  positiva «Sobrante».
- RN-DER-04: un pago se imputa a la guardia abierta en la ventanilla cuando se registra el cobro, aunque
  el turno lo haya abierto la guardia anterior.

En PostgreSQL la base vuelve a calcular el total del sistema, la diferencia y la categoría al insertar el
arqueo (trigger calcular_arqueo) y es la autoridad: este módulo hace el mismo cálculo para responder y para
las pruebas sin PostgreSQL.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.operador import Operador
from app.models.pago import Pago
from app.services.liquidacion import con_zona

CORRECTO = "Correcto"
FALTANTE = "Faltante"
SOBRANTE = "Sobrante"
CENTAVO = Decimal("0.01")


def franja_para(momento: datetime, anticipacion_min: int | None = None, zona: str | None = None) -> str:
    """Franja de 8 h (06:00, 14:00 o 22:00) que corresponde a una guardia abierta en `momento`.

    Se admite abrir la guardia hasta `anticipacion_min` minutos antes de su hora de inicio: a las 21:30 se
    abre la guardia de las 22:00, y a las 13:50, la de las 14:00.
    """
    anticipacion = settings.GUARDIA_ANTICIPACION_MIN if anticipacion_min is None else anticipacion_min
    local = con_zona(momento).astimezone(ZoneInfo(zona or settings.ZONA_HORARIA)) + timedelta(minutes=anticipacion)
    if 6 <= local.hour < 14:
        return "06:00"
    if 14 <= local.hour < 22:
        return "14:00"
    return "22:00"


def clasificar_diferencia(total_declarado: Decimal, total_sistema: Decimal) -> tuple[Decimal, str]:
    """RN-DER-03: diferencia y categoría de un arqueo."""
    diferencia = (Decimal(total_declarado) - Decimal(total_sistema)).quantize(CENTAVO)
    if diferencia == 0:
        return diferencia, CORRECTO
    return diferencia, FALTANTE if diferencia < 0 else SOBRANTE


@dataclass(frozen=True)
class TotalesCaja:
    efectivo: Decimal
    posnet: Decimal
    mercado_pago: Decimal

    @property
    def total(self) -> Decimal:
        return self.efectivo + self.posnet + self.mercado_pago


async def guardia_abierta(db: AsyncSession, bloquear: bool = False) -> Guardia | None:
    consulta = select(Guardia).where(Guardia.estado == "Abierta")
    if bloquear:
        consulta = consulta.with_for_update()
    return (await db.execute(consulta)).scalars().first()


async def nombre_de(db: AsyncSession, operador_id: int) -> str:
    operador = await db.get(Operador, operador_id)
    return operador.nombre_visible if operador else "—"


async def guardia_del_operador(db: AsyncSession, operador: Operador) -> Guardia:
    """La guardia abierta del operador de la sesión; si no la tiene, la operación no se permite (409).

    Sin esta condición un cobro quedaría fuera de toda caja y ningún arqueo lo controlaría.
    """
    guardia = await guardia_abierta(db)
    if guardia is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay una guardia abierta. Abra su guardia antes de operar la ventanilla.",
        )
    if guardia.operador_id != operador.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La guardia abierta es de {await nombre_de(db, guardia.operador_id)}. "
                "Debe cerrarla con su arqueo antes de que otro operador atienda la ventanilla."
            ),
        )
    return guardia


async def abrir_guardia(db: AsyncSession, operador: Operador, ahora: datetime | None = None) -> Guardia:
    abierta = await guardia_abierta(db)
    if abierta is not None:
        quien = "usted" if abierta.operador_id == operador.id else await nombre_de(db, abierta.operador_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya hay una guardia abierta (de {quien}). Solo puede haber una por ventanilla.",
        )
    momento = ahora or datetime.now(UTC)
    guardia = Guardia(
        operador_id=operador.id,
        franja=franja_para(momento),
        fondo_inicial=settings.FONDO_INICIAL_CAJA,
        abierta_en=momento,
        estado="Abierta",
    )
    db.add(guardia)
    try:
        await db.commit()
    except IntegrityError:
        # Dos aperturas simultáneas: el índice único de la base deja pasar solo una.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya hay una guardia abierta.") from None
    await db.refresh(guardia)
    return guardia


async def totales_del_sistema(db: AsyncSession, guardia: Guardia) -> TotalesCaja:
    """Lo que la caja debería tener según los pagos imputados a la guardia, más el fondo en efectivo."""
    filas = (
        await db.execute(
            select(Pago.medio_pago, func.coalesce(func.sum(Pago.monto), 0))
            .where(Pago.guardia_id == guardia.id)
            .group_by(Pago.medio_pago)
        )
    ).all()
    por_medio = {medio: Decimal(str(monto)) for medio, monto in filas}
    return TotalesCaja(
        efectivo=(Decimal(str(guardia.fondo_inicial)) + por_medio.get("EFECTIVO", Decimal("0"))).quantize(CENTAVO),
        posnet=por_medio.get("POSNET", Decimal("0")).quantize(CENTAVO),
        mercado_pago=por_medio.get("MERCADO_PAGO", Decimal("0")).quantize(CENTAVO),
    )


async def confirmar_arqueo(
    db: AsyncSession, operador: Operador, efectivo: Decimal, posnet: Decimal, mercado_pago: Decimal
) -> ArqueoCaja:
    """RF-08: guarda el recuento físico, calcula la diferencia (RF-09) y cierra la guardia, todo junto."""
    guardia = await guardia_abierta(db, bloquear=True)
    if guardia is None or guardia.operador_id != operador.id:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No tiene una guardia abierta para arquear."
        )
    return await _registrar_arqueo(db, guardia, operador, efectivo, posnet, mercado_pago, None)


async def _registrar_arqueo(
    db: AsyncSession,
    guardia: Guardia,
    confirma: Operador,
    efectivo: Decimal,
    posnet: Decimal,
    mercado_pago: Decimal,
    observacion: str | None,
) -> ArqueoCaja:
    sistema = await totales_del_sistema(db, guardia)
    declarado = (efectivo + posnet + mercado_pago).quantize(CENTAVO)
    diferencia, categoria = clasificar_diferencia(declarado, sistema.total)

    arqueo = ArqueoCaja(
        guardia_id=guardia.id,
        operador_id=guardia.operador_id,
        confirmado_por_id=confirma.id,
        observacion=observacion,
        declarado_efectivo=efectivo,
        declarado_posnet=posnet,
        declarado_mercado_pago=mercado_pago,
        total_declarado=declarado,
        sistema_efectivo=sistema.efectivo,
        sistema_posnet=sistema.posnet,
        sistema_mercado_pago=sistema.mercado_pago,
        total_sistema=sistema.total,
        diferencia=diferencia,
        categoria=categoria,
    )
    db.add(arqueo)
    # El arqueo se inserta antes de cerrar la guardia: en la base, una guardia no se cierra sin su arqueo.
    await db.flush()
    guardia.estado = "Cerrada"
    guardia.cerrada_en = datetime.now(UTC)
    await db.commit()
    await db.refresh(arqueo)  # trae los valores que calculó la base
    return arqueo
