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
    turno_activo: TurnoResponse | None = None
