from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

ROL_OPERADOR = "OPERADOR"
ROL_ADMINISTRADOR = "ADMINISTRADOR"
# Equipo que da de alta establecimientos (migración 006). No pertenece a ninguno ni ve su operación.
ROL_PLATAFORMA = "PLATAFORMA"

SIN_ESTABLECIMIENTO = text("establecimiento_id IS NULL")


class Operador(DeEstablecimiento, Base):
    """Persona que usa el sistema (RNF-04): un conserje (OPERADOR), la gerencia (ADMINISTRADOR) o la plataforma.

    Solo se guarda un usuario y un nombre visible: ningún dato personal del empleado. Desde el panel de la
    gerencia (RF-11) la aplicación da de alta y de baja conserjes, pero no elige el rol: la columna toma su
    valor por defecto, OPERADOR (migración 005). Tampoco cambia roles ni claves; eso lo hace el dueño de las
    tablas con scripts/crear_operador.py. La única excepción es la gerencia inicial de un establecimiento nuevo,
    que crea la función crear_gerencia_inicial de la base (migración 006).
    """

    __tablename__ = "operadores"
    # El usuario es único dentro de cada establecimiento; los de la plataforma, entre sí (migración 006).
    __table_args__ = (
        UniqueConstraint("establecimiento_id", "usuario", name="operadores_usuario_por_establecimiento"),
        Index("operadores_usuario_plataforma", "usuario", unique=True, postgresql_where=SIN_ESTABLECIMIENTO,
              sqlite_where=SIN_ESTABLECIMIENTO),
    )

    # Nulo solo para la plataforma (CHECK operador_de_un_establecimiento).
    establecimiento_id = Column(Integer, ForeignKey("establecimientos.id"), nullable=True, index=True)
    id = Column(Integer, primary_key=True)
    usuario = Column(String(40), nullable=False)
    nombre_visible = Column(String(60), nullable=False)
    hash_clave = Column(String(255), nullable=False)
    rol = Column(String(20), nullable=False, server_default=ROL_OPERADOR)
    activo = Column(Boolean, nullable=False, default=True)
    intentos_fallidos = Column(Integer, nullable=False, default=0)
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)
    ultimo_acceso = Column(DateTime(timezone=True), nullable=True)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
