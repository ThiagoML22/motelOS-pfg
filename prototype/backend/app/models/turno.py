import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Turno(Base):
    __tablename__ = "turnos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    identificador_vehicular = Column(String(50), nullable=True)
    tipo_cliente = Column(String(20), nullable=False, default="Auto")
    hora_inicio = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    hora_fin = Column(DateTime(timezone=True), nullable=True)
    tarifa_base = Column(Numeric(10, 2), nullable=False, default=12000)
    total_sobreturno = Column(Numeric(10, 2), nullable=False, default=0)
    total_consumos = Column(Numeric(10, 2), nullable=False, default=0)
    total_general = Column(Numeric(10, 2), nullable=False, default=12000)
    estado = Column(String(20), nullable=False, default="En Curso")
