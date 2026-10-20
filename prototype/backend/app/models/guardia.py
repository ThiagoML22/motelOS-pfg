from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from app.core.database import Base


class Guardia(Base):
    """Caja de un operador durante su franja de 8 h (06:00, 14:00 o 22:00).

    Hay una sola ventanilla: en la base, un índice único parcial impide dos guardias abiertas.
    Una guardia solo se cierra con su arqueo confirmado y, cerrada, no cambia más (trigger_guardia).
    """

    __tablename__ = "guardias"

    id = Column(Integer, primary_key=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    franja = Column(String(5), nullable=False)
    fondo_inicial = Column(Numeric(12, 2), nullable=False, default=0)
    abierta_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    cerrada_en = Column(DateTime(timezone=True), nullable=True)
    estado = Column(String(10), nullable=False, default="Abierta")
