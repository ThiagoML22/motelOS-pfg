from sqlalchemy import Boolean, Column, Integer, Numeric, String, true

from app.core.database import Base


class Articulo(Base):
    __tablename__ = "articulos"

    id = Column(Integer, primary_key=True, index=True)
    codigo = Column(String(50), unique=True, nullable=False)
    descripcion = Column(String(255), nullable=False)
    precio_unitario = Column(Numeric(10, 2), nullable=False)
    stock_actual = Column(Integer, nullable=False)
    categoria = Column(String(50))
    # RF-11: baja lógica; los consumos registrados siguen referenciando el artículo.
    activo = Column(Boolean, nullable=False, default=True, server_default=true())
