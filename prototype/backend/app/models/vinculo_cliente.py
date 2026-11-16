from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects import sqlite
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

# Cómo llegó el celular a la estadía (CHECK de la migración 020).
POR_QR = "QR"
INVITADO = "INVITADO"


class VinculoCliente(DeEstablecimiento, Base):
    """Un celular vinculado a una estadía con el QR fijo de la habitación (migración 020).

    Se reconoce por una cookie aleatoria que la página no puede leer; la base guarda solo su resumen SHA-256 (huella).
    Solo se revoca, una vez y a nombre de quien atiende la ventanilla (trigger_vinculo_revocacion); se depura a los
    30 días.
    """

    __tablename__ = "vinculos_cliente"
    __table_args__ = (
        UniqueConstraint("establecimiento_id", "turno_id", "huella", name="vinculos_un_celular_por_estadia"),
    )

    id = Column(BigInteger().with_variant(sqlite.INTEGER(), "sqlite"), primary_key=True)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=False)
    huella = Column(String(64), nullable=False)
    origen = Column(String(10), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    revocado_en = Column(DateTime(timezone=True), nullable=True)
    revocado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
