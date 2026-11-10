from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

PENDIENTE = "Pendiente"
RECIBIDO = "Recibido"
ANULADO = "Anulado"


class PedidoReposicion(DeEstablecimiento, Base):
    """Pedido de mercadería a un proveedor (migración 010). No se borra: pasa una vez de Pendiente a Recibido o
    Anulado (trigger_pedido)."""

    __tablename__ = "pedidos_reposicion"

    id = Column(Integer, primary_key=True)
    creado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    proveedor = Column(String(80), nullable=True)
    nota = Column(String(300), nullable=True)
    estado = Column(String(10), nullable=False, default=PENDIENTE)
    cerrado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    cerrado_en = Column(DateTime(timezone=True), nullable=True)


class PedidoItem(DeEstablecimiento, Base):
    """Un artículo de un pedido: lo pedido y, al recibirlo, lo que llegó (que se suma al stock)."""

    __tablename__ = "pedido_items"
    __table_args__ = (UniqueConstraint("pedido_id", "articulo_id", name="pedido_items_un_articulo"),)

    id = Column(Integer, primary_key=True)
    pedido_id = Column(Integer, ForeignKey("pedidos_reposicion.id"), nullable=False, index=True)
    articulo_id = Column(Integer, ForeignKey("articulos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    recibida = Column(Integer, nullable=True)
