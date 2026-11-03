"""Panel de configuración de la gerencia (RF-11 ampliado, acta del 27/10/2026)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.seguridad import LARGO_MINIMO_CLAVE, PATRON_USUARIO

MINUTOS_DE_UN_DIA = 1440
TOPE_IMPORTE = 10_000_000


class ParametrosTarifa(BaseModel):
    """Cómo se cobra una estadía: base (precio y minutos), fracción adicional (minutos y precio), tolerancia antes de
    la primera fracción y tope opcional de la estadía completa (por ejemplo, un pernocte)."""

    tarifa_base: float = Field(gt=0, le=TOPE_IMPORTE)
    estadia_base_min: int = Field(gt=0, le=MINUTOS_DE_UN_DIA)
    fraccion_min: int = Field(gt=0, le=MINUTOS_DE_UN_DIA)
    tarifa_fraccion: float = Field(ge=0, le=TOPE_IMPORTE)
    tolerancia_min: int = Field(default=0, ge=0, le=240)
    tope: float | None = Field(default=None, gt=0, le=TOPE_IMPORTE)

    @model_validator(mode="after")
    def tope_no_menor_que_la_base(self) -> "ParametrosTarifa":
        if self.tope is not None and self.tope < self.tarifa_base:
            raise ValueError("El tope de la estadía no puede ser menor que el precio de la estadía base.")
        return self


class TarifaCreate(ParametrosTarifa):
    """La tarifa nueva de una categoría. Sin categoría, la primera del establecimiento (compatibilidad con el v3)."""

    categoria_id: int | None = None


class TarifaResponse(ParametrosTarifa):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    categoria_id: int
    vigente: bool
    vigente_desde: datetime


# --- Categorías de habitación (migración 008) -------------------------------------------------------------------------
COLOR_HEX = r"^#[0-9a-fA-F]{6}$"


class CategoriaDatos(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=40)
    descripcion: str | None = Field(default=None, max_length=160)
    color: str | None = Field(default=None, pattern=COLOR_HEX)
    orden: int | None = Field(default=None, ge=0, le=999)


class CategoriaAlta(BaseModel):
    """Una categoría nueva con su tarifa inicial."""

    nombre: str = Field(min_length=2, max_length=40)
    descripcion: str | None = Field(default=None, max_length=160)
    color: str = Field(default="#244473", pattern=COLOR_HEX)
    orden: int = Field(default=0, ge=0, le=999)
    tarifa: ParametrosTarifa


class CategoriaCambio(CategoriaDatos):
    activa: bool | None = None


class CategoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descripcion: str | None = None
    color: str
    orden: int
    activa: bool
    habitaciones: int = 0
    tarifa: TarifaResponse | None = None


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
    # Sin categoría, la primera del establecimiento.
    categoria_id: int | None = None


class HabitacionConfiguracion(BaseModel):
    numero: int | None = Field(default=None, gt=0, le=9999)
    activa: bool | None = None
    categoria_id: int | None = None


class HabitacionConfiguracionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero: int
    estado: str
    activa: bool
    categoria_id: int


class ConserjeAlta(BaseModel):
    usuario: str = Field(pattern=PATRON_USUARIO.pattern)
    nombre_visible: str = Field(min_length=1, max_length=60)
    clave: str = Field(min_length=LARGO_MINIMO_CLAVE, max_length=128)


class OperadorActivo(BaseModel):
    activo: bool


# --- Datos del establecimiento (multiinquilino, migración 006) ----------------------------------------------------
class EstablecimientoDatos(BaseModel):
    """Lo que la gerencia edita de su establecimiento; el código no cambia (lo usan los inicios de sesión)."""

    nombre: str | None = Field(default=None, min_length=2, max_length=80)
    domicilio: str | None = Field(default=None, max_length=120)
    telefono: str | None = Field(default=None, max_length=40)
    leyenda_comprobante: str | None = Field(default=None, max_length=200)
    # Apariencia y avisos (migración 009). Color vacío: el azul de MotelOS.
    color_marca: str | None = Field(default=None, pattern=r"^(#[0-9a-fA-F]{6})?$")
    eslogan: str | None = Field(default=None, max_length=120)
    aviso_por_vencer_min: int | None = Field(default=None, ge=0, le=120)
    alertas_sonoras: bool | None = None


class EstablecimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    codigo: str
    nombre: str
    domicilio: str | None = None
    telefono: str | None = None
    leyenda_comprobante: str | None = None
    activo: bool
    creado_en: datetime
    color_marca: str | None = None
    eslogan: str | None = None
    aviso_por_vencer_min: int = 10
    alertas_sonoras: bool = False


# --- Registro de actividad (migración 007) --------------------------------------------------------------------------
class ActividadResponse(BaseModel):
    id: int
    creado_en: datetime
    categoria: str
    accion: str
    descripcion: str
    operador_id: int
    operador_nombre: str
    guardia_id: int | None = None
    articulo_id: int | None = None
    cantidad: int | None = None
    valor_anterior: str | None = None
    valor_nuevo: str | None = None
    requiere_revision: bool
    revisado_en: datetime | None = None
    revisado_por_nombre: str | None = None


class ActividadPendientes(BaseModel):
    pendientes: int


class ActividadRevision(BaseModel):
    """Entradas a marcar como vistas; sin ids, todas las pendientes."""

    ids: list[int] | None = Field(default=None, max_length=500)


# --- Plataforma (multiinquilino) -------------------------------------------------------------------------------------
class EstablecimientoAlta(BaseModel):
    """Alta de un motel: sus datos, la gerencia inicial y la configuración de arranque."""

    codigo: str = Field(pattern=r"^[a-z0-9-]{3,30}$")
    nombre: str = Field(min_length=2, max_length=80)
    domicilio: str | None = Field(default=None, max_length=120)
    telefono: str | None = Field(default=None, max_length=40)
    habitaciones: int = Field(ge=1, le=200)
    tarifa_base: float = Field(gt=0, le=TOPE_IMPORTE)
    estadia_base_min: int = Field(default=120, gt=0, le=MINUTOS_DE_UN_DIA)
    fraccion_min: int = Field(default=30, gt=0, le=MINUTOS_DE_UN_DIA)
    tarifa_fraccion: float = Field(ge=0, le=TOPE_IMPORTE)
    fondo_cambio: float = Field(default=25000, ge=0, le=TOPE_IMPORTE)
    gerente_usuario: str = Field(pattern=PATRON_USUARIO.pattern)
    gerente_nombre: str = Field(min_length=1, max_length=60)
    gerente_clave: str = Field(min_length=LARGO_MINIMO_CLAVE, max_length=128)


class EstablecimientoEstado(BaseModel):
    activo: bool


class EstablecimientoResumen(EstablecimientoResponse):
    """Un establecimiento visto por la plataforma: datos y cantidades, nunca filas de su operación."""

    habitaciones: int = 0
    ocupadas: int = 0
    usuarios: int = 0
    turnos_ultimas_24h: int = 0
    cobrado_ultimas_24h: float = 0
    guardia_abierta: bool = False
    categorias: int = 0
