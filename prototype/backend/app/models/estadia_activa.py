from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class EstadiaActiva(Base):
    """Dato operativo de una estadía: la patente vive aquí, separada del registro financiero (RNF-08).

    El turno (importes, horarios y pagos) es inmutable; esta fila se elimina dentro del plazo de
    retención posterior al cierre del turno (ver app.services.estadia.depurar_patentes).
    """

    __tablename__ = "estadias_activas"

    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), primary_key=True)
    identificador_vehicular = Column(String(50), nullable=False)
