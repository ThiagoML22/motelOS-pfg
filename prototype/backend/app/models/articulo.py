from sqlalchemy import Boolean, Column, Integer, Numeric, String, UniqueConstraint, true

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento


class Articulo(DeEstablecimiento, Base):
    __tablename__ = "articulos"
    __table_args__ = (UniqueConstraint("establecimiento_id", "codigo", name="articulos_codigo_por_establecimiento"),)

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), nullable=False)
    descripcion = Column(String(255), nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    stock_actual = Column(Integer, nullable=False)
    categoria = Column(String(50))
    # RF-11: baja lógica; los consumos registrados siguen referenciando el artículo.
    activo = Column(Boolean, nullable=False, default=True, server_default=true())
