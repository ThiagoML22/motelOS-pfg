import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.articulo import Articulo
from app.models.consumo import Consumo
from app.models.habitacion import Habitacion
from app.models.pago import Pago
from app.models.turno import Turno
from app.schemas.articulo import ConsumoCreate
from app.schemas.turno import PagoCreate, TurnoCreate, TurnoResponse, TurnoResumen
from app.services.billing_service import TARIFA_BASE, calcular_sobreturno

router = APIRouter()


def _utc(valor: datetime) -> datetime:
    return valor if valor.tzinfo else valor.replace(tzinfo=UTC)

@router.post("/", response_model=TurnoResponse, status_code=status.HTTP_201_CREATED)
async def create_turno(turno_in: TurnoCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Habitacion).where(Habitacion.id == turno_in.habitacion_id))
    habitacion = result.scalars().first()
    
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
        
    if habitacion.estado != "Libre":
        raise HTTPException(status_code=409, detail="RN-EXI-01: La habitación no está en estado Libre")
        
    nuevo_turno = Turno(
        habitacion_id=turno_in.habitacion_id,
        identificador_vehicular=turno_in.identificador_vehicular,
        tipo_cliente=turno_in.tipo_cliente,
        hora_inicio=datetime.now(UTC),
        estado="En Curso",
        tarifa_base=TARIFA_BASE,
        total_general=TARIFA_BASE
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
        subtotal=subtotal
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
        
    # RN-DER-01: la liquidación temporal se delega en un servicio puro.
    fin = _utc(turno.hora_fin) if turno.hora_fin else datetime.now(UTC)
    duracion = fin - _utc(turno.hora_inicio)
    minutos_transcurridos = int(duracion.total_seconds() / 60)

    if turno.estado == "En Curso":
        sobreturno = calcular_sobreturno(duracion)
        if sobreturno != turno.total_sobreturno:
            turno.total_sobreturno = sobreturno
            turno.total_general = turno.tarifa_base + sobreturno + turno.total_consumos
            await db.commit()
            await db.refresh(turno)
    
    # Obtener consumos
    cons_res = await db.execute(select(Consumo).where(Consumo.turno_id == turno_id))
    consumos = cons_res.scalars().all()
    
    resumen_dict = turno.__dict__.copy()
    resumen_dict["minutos_transcurridos"] = minutos_transcurridos
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

@router.post("/{turno_id}/cerrar")
async def cerrar_turno(turno_id: uuid.UUID, pago_in: PagoCreate, db: AsyncSession = Depends(get_db)):
    turno_res = await db.execute(select(Turno).where(Turno.id == turno_id))
    turno = turno_res.scalars().first()
    if not turno or turno.estado != "En Curso":
        raise HTTPException(status_code=400, detail="Turno no válido o ya finalizado")
        
    # Validar RN-EXI-03: Pago completo
    # En este prototipo asumimos 1 pago que cubre el total_general
    if pago_in.monto < float(turno.total_general):
        raise HTTPException(status_code=400, detail="RN-EXI-03: El monto del pago no cubre el total de la estadía.")
        
    nuevo_pago = Pago(
        turno_id=turno.id,
        monto=pago_in.monto,
        medio_pago=pago_in.medio_pago,
        comprobante_referencia=pago_in.comprobante_referencia
    )
    db.add(nuevo_pago)
    
    turno.estado = "FINALIZADO"
    turno.hora_fin = datetime.now(UTC)
    
    # Liberar habitacion -> Pasa a En Limpieza
    hab_res = await db.execute(select(Habitacion).where(Habitacion.id == turno.habitacion_id))
    habitacion = hab_res.scalars().first()
    if habitacion:
        habitacion.estado = "En Limpieza"
        
    await db.commit()
    return {"status": "ok", "mensaje": "Turno liquidado y cerrado correctamente."}
