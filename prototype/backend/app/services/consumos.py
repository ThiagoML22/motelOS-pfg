"""Cargar un consumo a un turno: lo usan la ventanilla y la atención de un pedido del cliente."""

import uuid
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.articulo import Articulo
from app.models.consumo import Consumo
from app.models.operador import Operador
from app.models.turno import Turno
from app.services.caja import guardia_del_operador


async def cargar_consumo(
    db: AsyncSession, turno_id: uuid.UUID, articulo_id: int, cantidad: int, operador: Operador
) -> Decimal:
    """Descuenta el stock y suma a la cuenta; lo guarda el commit de quien llama. Devuelve el subtotal."""
    # RN-EXI-02: Check stock and atomically add consumption
    # El turno se bloquea igual que en el cobro: un consumo y un cobro simultáneos no se intercalan.
    turno_res = await db.execute(select(Turno).where(Turno.id == turno_id).with_for_update())
    turno = turno_res.scalars().first()
    if not turno or turno.estado != "En Curso":
        raise HTTPException(status_code=400, detail="Turno no válido o no está en curso")

    await guardia_del_operador(db, operador)

    art_res = await db.execute(select(Articulo).where(Articulo.id == articulo_id).with_for_update())
    articulo = art_res.scalars().first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    if not articulo.activo:
        raise HTTPException(status_code=409, detail="El artículo está dado de baja.")

    if articulo.stock_actual < cantidad:
        raise HTTPException(
            status_code=400, detail=f"RN-EXI-02: Stock insuficiente. Stock actual: {articulo.stock_actual}"
        )

    # Descontar stock
    articulo.stock_actual -= cantidad

    subtotal = articulo.precio_unitario * cantidad

    db.add(
        Consumo(
            turno_id=turno_id,
            articulo_id=articulo.id,
            cantidad=cantidad,
            precio_unitario=articulo.precio_unitario,
            subtotal=subtotal,
            operador_id=operador.id,
        )
    )

    # Actualizar totales en turno
    turno.total_consumos += subtotal
    turno.total_general += subtotal
    return subtotal
