"""Liquidación temporal de la estadía (RN-DER-01).

Funciones puras: no acceden a la base de datos ni al reloj del sistema, por lo que
pueden verificarse de forma determinística.
"""

import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal


@dataclass(frozen=True)
class ParametrosTarifa:
    """Parámetros de liquidación de una tarifa vigente."""

    tarifa_base: Decimal
    estadia_base_min: int
    tolerancia_min: int
    fraccion_min: int
    tarifa_fraccion: Decimal


# Tarifa estándar del establecimiento: estadía base de 120 minutos por $8.000 y, superada,
# cada fracción de 30 minutos (o porción) suma $2.500. No se aplica tolerancia.
TARIFA_ESTANDAR = ParametrosTarifa(
    tarifa_base=Decimal("8000"),
    estadia_base_min=120,
    tolerancia_min=0,
    fraccion_min=30,
    tarifa_fraccion=Decimal("2500"),
)


def calcular_sobreturno(duracion: timedelta, tarifa: ParametrosTarifa = TARIFA_ESTANDAR) -> Decimal:
    """Importe de sobreturno para una estadía de la duración indicada.

    Hasta estadia_base_min + tolerancia_min minutos no se cobra sobreturno. Superado ese límite,
    el excedente se mide desde el fin de la estadía base y cada fracción de fraccion_min minutos
    (o porción) suma tarifa_fraccion.
    """
    segundos = duracion.total_seconds()
    if segundos <= (tarifa.estadia_base_min + tarifa.tolerancia_min) * 60:
        return Decimal("0")
    excedente_seg = segundos - tarifa.estadia_base_min * 60
    fracciones = math.ceil(excedente_seg / (tarifa.fraccion_min * 60))
    return tarifa.tarifa_fraccion * fracciones
