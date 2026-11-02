"""Panel de configuración de la gerencia (RF-11 ampliado, acta del 27/10/2026)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.seguridad import LARGO_MINIMO_CLAVE, PATRON_USUARIO

MINUTOS_DE_UN_DIA = 1440
TOPE_IMPORTE = 10_000_000


class TarifaCreate(BaseModel):
    """La tarifa nueva: estadía base (precio y minutos) y fracción adicional (minutos y precio)."""

    tarifa_base: float = Field(gt=0, le=TOPE_IMPORTE)
    estadia_base_min: int = Field(gt=0, le=MINUTOS_DE_UN_DIA)
    fraccion_min: int = Field(gt=0, le=MINUTOS_DE_UN_DIA)
    tarifa_fraccion: float = Field(ge=0, le=TOPE_IMPORTE)


class TarifaResponse(TarifaCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    vigente: bool
    vigente_desde: datetime


class FondoCambio(BaseModel):
    fondo_cambio: float = Field(ge=0, le=TOPE_IMPORTE)


class FondoCambioResponse(FondoCambio):
    model_config = ConfigDict(from_attributes=True)

    actualizado_en: datetime | None = None


class ArticuloConfiguracion(BaseModel):
    """Cambios de un artículo: solo los campos enviados se modifican."""

    descripcion: str | None = Field(default=None, min_length=1, max_length=255)
    categoria: str | None = Field(default=None, max_length=50)
    precio_unitario: float | None = Field(default=None, ge=0, le=TOPE_IMPORTE)
    stock_actual: int | None = Field(default=None, ge=0)
    activo: bool | None = None


class HabitacionAlta(BaseModel):
    numero: int = Field(gt=0, le=9999)


class HabitacionConfiguracion(BaseModel):
    numero: int | None = Field(default=None, gt=0, le=9999)
    activa: bool | None = None


class HabitacionConfiguracionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero: int
    estado: str
    activa: bool


class ConserjeAlta(BaseModel):
    usuario: str = Field(pattern=PATRON_USUARIO.pattern)
    nombre_visible: str = Field(min_length=1, max_length=60)
    clave: str = Field(min_length=LARGO_MINIMO_CLAVE, max_length=128)


class OperadorActivo(BaseModel):
    activo: bool
