from datetime import datetime

from pydantic import UUID4, BaseModel

from app.schemas.articulo import ConsumoResponse


class TurnoBase(BaseModel):
    habitacion_id: int
    identificador_vehicular: str
    tipo_cliente: str = "Auto"

class TurnoCreate(TurnoBase):
    pass

class TurnoResponse(TurnoBase):
    id: UUID4
    hora_inicio: datetime
    hora_fin: datetime | None = None
    estado: str
    tarifa_base: float
    total_sobreturno: float
    total_consumos: float
    total_general: float

    class Config:
        from_attributes = True

class TurnoResumen(TurnoResponse):
    minutos_transcurridos: int
    consumos: list[ConsumoResponse] = []

class PagoCreate(BaseModel):
    monto: float
    medio_pago: str
    comprobante_referencia: str | None = None
