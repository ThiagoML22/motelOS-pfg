from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

ARTICULO = "ARTICULO"
SALIDA = "SALIDA"
TIEMPO = "TIEMPO"
# Los avisos que el cliente puede mandar (CHECK de las migraciones 013 y 015). No hay texto libre.
AVISOS = {
    "TOALLAS": "Pide toallas",
    "LLAMAR": "Pide que llamen a la habitación",
    SALIDA: "Pide la cuenta",
    TIEMPO: "Se queda más tiempo",
}
# Los que se mandan con un toque; la cuenta y el tiempo tienen su propio paso en la página.
AVISOS_DIRECTOS = ("TOALLAS", "LLAMAR")
MINUTOS_EXTRA = (30, 60, 120)
MEDIOS_PAGO = {"EFECTIVO": "Efectivo", "POSNET": "Tarjeta", "MERCADO_PAGO": "Mercado Pago"}
PENDIENTE = "Pendiente"
EN_CAMINO = "En camino"
ATENDIDO = "Atendido"
RECHAZADO = "Rechazado"
SIN_RESOLVER = (PENDIENTE, EN_CAMINO)


class PedidoCliente(DeEstablecimiento, Base):
    """Lo que el cliente pide desde su habitación con el QR del ticket (migración 013).

    Un pedido no toca el stock ni la cuenta: el conserje lo atiende, y recién ahí se carga como consumo. Se atiende una
    sola vez (trigger_pedido_cliente_atencion) y no se borra. Las líneas de un carrito comparten `lote` (migración 015).
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
    lote = Column(UUID(as_uuid=True), nullable=True)
    # Cuánto más se queda, en un aviso de tiempo, y cómo va a pagar, en un pedido de cuenta.
    minutos = Column(Integer, nullable=True)
    medio_pago = Column(String(20), nullable=True)
    llevado_por_id = Column(Integer, ForeignKey("operadores.id"), nullable=True)
    llevado_en = Column(DateTime(timezone=True), nullable=True)
