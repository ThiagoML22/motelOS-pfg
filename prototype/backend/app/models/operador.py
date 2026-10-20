from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.core.database import Base

ROL_OPERADOR = "OPERADOR"
ROL_ADMINISTRADOR = "ADMINISTRADOR"


class Operador(Base):
    """Persona que usa el sistema (RNF-04): un conserje (OPERADOR) o la gerencia (ADMINISTRADOR).

    Solo se guarda un usuario y un nombre visible: ningún dato personal del empleado. La aplicación
    no da de alta operadores ni cambia roles o claves (permisos de db/migraciones/002_v2_caja.sql);
    eso lo hace el dueño de las tablas con scripts/crear_operador.py.
    """

    __tablename__ = "operadores"

    id = Column(Integer, primary_key=True)
    usuario = Column(String(40), unique=True, nullable=False)
    nombre_visible = Column(String(60), nullable=False)
    hash_clave = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    intentos_fallidos = Column(Integer, nullable=False, default=0)
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)
    ultimo_acceso = Column(DateTime(timezone=True), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
