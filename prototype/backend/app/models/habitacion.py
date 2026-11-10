from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, true

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento


class Habitacion(DeEstablecimiento, Base):
    __tablename__ = "habitaciones"
    # El número se repite entre establecimientos, no dentro de uno (migración 006).
    __table_args__ = (UniqueConstraint("establecimiento_id", "numero", name="habitaciones_numero_por_establecimiento"),)

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, index=True, nullable=False)
    estado = Column(String(20), nullable=False, default="Libre") # Libre, Ocupada, En Limpieza, Mantenimiento
    # RF-11: una habitación dada de baja sale de la grilla y conserva su historial de turnos.
    activa = Column(Boolean, nullable=False, default=True, server_default=true())
