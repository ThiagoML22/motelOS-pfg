from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, true

from app.core.database import Base


class Establecimiento(Base):
    """Un motel que usa el sistema (inquilino, migración 006).

    No es un modelo DeEstablecimiento: el inicio de sesión busca el código antes de saber a qué establecimiento
    pertenece el usuario. Solo guarda datos del comercio (nombre, domicilio y teléfono), ninguno personal.
    """

    __tablename__ = "establecimientos"

    id = Column(Integer, primary_key=True)
    codigo = Column(String(30), unique=True, nullable=False)
    nombre = Column(String(80), nullable=False)
    domicilio = Column(String(120), nullable=True)
    telefono = Column(String(40), nullable=True)
    # Texto al pie del comprobante de arqueo en PDF (RF-10).
    leyenda_comprobante = Column(String(200), nullable=True)
    activo = Column(Boolean, nullable=False, default=True, server_default=true())
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
