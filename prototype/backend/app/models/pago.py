import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    medio_pago = Column(String(50), nullable=False)
    comprobante_referencia = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    # RNF-04 y RN-DER-04: el pago se imputa al operador y a la guardia abierta al momento del cobro,
    # aunque el turno lo haya abierto otra guardia. Nulos solo en los pagos de la v1.
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=True)
