from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, text

from app.core.database import Base
from app.services.billing_service import ParametrosTarifa

VIGENTE = text("vigente")


class Tarifa(Base):
    """Tarifa de la estadía. Una tarifa ya usada no se edita: el cambio crea otra (RF-11, RN-DER-06)."""

    __tablename__ = "tarifas"
    # A lo sumo una tarifa vigente (migración 005).
    __table_args__ = (
        Index("tarifas_una_vigente", "vigente", unique=True, postgresql_where=VIGENTE, sqlite_where=VIGENTE),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), unique=True, nullable=False)
    tarifa_base = Column(Numeric(10, 2), nullable=False)
    estadia_base_min = Column(Integer, nullable=False, default=120)
    tolerancia_min = Column(Integer, nullable=False, default=0)
    fraccion_min = Column(Integer, nullable=False, default=30)
    tarifa_fraccion = Column(Numeric(10, 2), nullable=False)
    vigente = Column(Boolean, nullable=False, default=True)
    vigente_desde = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    creada_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)

    def parametros(self) -> ParametrosTarifa:
        return ParametrosTarifa(
            tarifa_base=self.tarifa_base,
            estadia_base_min=self.estadia_base_min,
            tolerancia_min=self.tolerancia_min,
            fraccion_min=self.fraccion_min,
            tarifa_fraccion=self.tarifa_fraccion,
        )
