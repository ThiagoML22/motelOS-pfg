import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.articulo import Articulo
from app.models.consumo import Consumo
from app.models.habitacion import Habitacion
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.schemas.articulo import ConsumoCreate
from app.schemas.turno import (
    CierreTurnoCreate,
    ConstanciaCobro,
    PagoConstancia,
    TurnoCreate,
    TurnoResponse,
    TurnoResumen,
)
from app.services.liquidacion import liquidar_turno

router = APIRouter()


@router.post("/", response_model=TurnoResponse, status_code=status.HTTP_201_CREATED)
async def create_turno(turno_in: TurnoCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Habitacion).where(Habitacion.id == turno_in.habitacion_id))
    habitacion = result.scalars().first()

    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    if habitacion.estado != "Libre":
        raise HTTPException(status_code=409, detail="RN-EXI-01: La habitación no está en estado Libre")

    tarifa_res = await db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)).order_by(Tarifa.id.desc()))
    tarifa = tarifa_res.scalars().first()
    if not tarifa:
        raise HTTPException(status_code=409, detail="No hay una tarifa vigente para liquidar el turno")

    nuevo_turno = Turno(
        habitacion_id=turno_in.habitacion_id,
        tarifa_id=tarifa.id,
        identificador_vehicular=turno_in.identificador_vehicular,
        tipo_cliente=turno_in.tipo_cliente,
        hora_inicio=datetime.now(UTC),
        estado="En Curso",
        tarifa_base=tarifa.tarifa_base,
        total_general=tarifa.tarifa_base,
    )
    db.add(nuevo_turno)
    habitacion.estado = "Ocupada"

    await db.commit()
    await db.refresh(nuevo_turno)
    return nuevo_turno


@router.post("/{turno_id}/consumos", status_code=status.HTTP_201_CREATED)
async def add_consumo(turno_id: uuid.UUID, consumo_in: ConsumoCreate, db: AsyncSession = Depends(get_db)):
    # RN-EXI-02: Check stock and atomically add consumption
    turno_res = await db.execute(select(Turno).where(Turno.id == turno_id))
    turno = turno_res.scalars().first()
    if not turno or turno.estado != "En Curso":
        raise HTTPException(status_code=400, detail="Turno no válido o no está en curso")

    art_res = await db.execute(select(Articulo).where(Articulo.id == consumo_in.articulo_id).with_for_update())
    articulo = art_res.scalars().first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado")

    if articulo.stock_actual < consumo_in.cantidad:
        raise HTTPException(
            status_code=400, detail=f"RN-EXI-02: Stock insuficiente. Stock actual: {articulo.stock_actual}"
        )

    # Descontar stock
    articulo.stock_actual -= consumo_in.cantidad

    subtotal = articulo.precio_unitario * consumo_in.cantidad

    nuevo_consumo = Consumo(
        turno_id=turno_id,
        articulo_id=articulo.id,
        cantidad=consumo_in.cantidad,
        precio_unitario=articulo.precio_unitario,
        subtotal=subtotal,
    )
    db.add(nuevo_consumo)

    # Actualizar totales en turno
    turno.total_consumos += subtotal
    turno.total_general += subtotal

    await db.commit()
    return {"status": "ok", "subtotal": float(subtotal)}


@router.get("/{turno_id}/resumen", response_model=TurnoResumen)
async def get_resumen(turno_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    turno_res = await db.execute(select(Turno).where(Turno.id == turno_id))
    turno = turno_res.scalars().first()
    if not turno:
        raise HTTPException(status_code=404, detail="Turno no encontrado")

    # RN-DER-01 / RN-DER-02: la liquidación se delega en servicios del backend.
    liquidacion = await liquidar_turno(db, turno)
    await db.commit()
    await db.refresh(turno)

    cons_res = await db.execute(select(Consumo).where(Consumo.turno_id == turno_id))
    consumos = cons_res.scalars().all()

    resumen_dict = turno.__dict__.copy()
    resumen_dict["minutos_transcurridos"] = liquidacion.minutos_transcurridos
    resumen_dict["total_pagado"] = liquidacion.total_pagado
    resumen_dict["saldo_pendiente"] = liquidacion.saldo_pendiente
    resumen_dict["consumos"] = [
        {
            "id": str(c.id),
            "articulo_id": c.articulo_id,
            "cantidad": c.cantidad,
            "precio_unitario": c.precio_unitario,
            "subtotal": c.subtotal,
        }
        for c in consumos
    ]

    return TurnoResumen.model_validate(resumen_dict)


@router.post("/{turno_id}/cerrar", response_model=ConstanciaCobro)
async def cerrar_turno(turno_id: uuid.UUID, cierre_in: CierreTurnoCreate, db: AsyncSession = Depends(get_db)):
    turno_res = await db.execute(select(Turno).where(Turno.id == turno_id))
    turno = turno_res.scalars().first()
    if not turno or turno.estado != "En Curso":
        raise HTTPException(status_code=400, detail="Turno no válido o ya finalizado")

    liquidacion = await liquidar_turno(db, turno)
    montos = [Decimal(str(p.monto)).quantize(Decimal("0.01")) for p in cierre_in.pagos]
    total_declarado = sum(montos, Decimal("0"))

    # RN-EXI-03: el turno solo se cierra con saldo exactamente cero.
    if total_declarado != liquidacion.saldo_pendiente:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                f"RN-EXI-03: El desglose de pagos (${total_declarado}) debe cubrir exactamente "
                f"el saldo pendiente (${liquidacion.saldo_pendiente})."
            ),
        )

    pagos_constancia = []
    for pago_in, monto in zip(cierre_in.pagos, montos, strict=True):
        comprobante = (pago_in.comprobante_referencia or "").strip() or None
        db.add(Pago(turno_id=turno.id, monto=monto, medio_pago=pago_in.medio_pago, comprobante_referencia=comprobante))
        pagos_constancia.append(
            PagoConstancia(medio_pago=pago_in.medio_pago, monto=monto, comprobante_referencia=comprobante)
        )

    turno.estado = "FINALIZADO"
    turno.hora_fin = datetime.now(UTC)

    # Liberar habitacion -> Pasa a En Limpieza
    hab_res = await db.execute(select(Habitacion).where(Habitacion.id == turno.habitacion_id))
    habitacion = hab_res.scalars().first()
    if habitacion:
        habitacion.estado = "En Limpieza"

    await db.commit()
    await db.refresh(turno)

    return ConstanciaCobro(
        turno_id=turno.id,
        habitacion_numero=habitacion.numero if habitacion else 0,
        hora_inicio=turno.hora_inicio,
        hora_fin=turno.hora_fin,
        tarifa_base=turno.tarifa_base,
        total_sobreturno=turno.total_sobreturno,
        total_consumos=turno.total_consumos,
        total_general=turno.total_general,
        total_pagado=total_declarado,
        saldo_pendiente=Decimal("0"),
        pagos=pagos_constancia,
    )
