"""Liquidación de un turno contra la base de datos (RN-DER-01, RN-DER-02 y RN-EXI-03)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services.billing_service import calcular_sobreturno


@dataclass(frozen=True)
class Liquidacion:
    minutos_transcurridos: int
    total_pagado: Decimal
    saldo_pendiente: Decimal


def con_zona(valor: datetime) -> datetime:
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)


async def liquidar_turno(db: AsyncSession, turno: Turno) -> Liquidacion:
    """Recalcula el sobreturno y el total de un turno en curso y devuelve su saldo pendiente.

    Los cambios quedan en la sesión; confirmarlos (commit) es responsabilidad de quien llama.
    """
    tarifa = await db.get(Tarifa, turno.tarifa_id)
    if tarifa is None:
        raise HTTPException(status_code=500, detail="El turno referencia una tarifa inexistente")

    fin = con_zona(turno.hora_fin) if turno.hora_fin else datetime.now(UTC)
    duracion = fin - con_zona(turno.hora_inicio)

    if turno.estado == "En Curso":
        sobreturno = calcular_sobreturno(duracion, tarifa.parametros())
        if sobreturno != turno.total_sobreturno:
            turno.total_sobreturno = sobreturno
        turno.total_general = turno.tarifa_base + turno.total_sobreturno + turno.total_consumos

    pagos = (await db.execute(select(Pago).where(Pago.turno_id == turno.id))).scalars().all()
    total_pagado = sum((Decimal(str(p.monto)) for p in pagos), Decimal("0"))
    saldo = Decimal(str(turno.total_general)) - total_pagado
    return Liquidacion(int(duracion.total_seconds() / 60), total_pagado, saldo)
