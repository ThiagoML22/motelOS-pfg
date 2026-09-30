import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Consumo(Base):
    __tablename__ = "detalles_consumo"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=False)
    articulo_id = Column(Integer, ForeignKey("articulos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
