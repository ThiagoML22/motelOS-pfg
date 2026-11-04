from datetime import UTC, datetime

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects import sqlite

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento


class SelloArqueo(DeEstablecimiento, Base):
    """La huella de un arqueo, encadenada con la del anterior (migración 012). Es de solo agregado."""

    __tablename__ = "sellos_arqueo"
    __table_args__ = (UniqueConstraint("establecimiento_id", "secuencia", name="sellos_secuencia_por_establecimiento"),)

    # BIGSERIAL en PostgreSQL; en SQLite solo INTEGER es autoincremental.
    id = Column(BigInteger().with_variant(sqlite.INTEGER(), "sqlite"), primary_key=True)
    arqueo_id = Column(Integer, ForeignKey("arqueos_caja.id"), nullable=False, unique=True)
    secuencia = Column(Integer, nullable=False)
    huella_anterior = Column(String(64), nullable=False)
    huella = Column(String(64), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
