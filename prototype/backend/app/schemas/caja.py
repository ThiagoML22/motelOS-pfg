from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# Tope de cada importe declarado: evita valores absurdos por un error de tipeo (cien millones de pesos).
IMPORTE_MAXIMO = Decimal("100000000")


class GuardiaPublica(BaseModel):
    """Datos de una guardia que puede ver cualquier operador. Nunca incluye totales (RN-RES-03)."""

    id: int
    franja: str
    estado: str
    abierta_en: datetime
    cerrada_en: datetime | None = None
    operador_id: int
    operador_nombre: str
    fondo_inicial: float
    es_propia: bool


class DeclaracionCaja(BaseModel):
    """Recuento físico que declara el operador al cerrar su guardia (RF-08)."""

    efectivo: Decimal = Field(ge=0, le=IMPORTE_MAXIMO, decimal_places=2)
    posnet: Decimal = Field(default=Decimal("0"), ge=0, le=IMPORTE_MAXIMO, decimal_places=2)
    mercado_pago: Decimal = Field(default=Decimal("0"), ge=0, le=IMPORTE_MAXIMO, decimal_places=2)


class DeclaracionSupervisada(DeclaracionCaja):
    """Recuento de la gerencia en el cierre de una guardia abandonada: exige explicar por qué."""

    observacion: str = Field(min_length=10, max_length=300)


class ArqueoResultado(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guardia_id: int
    franja: str
    abierta_en: datetime
    cerrada_en: datetime | None
    operador_id: int
    operador_nombre: str
    declarado_efectivo: float
    declarado_posnet: float
    declarado_mercado_pago: float
    total_declarado: float
    sistema_efectivo: float
    sistema_posnet: float
    sistema_mercado_pago: float
    total_sistema: float
    fondo_inicial: float
    diferencia: float
    categoria: str
    confirmado_en: datetime
    # Cierre supervisado: lo confirmó la gerencia, no el conserje dueño de la caja.
    supervisado: bool = False
    confirmado_por_nombre: str | None = None
    observacion: str | None = None


class PagoDetalle(BaseModel):
    registrado_en: datetime
    habitacion_numero: int
    medio_pago: str
    monto: float
    comprobante_referencia: str | None = None


class ArqueoDetalle(ArqueoResultado):
    pagos: list[PagoDetalle]


class MetricaCaja(BaseModel):
    """RF-09: métrica por operador (o general) que hoy la gerencia arma a mano (H-18)."""

    operador_id: int | None = None
    operador_nombre: str | None = None
    arqueos: int
    correctos: int
    faltantes: int
    sobrantes: int
    total_faltante: float
    total_sobrante: float
    # Tasa de Discrepancia de Caja: arqueos con diferencia distinta de 0 sobre el total (línea de base: 10 %).
    tdc: float


class MetricasCaja(BaseModel):
    desde: date | None
    hasta: date | None
    general: MetricaCaja
    por_operador: list[MetricaCaja]
