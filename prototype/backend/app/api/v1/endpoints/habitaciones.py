from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.habitacion import Habitacion
from app.models.turno import Turno
from app.schemas.habitacion import HabitacionEstadoUpdate, HabitacionResponse

router = APIRouter()

@router.get("/", response_model=list[HabitacionResponse])
async def get_habitaciones(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Habitacion).order_by(Habitacion.numero))
    habitaciones = result.scalars().all()
    
    turnos_result = await db.execute(select(Turno).where(Turno.estado == 'En Curso'))
    turnos_activos = {t.habitacion_id: t for t in turnos_result.scalars().all()}
    
    response_list = []
    for h in habitaciones:
        h_dict = h.__dict__.copy()
        if h.id in turnos_activos:
            h_dict["turno_activo"] = turnos_activos[h.id]
        response_list.append(HabitacionResponse.model_validate(h_dict))
        
    return response_list

@router.patch("/{habitacion_id}/liberar")
async def liberar_habitacion(habitacion_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id))
    habitacion = result.scalars().first()
    
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
        
    if habitacion.estado != "En Limpieza":
        raise HTTPException(status_code=400, detail="Solo se puede liberar una habitación que está En Limpieza")
        
    habitacion.estado = "Libre"
    await db.commit()
    return {"status": "ok"}



@router.patch("/{habitacion_id}/estado")
async def update_estado(habitacion_id: int, estado_in: HabitacionEstadoUpdate, db: AsyncSession = Depends(get_db)):
    valid_estados = ["Libre", "En Limpieza", "Mantenimiento"]
    if estado_in.estado not in valid_estados:
        raise HTTPException(status_code=400, detail="Estado inválido. Debe ser Libre, En Limpieza o Mantenimiento")
        
    result = await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id))
    habitacion = result.scalars().first()
    
    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")
        
    if habitacion.estado == "Ocupada":
        raise HTTPException(
            status_code=400, detail="No se puede cambiar manualmente el estado de una habitación Ocupada"
        )
        
    habitacion.estado = estado_in.estado
    await db.commit()
    return {"status": "ok"}
