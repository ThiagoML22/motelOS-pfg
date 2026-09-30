from datetime import datetime
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field

from app.schemas.articulo import ConsumoResponse

TipoCliente = Literal["Auto", "Moto", "Peaton"]
MedioPago = Literal["EFECTIVO", "MERCADO_PAGO", "POSNET"]


class TurnoBase(BaseModel):
    habitacion_id: int
    # RNF-03: identificación vehicular transitoria y opcional; nunca datos personales.
    identificador_vehicular: str | None = Field(default=None, max_length=50)
    tipo_cliente: TipoCliente = "Auto"


class TurnoCreate(TurnoBase):
    pass


class TurnoResponse(TurnoBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    hora_inicio: datetime
    hora_fin: datetime | None = None
    estado: str
    tarifa_base: float
    total_sobreturno: float
    total_consumos: float
    total_general: float


class TurnoResumen(TurnoResponse):
    minutos_transcurridos: int
    consumos: list[ConsumoResponse] = []


class PagoCreate(BaseModel):
    monto: float = Field(gt=0)
    medio_pago: MedioPago
    comprobante_referencia: str | None = Field(default=None, max_length=100)
