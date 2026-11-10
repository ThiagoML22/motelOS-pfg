from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric

from app.core.database import Base


class ConfiguracionCaja(Base):
    """Fondo de cambio vigente (RF-11, acta del 27/10/2026). Una fila por establecimiento (migración 006).

    La guardia copia el monto al abrirse (Guardia.fondo_inicial): un cambio rige desde la guardia siguiente.
    La clave primaria es el establecimiento, por eso no usa la mezcla DeEstablecimiento: se busca con
    db.get(ConfiguracionCaja, establecimiento_id).
    """

    __tablename__ = "configuracion_caja"

    establecimiento_id = Column(Integer, ForeignKey("establecimientos.id"), primary_key=True, autoincrement=False)
    fondo_cambio = Column(Numeric(12, 2), nullable=False)
    actualizado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    actualizado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
