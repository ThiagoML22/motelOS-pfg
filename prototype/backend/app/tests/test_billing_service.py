from datetime import timedelta
from decimal import Decimal

import pytest

from app.services.billing_service import TARIFA_ESTANDAR, ParametrosTarifa, calcular_sobreturno


@pytest.mark.parametrize(
    "duracion, esperado",
    [
        (timedelta(0), 0),
        (timedelta(minutes=119), 0),
        (timedelta(minutes=120), 0),  # la estadía base incluye exactamente 120 minutos
        (timedelta(minutes=120, seconds=1), 2500),  # cualquier porción excedente suma una fracción
        (timedelta(minutes=125), 2500),
        (timedelta(minutes=150), 2500),  # exactamente una fracción de 30 min sobre la base
        (timedelta(minutes=150, seconds=1), 5000),
        (timedelta(minutes=170), 5000),
        (timedelta(minutes=180), 5000),
        (timedelta(minutes=181), 7500),
    ],
)
def test_calcular_sobreturno_rn_der_01(duracion, esperado):
    assert calcular_sobreturno(duracion) == Decimal(esperado)


def test_tarifa_estandar_coincide_con_el_catalogo():
    assert TARIFA_ESTANDAR.tarifa_base == Decimal("8000")
    assert TARIFA_ESTANDAR.estadia_base_min == 120
    assert TARIFA_ESTANDAR.fraccion_min == 30
    assert TARIFA_ESTANDAR.tarifa_fraccion == Decimal("2500")
    assert TARIFA_ESTANDAR.tolerancia_min == 0


def test_duracion_negativa_no_genera_cargo():
    assert calcular_sobreturno(timedelta(minutes=-5)) == 0


def test_los_parametros_de_la_tarifa_gobiernan_el_calculo():
    con_tolerancia = ParametrosTarifa(Decimal("10000"), 90, 10, 20, Decimal("1000"))

    assert calcular_sobreturno(timedelta(minutes=100), con_tolerancia) == 0  # dentro de la tolerancia
    assert calcular_sobreturno(timedelta(minutes=100, seconds=1), con_tolerancia) == 1000
    assert calcular_sobreturno(timedelta(minutes=130, seconds=1), con_tolerancia) == 3000
