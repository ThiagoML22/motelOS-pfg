from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.core.database import Base
from app.core.inquilino import DeEstablecimiento

SIN_LUGAR = "SIN_LUGAR"
ESPERA = "ESPERA"
PRECIO = "PRECIO"
# Por qué se fue el cliente (CHECK de la migración 011).
MOTIVOS = {SIN_LUGAR: "No había lugar", ESPERA: "No quiso esperar", PRECIO: "Le pareció caro"}


class ClientePerdido(DeEstablecimiento, Base):
    """El cliente que se fue sin quedarse (migración 011).

    Sin esto el análisis solo ve la demanda atendida. Es de solo agregado, a nombre de quien atiende y en su guardia
    abierta (trigger_cliente_perdido). No guarda ningún dato del cliente.
    """

    __tablename__ = "clientes_perdidos"

    id = Column(Integer, primary_key=True)
    motivo = Column(String(10), nullable=False)
    categoria_id = Column(Integer, ForeignKey("categorias_habitacion.id"), nullable=True)
    operador_id = Column(Integer, ForeignKey("operadores.id"), nullable=False)
    guardia_id = Column(Integer, ForeignKey("guardias.id"), nullable=False)
    creado_en = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
