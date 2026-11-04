"""Registra todos los modelos en Base.metadata (las claves foráneas se resuelven por nombre de tabla)."""

from app.models import (  # noqa: F401
    actividad,
    arqueo,
    articulo,
    categoria,
    cliente_perdido,
    configuracion,
    consumo,
    establecimiento,
    estadia_activa,
    evento_habitacion,
    guardia,
    habitacion,
    novedad,
    operador,
    pago,
    pedido,
    pedido_cliente,
    sello_arqueo,
    tarifa,
    turno,
)
