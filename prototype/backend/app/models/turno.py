import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Turno(Base):
    __tablename__ = "turnos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    tarifa_id = Column(Integer, ForeignKey("tarifas.id"), nullable=False)
    # RNF-08: la patente ya no se guarda en el turno (inmutable); vive en estadias_activas y se carga
    # como atributo transitorio con app.services.estadia.cargar_patentes.
    identificador_vehicular = None
    # Nombre visible de quien abrió el turno (atributo transitorio, ver cargar_nombres_de_apertura).
    abierto_por = None
    tipo_cliente = Column(String(20), nullable=False, default="Auto")
    hora_inicio = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    hora_fin = Column(DateTime(timezone=True), nullable=True)
    tarifa_base = Column(Numeric(10, 2), nullable=False)
    total_sobreturno = Column(Numeric(10, 2), nullable=False, default=0)
    total_consumos = Column(Numeric(10, 2), nullable=False, default=0)
    total_general = Column(Numeric(10, 2), nullable=False)
    estado = Column(String(20), nullable=False, default="En Curso")
    # RNF-04: quién abrió el turno, en qué guardia, y quién lo cobró. Los toma el backend del token de
    # sesión, nunca del cuerpo de la petición. Nulos solo en los turnos de la v1 (sin autenticación).
    operador_apertura_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    guardia_apertura_id = Column(Integer, ForeignKey("guardias.id"), nullable=True)
    operador_cierre_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
