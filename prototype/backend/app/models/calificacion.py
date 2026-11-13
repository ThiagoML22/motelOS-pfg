from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

# Lo que puede marcar el cliente: una máscara (migración 015).
PROBLEMAS = {
    1: "Limpieza",
    2: "Ruido",
    4: "Aire o calefacción",
    8: "TV o Wi-Fi",
    16: "Baño",
    32: "Atención",
}
TODOS_LOS_PROBLEMAS = sum(PROBLEMAS)
# Se puede calificar hasta este rato después del cobro: el trigger de la base aplica la misma regla.
VENTANA_DESPUES_DEL_COBRO_MIN = 60
# La reseña (migración 018): unas pocas palabras, que pasan por el filtro de app/services/moderacion.py.
PALABRAS_RESENA = 6
LARGO_RESENA = 60


class Calificacion(DeEstablecimiento, Base):
    """Cómo le fue al cliente: un puntaje y lo que falló, una por turno (migración 015).

    Es anónima: no guarda datos de la persona, y la gerencia ve promedios y totales, nunca una opinión suelta con su
    hora. La reseña de hasta seis palabras se le muestra sin hora ni habitación. No se cambia ni se borra.
    """

    __tablename__ = "calificaciones"
    __table_args__ = (UniqueConstraint("establecimiento_id", "turno_id", name="calificaciones_una_por_turno"),)

    id = Column(Integer, primary_key=True)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=False)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    puntaje = Column(SmallInteger, nullable=False)
    problemas = Column(SmallInteger, nullable=False, default=0)
    resena = Column(String(LARGO_RESENA), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
