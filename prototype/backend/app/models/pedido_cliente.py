from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

ARTICULO = "ARTICULO"
# Los avisos que el cliente puede mandar (CHECK de la migración 013). No hay texto libre.
AVISOS = {
    "TOALLAS": "Pide toallas",
    "LLAMAR": "Pide que llamen a la habitación",
    "SALIDA": "Avisa que se va",
}
PENDIENTE = "Pendiente"
ATENDIDO = "Atendido"
RECHAZADO = "Rechazado"


class PedidoCliente(DeEstablecimiento, Base):
    """Lo que el cliente pide desde su habitación con el QR del ticket (migración 013).

    Un pedido no toca el stock ni la cuenta: el conserje lo atiende, y recién ahí se carga como consumo. Se atiende una
    sola vez (trigger_pedido_cliente_atencion) y no se borra.
    """

    __tablename__ = "pedidos_cliente"

    id = Column(Integer, primary_key=True)
    turno_id = Column(UUID(as_uuid=True), ForeignKey("turnos.id"), nullable=False)
    tipo = Column(String(10), nullable=False)
    articulo_id = Column(Integer, ForeignKey("articulos.id"), nullable=True)
    cantidad = Column(Integer, nullable=True)
    estado = Column(String(10), nullable=False, default=PENDIENTE)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    atendido_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    atendido_en = Column(DateTime(timezone=True), nullable=True)
