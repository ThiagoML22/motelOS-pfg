import uuid
from datetime import UTC, datetime
from decimal import Decimal

import segno
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.categoria import CategoriaHabitacion
from app.models.consumo import Consumo
from app.models.estadia_activa import EstadiaActiva
from app.models.evento_habitacion import COBRO, TURNO
from app.models.franja_tarifa import FranjaTarifa
from app.models.habitacion import Habitacion
from app.models.operador import Operador
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
from app.services import acceso_cliente, franjas, rotacion
from app.services.actividad import pesos
from app.services.caja import guardia_del_operador
from app.services.consumos import cargar_consumo
from app.services.estadia import cargar_estadia_base, cargar_nombres_de_apertura, cargar_patentes
from app.services.liquidacion import liquidar_turno

router = APIRouter()


@router.post("/", response_model=TurnoResponse, status_code=status.HTTP_201_CREATED)
async def create_turno(
    turno_in: TurnoCreate,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    # Bloquea la habitación: una segunda apertura simultánea espera y la encuentra Ocupada.
    result = await db.execute(select(Habitacion).where(Habitacion.id == turno_in.habitacion_id).with_for_update())
    habitacion = result.scalars().first()

    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    if not habitacion.activa:
        raise HTTPException(status_code=409, detail="La habitación está dada de baja.")

    if habitacion.estado != "Libre":
        raise HTTPException(status_code=409, detail="RN-EXI-01: La habitación no está en estado Libre")

    guardia = await guardia_del_operador(db, operador)

    # La tarifa que rige ahora para la categoría de la habitación: la especial de esta franja o la general. El turno la
    # conserva aunque después cambie la franja, la tarifa o la categoría (RN-DER-06).
    ahora = datetime.now(UTC)
    vigente = await franjas.tarifa_en(db, habitacion.categoria_id, ahora)
    if vigente is None:
        raise HTTPException(status_code=409, detail="No hay una tarifa vigente para la categoría de la habitación")
    tarifa = vigente.tarifa
    if turno_in.tarifa_id is not None and turno_in.tarifa_id != tarifa.id:
        nombre = f" ({vigente.franja.nombre})" if vigente.franja else ""
        raise HTTPException(
            status_code=409,
            detail=f"La tarifa acaba de cambiar: ahora rige {pesos(tarifa.tarifa_base)}{nombre}. Revísela.",
        )

    nuevo_turno = Turno(
        habitacion_id=turno_in.habitacion_id,
        tarifa_id=tarifa.id,
        tipo_cliente=turno_in.tipo_cliente,
        hora_inicio=ahora,
        estado="En Curso",
        tarifa_base=tarifa.tarifa_base,
        total_general=tarifa.tarifa_base,
        # RNF-04: el turno queda a nombre del operador de la sesión y de su guardia.
        operador_apertura_id=operador.id,
        guardia_apertura_id=guardia.id,
    )
    db.add(nuevo_turno)
    patente = (turno_in.identificador_vehicular or "").strip() or None
    try:
        await db.flush()
        if patente:
            # RNF-08: la patente vive en la estadía activa, no en el turno inmutable.
            db.add(EstadiaActiva(turno_id=nuevo_turno.id, identificador_vehicular=patente))
        await rotacion.cambiar_estado(db, habitacion, "Ocupada", operador, TURNO, nuevo_turno.id)
        await db.commit()
    except IntegrityError:
        # RN-EXI-01: el índice turnos_uno_en_curso_por_habitacion deja pasar un solo turno en curso.
        await db.rollback()
        raise HTTPException(status_code=409, detail="RN-EXI-01: La habitación ya tiene un turno en curso") from None
    await db.refresh(nuevo_turno)
    nuevo_turno.identificador_vehicular = patente
    nuevo_turno.abierto_por = operador.nombre_visible
    nuevo_turno.estadia_base_min = tarifa.estadia_base_min
    return nuevo_turno


@router.post("/{turno_id}/consumos", status_code=status.HTTP_201_CREATED)
async def add_consumo(
    turno_id: uuid.UUID,
    consumo_in: ConsumoCreate,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    subtotal = await cargar_consumo(db, turno_id, consumo_in.articulo_id, consumo_in.cantidad, operador)
    await db.commit()
    return {"status": "ok", "subtotal": float(subtotal)}


@router.get("/{turno_id}/ticket")
async def ticket(
    turno_id: uuid.UUID, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    """El ticket del cliente: un enlace firmado a su estadía, que vale mientras el turno esté en curso."""
    turno = (await db.execute(select(Turno).where(Turno.id == turno_id))).scalars().first()
    if not turno or turno.estado != "En Curso":
        raise HTTPException(status_code=400, detail="Turno no válido o no está en curso")
    direccion = acceso_cliente.direccion_de(acceso_cliente.token_de(operador.establecimiento_id, turno.id))
    habitacion = await db.get(Habitacion, turno.habitacion_id)
    return {
        "direccion": direccion,
        "qr": segno.make(direccion, error="m", boost_error=False).svg_data_uri(scale=4, border=2),
        "numero": habitacion.numero,
        "hora_inicio": turno.hora_inicio,
    }


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

    await cargar_patentes(db, [turno])
    await cargar_nombres_de_apertura(db, [turno])
    await cargar_estadia_base(db, [turno])
    resumen_dict = turno.__dict__.copy()
    resumen_dict["minutos_transcurridos"] = liquidacion.minutos_transcurridos
    resumen_dict["total_pagado"] = liquidacion.total_pagado
    resumen_dict["saldo_pendiente"] = liquidacion.saldo_pendiente
    tarifa = await db.get(Tarifa, turno.tarifa_id)
    if tarifa is not None:
        categoria = await db.get(CategoriaHabitacion, tarifa.categoria_id)
        franja = await db.get(FranjaTarifa, tarifa.franja_id) if tarifa.franja_id else None
        resumen_dict["tarifa"] = {
            "categoria": categoria.nombre if categoria else None,
            "color": categoria.color if categoria else None,
            "franja": franja.nombre if franja else None,
            "tarifa_base": tarifa.tarifa_base,
            "estadia_base_min": tarifa.estadia_base_min,
            "fraccion_min": tarifa.fraccion_min,
            "tarifa_fraccion": tarifa.tarifa_fraccion,
            "tolerancia_min": tarifa.tolerancia_min,
            "tope": tarifa.tope,
        }
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
async def cerrar_turno(
    turno_id: uuid.UUID,
    cierre_in: CierreTurnoCreate,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    # Bloquea el turno: un segundo cobro simultáneo (doble clic, reintento) espera y lo encuentra finalizado,
    # en lugar de chocar con el trigger de inmutabilidad (RN-RES-01) y responder un error interno.
    turno_res = await db.execute(select(Turno).where(Turno.id == turno_id).with_for_update())
    turno = turno_res.scalars().first()
    if not turno or turno.estado != "En Curso":
        raise HTTPException(status_code=400, detail="Turno no válido o ya finalizado")

    # RN-DER-04: el cobro entra a la caja de la guardia que atiende ahora, aunque el turno lo haya
    # abierto la anterior.
    guardia = await guardia_del_operador(db, operador)
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
        db.add(
            Pago(
                turno_id=turno.id,
                monto=monto,
                medio_pago=pago_in.medio_pago,
                comprobante_referencia=comprobante,
                operador_id=operador.id,
                guardia_id=guardia.id,
            )
        )
        pagos_constancia.append(
            PagoConstancia(medio_pago=pago_in.medio_pago, monto=monto, comprobante_referencia=comprobante)
        )

    turno.estado = "FINALIZADO"
    turno.hora_fin = datetime.now(UTC)
    turno.operador_cierre_id = operador.id

    # Liberar habitacion -> Pasa a En Limpieza
    hab_res = await db.execute(select(Habitacion).where(Habitacion.id == turno.habitacion_id))
    habitacion = hab_res.scalars().first()
    if habitacion:
        await rotacion.cambiar_estado(db, habitacion, "En Limpieza", operador, COBRO, turno.id)

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
