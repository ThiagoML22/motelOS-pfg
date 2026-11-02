from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger

from app.core.database import Base


class ConfiguracionCaja(Base):
    """Fondo de cambio vigente (RF-11, acta del 27/10/2026). Una sola fila (id = 1, migración 005).

    La guardia copia el monto al abrirse (Guardia.fondo_inicial): un cambio rige desde la guardia siguiente.
    """

    __tablename__ = "configuracion_caja"
    __table_args__ = (CheckConstraint("id = 1", name="configuracion_caja_una_fila"),)

    id = Column(SmallInteger, primary_key=True, default=1)
    fondo_cambio = Column(Numeric(12, 2), nullable=False)
    actualizado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    actualizado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
