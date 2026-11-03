from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, false

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento


class Novedad(DeEstablecimiento, Base):
    """Lo que el personal deja escrito para la guardia siguiente y para la gerencia (migración 009).

    Solo se agregan: la aplicación no tiene permiso para editarlas ni borrarlas. Cada una queda a nombre del usuario
    de la sesión y, si la escribe un conserje, en su guardia abierta (trigger_novedad).
    """

    __tablename__ = "novedades"

    id = Column(Integer, primary_key=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=True)
    texto = Column(String(500), nullable=False)
    importante = Column(Boolean, nullable=False, default=False, server_default=false())
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
