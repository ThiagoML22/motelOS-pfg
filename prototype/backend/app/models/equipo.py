from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects import sqlite

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

# Estados de un equipo (CHECK de la migración 019).
PENDIENTE = "PENDIENTE"
AUTORIZADO = "AUTORIZADO"
BLOQUEADO = "BLOQUEADO"
ESTADOS = (PENDIENTE, AUTORIZADO, BLOQUEADO)

# Por qué se rechazó un intento.
POR_EQUIPO = "EQUIPO"
POR_RED = "RED"


class Equipo(DeEstablecimiento, Base):
    """Un navegador desde el que un conserje intentó entrar o que la gerencia autorizó (migración 019).

    Se reconoce por una cookie aleatoria que la página no puede leer; la base guarda solo su resumen SHA-256 (huella),
    como con las claves. No se borra: un equipo que ya no sirve queda bloqueado.
    """

    __tablename__ = "equipos"
    __table_args__ = (UniqueConstraint("establecimiento_id", "huella", name="equipos_una_huella"),)

    id = Column(Integer, primary_key=True)
    huella = Column(String(64), nullable=False)
    nombre = Column(String(40), nullable=True)
    estado = Column(String(12), nullable=False, default=PENDIENTE)
    # «Chrome en Android (celular)»: lo que dice el propio navegador, resumido. No identifica a la persona.
    descripcion = Column(String(60), nullable=False)
    ultima_ip = Column(String(45), nullable=True)
    ultimo_operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    ultimo_uso = Column(DateTime(timezone=True), nullable=True)
    decidido_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    decidido_en = Column(DateTime(timezone=True), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class IntentoAcceso(DeEstablecimiento, Base):
    """Un conserje que quiso entrar desde un equipo o una red no permitidos (migración 019). Solo agregado; se borra
    a los 90 días (trigger_intento_baja)."""

    __tablename__ = "intentos_acceso"

    id = Column(BigInteger().with_variant(sqlite.INTEGER(), "sqlite"), primary_key=True)
    equipo_id = Column(Integer, ForeignKey("equipos.id"), nullable=True)
    # Solo si el usuario existe: un texto cualquiera podría ser una clave escrita en el campo equivocado.
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    clave_correcta = Column(Boolean, nullable=False)
    motivo = Column(String(10), nullable=False)
    ip = Column(String(45), nullable=True)
    descripcion = Column(String(60), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
