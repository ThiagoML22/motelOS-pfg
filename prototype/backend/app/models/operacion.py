from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

# Motivos de un traslado (CHECK de la migración 016).
FALLA = "FALLA"
PEDIDO_DEL_CLIENTE = "CLIENTE"
OTRO = "OTRO"
MOTIVOS_TRASLADO = {FALLA: "Falla en la habitación", PEDIDO_DEL_CLIENTE: "Pedido del cliente", OTRO: "Otro motivo"}

MANTENIMIENTO = "MANTENIMIENTO"
TIPOS_ARREGLO = {FALLA: "Falla", MANTENIMIENTO: "Mantenimiento"}
RUBROS = {
    "AIRE": "Aire o calefacción",
    "PLOMERIA": "Plomería",
    "ELECTRICIDAD": "Electricidad",
    "TV": "TV o Wi-Fi",
    "MUEBLES": "Muebles",
    "OTRO": "Otro",
}
ABIERTO = "Abierto"
EN_CURSO = "En curso"
RESUELTO = "Resuelto"
SIN_RESOLVER = (ABIERTO, EN_CURSO)

PRENDAS = {"TOALLAS": "Toallas", "SABANAS": "Sábanas"}
APERTURA = "APERTURA"
CIERRE = "CIERRE"
# Cuánto suma cada movimiento a lo que hay en el motel.
MOVIMIENTOS_ROPA = {
    "LAVANDERIA_SALE": ("Salió a la lavandería", -1),
    "LAVANDERIA_VUELVE": ("Volvió de la lavandería", 1),
    "COMPRA": ("Compra", 1),
    "BAJA": ("Baja por rotura", -1),
}


def _ahora() -> datetime:
    return datetime.now(UTC)


class TrasladoTurno(DeEstablecimiento, Base):
    """Un turno que pasó a otra habitación (migración 016). Es de solo agregado.

    El turno sigue siendo el mismo: conserva su hora, su tarifa, su cuenta y el enlace del cliente. La base no deja
    cambiarle la habitación sin esta fila.
    """

    __tablename__ = "traslados_turno"

    id = Column(Integer, primary_key=True)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=False)
    desde_habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    hacia_habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    motivo = Column(String(10), nullable=False)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=_ahora)


class Arreglo(DeEstablecimiento, Base):
    """Una falla o un mantenimiento de una habitación, con quién lo reparó y cuánto costó (migración 016).

    Lo reportado no cambia y se resuelve una sola vez; después solo se puede cargar el costo, que suele llegar con la
    factura. El costo es informativo: no mueve la caja. No se borra.
    """

    __tablename__ = "arreglos"

    id = Column(Integer, primary_key=True)
    habitacion_id = Column(Integer, ForeignKey("habitaciones.id"), nullable=False)
    tipo = Column(String(15), nullable=False)
    rubro = Column(String(15), nullable=False)
    descripcion = Column(String(200), nullable=False)
    estado = Column(String(10), nullable=False, default=ABIERTO)
    abierto_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    abierto_en = Column(DateTime(timezone=True), nullable=False, default=_ahora)
    resuelto_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    resuelto_en = Column(DateTime(timezone=True), nullable=True)
    reparado_por = Column(String(80), nullable=True)
    trabajo = Column(String(200), nullable=True)
    costo = Column(Numeric(10, 2), nullable=True)


class RopaConteo(DeEstablecimiento, Base):
    """Cuánta ropa hay en el motel al abrir o cerrar una guardia (migración 016). Es de solo agregado."""

    __tablename__ = "ropa_conteos"
    __table_args__ = (
        UniqueConstraint("establecimiento_id", "guardia_id", "momento", "prenda", name="ropa_conteos_uno_por_momento"),
    )

    id = Column(Integer, primary_key=True)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    momento = Column(String(10), nullable=False)
    prenda = Column(String(10), nullable=False)
    limpias = Column(Integer, nullable=False)
    sucias = Column(Integer, nullable=False)
    en_habitaciones = Column(Integer, nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=_ahora)

    @property
    def total(self) -> int:
        return self.limpias + self.sucias + self.en_habitaciones


class RopaMovimiento(DeEstablecimiento, Base):
    """Ropa que entra o sale del motel: así una diferencia sin explicar es una diferencia de verdad (migración 016)."""

    __tablename__ = "ropa_movimientos"

    id = Column(Integer, primary_key=True)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    prenda = Column(String(10), nullable=False)
    tipo = Column(String(20), nullable=False)
    cantidad = Column(Integer, nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=_ahora)


class Traspaso(DeEstablecimiento, Base):
    """Lo que recibió quien abrió una guardia, como foto: no cambia aunque cambie la ventanilla (migración 016).

    No lleva importes ni patentes. La confirma quien entra, y es de solo agregado.
    """

    __tablename__ = "traspasos"
    __table_args__ = (UniqueConstraint("establecimiento_id", "guardia_id", name="traspasos_uno_por_guardia"),)

    id = Column(Integer, primary_key=True)
    guardia_saliente_id = Column(Integer, ForeignKey("guardias.id"), nullable=True)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    resumen = Column(JSON, nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=_ahora)
