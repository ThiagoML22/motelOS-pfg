from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, false, text, true

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
    # Apariencia y avisos (migración 009): acento de la interfaz, eslogan del ingreso, anticipación del aviso «por
    # vencer» de la grilla y alertas sonoras de la ventanilla.
    color_marca = Column(String(7), nullable=True)
    eslogan = Column(String(120), nullable=True)
    aviso_por_vencer_min = Column(Integer, nullable=False, default=10, server_default=text("10"))
    alertas_sonoras = Column(Boolean, nullable=False, default=False, server_default=false())
