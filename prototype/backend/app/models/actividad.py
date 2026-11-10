from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects import sqlite

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

# Categorías del registro (CHECK de la migración 007).
INVENTARIO = "INVENTARIO"
TARIFA = "TARIFA"
CAJA = "CAJA"
HABITACION = "HABITACION"
PERSONAL = "PERSONAL"
ESTABLECIMIENTO = "ESTABLECIMIENTO"


class RegistroActividad(DeEstablecimiento, Base):
    """Quién cambió qué del inventario o de la configuración, y cuándo (migración 007).

    Es de solo agregado: después de guardarse solo cambia la marca de revisión de la gerencia, una vez
    (trigger_registro_actividad). Lo que hace un conserje queda «por revisar».
    """

    __tablename__ = "registro_actividad"

    # BIGSERIAL en PostgreSQL; en SQLite solo INTEGER es autoincremental.
    id = Column(BigInteger().with_variant(sqlite.INTEGER(), "sqlite"), primary_key=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=True)
    categoria = Column(String(20), nullable=False)
    accion = Column(String(40), nullable=False)
    descripcion = Column(String(300), nullable=False)
    articulo_id = Column(Integer, ForeignKey("articulos.id"), nullable=True)
    cantidad = Column(Integer, nullable=True)
    valor_anterior = Column(String(80), nullable=True)
    valor_nuevo = Column(String(80), nullable=True)
    requiere_revision = Column(Boolean, nullable=False, default=False)
    revisado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    revisado_en = Column(DateTime(timezone=True), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
