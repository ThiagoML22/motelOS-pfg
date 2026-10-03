from sqlalchemy import Boolean, Column, Integer, Numeric, String

from app.core.database import Base
from app.services.billing_service import ParametrosTarifa


class Tarifa(Base):
    __tablename__ = "tarifas"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), unique=True, nullable=False)
    tarifa_base = Column(Numeric(10, 2), nullable=False)
    estadia_base_min = Column(Integer, nullable=False, default=120)
    tolerancia_min = Column(Integer, nullable=False, default=0)
    fraccion_min = Column(Integer, nullable=False, default=30)
    tarifa_fraccion = Column(Numeric(10, 2), nullable=False)
    vigente = Column(Boolean, nullable=False, default=True)

    def parametros(self) -> ParametrosTarifa:
        return ParametrosTarifa(
            tarifa_base=self.tarifa_base,
            estadia_base_min=self.estadia_base_min,
            tolerancia_min=self.tolerancia_min,
            fraccion_min=self.fraccion_min,
            tarifa_fraccion=self.tarifa_fraccion,
        )
