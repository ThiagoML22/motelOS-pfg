from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento
from app.services.billing_service import ParametrosTarifa

GENERAL_VIGENTE = text("vigente AND franja_id IS NULL")
VIGENTE_DE_FRANJA = text("vigente AND franja_id IS NOT NULL")


class Tarifa(DeEstablecimiento, Base):
    """Tarifa de la estadía. Una tarifa ya usada no se edita: el cambio crea otra (RF-11, RN-DER-06).

    Sin franja_id es la tarifa general de la categoría; con franja_id, el precio de una tarifa especial (migración 014).
    """

    __tablename__ = "tarifas"
    # A lo sumo una tarifa general vigente por categoría y una vigente por franja (migraciones 005, 006, 008 y 014).
    __table_args__ = (
        Index("tarifas_una_vigente", "establecimiento_id", "categoria_id", unique=True,
              postgresql_where=GENERAL_VIGENTE, sqlite_where=GENERAL_VIGENTE),
        Index("tarifas_una_vigente_por_franja", "establecimiento_id", "franja_id", unique=True,
              postgresql_where=VIGENTE_DE_FRANJA, sqlite_where=VIGENTE_DE_FRANJA),
        UniqueConstraint("establecimiento_id", "nombre", name="tarifas_nombre_por_establecimiento"),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    tarifa_base = Column(Numeric(10, 2), nullable=False)
    estadia_base_min = Column(Integer, nullable=False, default=120)
    tolerancia_min = Column(Integer, nullable=False, default=0)
    fraccion_min = Column(Integer, nullable=False, default=30)
    tarifa_fraccion = Column(Numeric(10, 2), nullable=False)
    vigente = Column(Boolean, nullable=False, default=True)
    vigente_desde = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    creada_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias_habitacion.id"), nullable=False)
    # Precio máximo de la estadía (por ejemplo, un pernocte): el sobreturno no lo supera. Opcional.
    tope = Column(Numeric(10, 2), nullable=True)
    franja_id = Column(Integer, ForeignKey("franjas_tarifa.id"), nullable=True)

    def parametros(self) -> ParametrosTarifa:
        return ParametrosTarifa(
            tarifa_base=self.tarifa_base,
            estadia_base_min=self.estadia_base_min,
            tolerancia_min=self.tolerancia_min,
            fraccion_min=self.fraccion_min,
            tarifa_fraccion=self.tarifa_fraccion,
            tope=self.tope,
        )
