from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String, text

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

ABIERTA = text("estado = 'Abierta'")


class Guardia(DeEstablecimiento, Base):
    """Caja de un operador durante su franja de 8 h (06:00, 14:00 o 22:00).

    Cada establecimiento tiene una sola ventanilla: un índice único parcial impide dos guardias abiertas.
    Una guardia solo se cierra con su arqueo confirmado y, cerrada, no cambia más (trigger_guardia).
    """

    __tablename__ = "guardias"
    __table_args__ = (
        Index("guardias_una_abierta", "establecimiento_id", unique=True, postgresql_where=ABIERTA,
              sqlite_where=ABIERTA),
    )

    id = Column(Integer, primary_key=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    franja = Column(String(5), nullable=False)
    fondo_inicial = Column(Numeric(12, 2), nullable=False, default=0)
    abierta_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    cerrada_en = Column(DateTime(timezone=True), nullable=True)
    estado = Column(String(10), nullable=False, default="Abierta")
