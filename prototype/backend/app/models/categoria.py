from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint, true

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento


class CategoriaHabitacion(DeEstablecimiento, Base):
    """Tipo de habitación que define cada establecimiento (Simple, Especial, VIP...), con su tarifa (migración 008).

    La tarifa vive en la tabla tarifas (una vigente por categoría); la categoría solo guarda cómo se muestra. No se
    borra: se da de baja cuando no le quedan habitaciones activas (trigger_categoria_baja).
    """

    __tablename__ = "categorias_habitacion"
    __table_args__ = (UniqueConstraint("establecimiento_id", "nombre", name="categorias_nombre_por_establecimiento"),)

    id = Column(Integer, primary_key=True)
    nombre = Column(String(40), nullable=False)
    descripcion = Column(String(160), nullable=True)
    color = Column(String(7), nullable=False, default="#244473")
    orden = Column(Integer, nullable=False, default=0)
    activa = Column(Boolean, nullable=False, default=True, server_default=true())
    creada_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
