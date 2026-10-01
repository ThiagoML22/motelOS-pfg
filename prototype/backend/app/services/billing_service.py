"""Liquidación temporal de la estadía (RN-DER-01).

Funciones puras: no acceden a la base de datos ni al reloj del sistema, por lo que
pueden verificarse de forma determinística.
"""

import math
from datetime import timedelta
from decimal import Decimal

TARIFA_BASE = Decimal("12000")
ESTADIA_BASE_MIN = 120
TOLERANCIA_MIN = 10
FRACCION_MIN = 30
TARIFA_FRACCION = Decimal("3500")


def calcular_sobreturno(duracion: timedelta) -> Decimal:
    """Importe de sobreturno para una estadía de la duración indicada.

    Hasta ESTADIA_BASE_MIN + TOLERANCIA_MIN minutos no se cobra sobreturno. Superada la tolerancia,
    el excedente se mide desde el fin de la estadía base y cada fracción de FRACCION_MIN minutos
    (o porción) suma TARIFA_FRACCION.
    """
    segundos = duracion.total_seconds()
    if segundos <= (ESTADIA_BASE_MIN + TOLERANCIA_MIN) * 60:
        return Decimal("0")
    excedente_seg = segundos - ESTADIA_BASE_MIN * 60
    fracciones = math.ceil(excedente_seg / (FRACCION_MIN * 60))
    return TARIFA_FRACCION * fracciones
