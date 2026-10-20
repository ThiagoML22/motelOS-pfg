"""Registra todos los modelos en Base.metadata (las claves foráneas se resuelven por nombre de tabla)."""

from app.models import (  # noqa: F401
    arqueo,
    articulo,
    consumo,
    estadia_activa,
    guardia,
    habitacion,
    operador,
    pago,
    tarifa,
    turno,
)
