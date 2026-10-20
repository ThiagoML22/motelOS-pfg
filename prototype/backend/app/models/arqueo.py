from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String

from app.core.database import Base


class ArqueoCaja(Base):
    """Cierre de caja ciego de una guardia (RF-08) con su diferencia clasificada (RF-09).

    En PostgreSQL el trigger calcular_arqueo recalcula los totales del sistema, la diferencia y la
    categoría al insertar, y trigger_arqueo_inmutable impide modificarlo o borrarlo (RN-RES-02).
    """

    __tablename__ = "arqueos_caja"

    id = Column(Integer, primary_key=True)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False, unique=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    declarado_efectivo = Column(Numeric(12, 2), nullable=False)
    declarado_posnet = Column(Numeric(12, 2), nullable=False, default=0)
    declarado_mercado_pago = Column(Numeric(12, 2), nullable=False, default=0)
    total_declarado = Column(Numeric(12, 2), nullable=False)
    sistema_efectivo = Column(Numeric(12, 2), nullable=False, default=0)
    sistema_posnet = Column(Numeric(12, 2), nullable=False, default=0)
    sistema_mercado_pago = Column(Numeric(12, 2), nullable=False, default=0)
    total_sistema = Column(Numeric(12, 2), nullable=False, default=0)
    diferencia = Column(Numeric(12, 2), nullable=False)
    categoria = Column(String(10), nullable=False)
    confirmado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    # Quién confirmó el recuento: el propio operador o, en un cierre supervisado, la gerencia (con observación).
    confirmado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    observacion = Column(String(300), nullable=True)
