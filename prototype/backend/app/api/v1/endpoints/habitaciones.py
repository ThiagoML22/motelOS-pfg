from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.actividad import HABITACION
from app.models.evento_habitacion import LIBERAR, MANUAL
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.turno import Turno
from app.schemas.habitacion import HabitacionEstadoUpdate, HabitacionResponse
from app.services import rotacion
from app.services.actividad import registrar
from app.services.estadia import cargar_estadia_base, cargar_nombres_de_apertura, cargar_patentes
from app.services.liquidacion import liquidar_turno

router = APIRouter()

@router.get("/", response_model=list[HabitacionResponse])
async def get_habitaciones(db: AsyncSession = Depends(get_db)):
    # RF-11: las habitaciones dadas de baja no aparecen en la grilla.
    result = await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))
    habitaciones = result.scalars().all()

    turnos_result = await db.execute(select(Turno).where(Turno.estado == 'En Curso'))
    lista_activos = turnos_result.scalars().all()
    await cargar_patentes(db, lista_activos)
    await cargar_nombres_de_apertura(db, lista_activos)
    await cargar_estadia_base(db, lista_activos)
    turnos_activos = {t.habitacion_id: t for t in lista_activos}

    response_list = []
    for h in habitaciones:
        h_dict = h.__dict__.copy()
        if h.id in turnos_activos:
            h_dict["turno_activo"] = turnos_activos[h.id]
        response_list.append(HabitacionResponse.model_validate(h_dict))

    return response_list


@router.get("/proxima-libre")
async def proxima_libre(db: AsyncSession = Depends(get_db)) -> dict:
    """Cuándo quedaría disponible cada habitación, con la duración real de las estadías y de la limpieza."""
    return await rotacion.proxima_libre(db)


@router.get("/linea-de-tiempo")
async def linea_de_tiempo(dia: date | None = Query(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    """Las 24 horas de cada habitación: las últimas o las de un día. No lleva patentes ni importes."""
    return await rotacion.linea_de_tiempo(db, dia)


@router.patch("/{habitacion_id}/liberar")
async def liberar_habitacion(
    habitacion_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
):
    result = await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id))
    habitacion = result.scalars().first()

    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    if habitacion.estado != "En Limpieza":
        raise HTTPException(status_code=400, detail="Solo se puede liberar una habitación que está En Limpieza")

    await rotacion.cambiar_estado(db, habitacion, "Libre", operador, LIBERAR)
    await db.commit()
    return {"status": "ok"}



@router.patch("/{habitacion_id}/estado")
async def update_estado(
    habitacion_id: int,
    estado_in: HabitacionEstadoUpdate,
    db: AsyncSession = Depends(get_db),
    operador: Operador = Depends(operador_actual),
):
    valid_estados = ["Libre", "En Limpieza", "Mantenimiento"]
    if estado_in.estado not in valid_estados:
        raise HTTPException(status_code=400, detail="Estado inválido. Debe ser Libre, En Limpieza o Mantenimiento")

    result = await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id))
    habitacion = result.scalars().first()

    if not habitacion:
        raise HTTPException(status_code=404, detail="Habitación no encontrada")

    if habitacion.estado == "Ocupada":
        if estado_in.estado == "En Limpieza":
            # RN-EXI-03 / RF-07: una habitación con saldo pendiente no pasa a limpieza.
            turno_res = await db.execute(
                select(Turno).where(Turno.habitacion_id == habitacion.id, Turno.estado == "En Curso")
            )
            turno = turno_res.scalars().first()
            if turno:
                liquidacion = await liquidar_turno(db, turno)
                await db.commit()
                if liquidacion.saldo_pendiente != 0:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "RN-EXI-03: La habitación no puede pasar a En Limpieza con un saldo "
                            f"pendiente de ${liquidacion.saldo_pendiente}."
                        ),
                    )
        raise HTTPException(
            status_code=400, detail="No se puede cambiar manualmente el estado de una habitación Ocupada"
        )

    # Terminar una limpieza es la rutina de cada turno; cualquier otro cambio a mano queda además en Actividad.
    anterior = habitacion.estado
    es_liberar = anterior == "En Limpieza" and estado_in.estado == "Libre"
    await rotacion.cambiar_estado(db, habitacion, estado_in.estado, operador, LIBERAR if es_liberar else MANUAL)
    if not es_liberar and anterior != estado_in.estado:
        await registrar(
            db,
            operador,
            HABITACION,
            "HABITACION_ESTADO",
            f"La habitación {habitacion.numero} pasó de {anterior} a {estado_in.estado}",
            valor_anterior=anterior,
            valor_nuevo=estado_in.estado,
        )
    await db.commit()
    return {"status": "ok"}
