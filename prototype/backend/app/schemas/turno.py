from datetime import datetime
from typing import Literal

from pydantic import UUID4, BaseModel, ConfigDict, Field, model_validator

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
    total_pagado: float = 0
    saldo_pendiente: float = 0
    consumos: list[ConsumoResponse] = []


class PagoCreate(BaseModel):
    monto: float = Field(gt=0)
    medio_pago: MedioPago
    comprobante_referencia: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def exigir_comprobante_electronico(self) -> "PagoCreate":
        # RF-06: los cobros electrónicos (cupón POSNET, Mercado Pago) se respaldan con su comprobante.
        if self.medio_pago != "EFECTIVO" and not (self.comprobante_referencia or "").strip():
            raise ValueError(f"El medio de pago {self.medio_pago} requiere número de comprobante")
        return self


class CierreTurnoCreate(BaseModel):
    """Desglose de pagos (efectivo y/o cupones) con el que se liquida un turno."""

    pagos: list[PagoCreate] = Field(min_length=1)


class PagoConstancia(BaseModel):
    medio_pago: str
    monto: float
    comprobante_referencia: str | None = None


class ConstanciaCobro(BaseModel):
    turno_id: UUID4
    habitacion_numero: int
    hora_inicio: datetime
    hora_fin: datetime
    tarifa_base: float
    total_sobreturno: float
    total_consumos: float
    total_general: float
    total_pagado: float
    saldo_pendiente: float
    pagos: list[PagoConstancia]
