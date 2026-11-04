from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects import sqlite
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

# De dónde viene el cambio de estado (CHECK de la migración 011).
TURNO = "TURNO"  # se abrió un turno
COBRO = "COBRO"  # se cobró y cerró un turno
LIBERAR = "LIBERAR"  # terminó la limpieza
MANUAL = "MANUAL"  # alguien lo cambió a mano


class EventoHabitacion(DeEstablecimiento, Base):
    """Cada cambio de estado de una habitación (migración 011). Es de solo agregado.

    La habitación guarda solo su estado actual; acá queda desde cuándo, quién lo cambió y por qué. Con esto se mide la
    limpieza, se arma la línea de tiempo y se ve una limpieza que no vino de un turno.
    """

    __tablename__ = "eventos_habitacion"

    # BIGSERIAL en PostgreSQL; en SQLite solo INTEGER es autoincremental.
    id = Column(BigInteger().with_variant(sqlite.INTEGER(), "sqlite"), primary_key=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    estado_anterior = Column(String(20), nullable=False)
    estado_nuevo = Column(String(20), nullable=False)
    origen = Column(String(10), nullable=False)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
