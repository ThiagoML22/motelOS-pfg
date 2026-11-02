from sqlalchemy import Boolean, Column, Integer, String, true

from app.core.database import Base


class Habitacion(Base):
    __tablename__ = "habitaciones"

    id = Column(Integer, primary_key=True, index=True)
    numero = Column(Integer, unique=True, index=True, nullable=False)
    estado = Column(String(20), nullable=False, default="Libre") # Libre, Ocupada, En Limpieza, Mantenimiento
    # RF-11: una habitación dada de baja sale de la grilla y conserva su historial de turnos.
    activa = Column(Boolean, nullable=False, default=True, server_default=true())
