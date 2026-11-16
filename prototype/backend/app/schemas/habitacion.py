from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.turno import TurnoResponse

EstadoHabitacion = Literal["Libre", "Ocupada", "En Limpieza", "Mantenimiento"]


class HabitacionBase(BaseModel):
    numero: int
    estado: EstadoHabitacion


class HabitacionCreate(HabitacionBase):
    pass


class HabitacionEstadoUpdate(BaseModel):
    estado: str


class HabitacionResponse(HabitacionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # Categoría de la habitación (migración 008); la grilla toma nombre, color y tarifa de /categorias.
    categoria_id: int | None = None
    turno_activo: TurnoResponse | None = None
    # Arreglos sin resolver: la grilla los marca con un ícono (migración 016).
    arreglos_abiertos: int = 0
    # RF-12: solo En Limpieza. Los minutos los calcula el servidor; demora si superan DEMORA_LIMPIEZA_MIN (30).
    en_limpieza_desde: datetime | None = None
    minutos_en_limpieza: int | None = None
    demora_limpieza: bool = False
