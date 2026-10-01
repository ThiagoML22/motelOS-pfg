from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.turno import Turno
from app.services.billing_service import calcular_sobreturno


@pytest.mark.parametrize(
    "duracion, esperado",
    [
        (timedelta(0), 0),
        (timedelta(minutes=119), 0),
        (timedelta(minutes=120), 0),
        (timedelta(minutes=125), 0),
        (timedelta(minutes=130), 0),  # el límite de la tolerancia todavía no se cobra
        (timedelta(minutes=130, seconds=1), 3500),  # superada la tolerancia: una fracción
        (timedelta(minutes=131), 3500),
        (timedelta(minutes=150), 3500),  # exactamente una fracción de 30 min sobre la base
        (timedelta(minutes=150, seconds=1), 7000),  # cualquier porción adicional suma otra fracción
        (timedelta(minutes=170), 7000),
        (timedelta(minutes=180), 7000),
        (timedelta(minutes=181), 10500),
    ],
)
def test_calcular_sobreturno_rn_der_01(duracion, esperado):
    assert calcular_sobreturno(duracion) == Decimal(esperado)


def test_duracion_negativa_no_genera_cargo():
    assert calcular_sobreturno(timedelta(minutes=-5)) == 0


async def _turno_con_antiguedad(client: AsyncClient, db, minutos: int) -> str:
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": 1})
    assert resp.status_code == 201
    fila = (await db.execute(select(Turno))).scalars().first()
    fila.hora_inicio = datetime.now(UTC) - timedelta(minutes=minutos, seconds=2)
    await db.commit()
    return resp.json()["id"]


async def test_resumen_dentro_de_la_tolerancia_no_cobra_sobreturno(client: AsyncClient, db):
    turno_id = await _turno_con_antiguedad(client, db, 125)

    resumen = (await client.get(f"/api/v1/turnos/{turno_id}/resumen")).json()

    assert resumen["total_sobreturno"] == 0
    assert resumen["total_general"] == 12000


async def test_resumen_superada_la_tolerancia_cobra_una_fraccion(client: AsyncClient, db):
    turno_id = await _turno_con_antiguedad(client, db, 131)

    resumen = (await client.get(f"/api/v1/turnos/{turno_id}/resumen")).json()

    assert resumen["total_sobreturno"] == 3500
    assert resumen["total_general"] == 15500


async def test_cobro_dentro_de_la_tolerancia_liquida_solo_la_base(client: AsyncClient, db):
    turno_id = await _turno_con_antiguedad(client, db, 128)

    resp = await client.post(f"/api/v1/turnos/{turno_id}/cerrar", json={"monto": 12000, "medio_pago": "EFECTIVO"})

    assert resp.status_code == 200
