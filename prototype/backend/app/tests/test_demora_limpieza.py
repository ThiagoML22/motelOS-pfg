"""RF-12: la grilla marca las habitaciones que superan 30 min En Limpieza (catálogo v6, validado en el acta del 23/09).

Criterio: habitación En Limpieza desde hace más de 30 min; al refrescar la grilla, la tarjeta muestra la marca con los
minutos transcurridos; con 30 min o menos no se muestra. Los minutos los calcula el servidor.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.core.config import settings
from app.models.evento_habitacion import MANUAL, EventoHabitacion
from app.models.habitacion import Habitacion

GRILLA = "/api/v1/habitaciones/"


async def _en_limpieza_hace(db, habitacion_id: int, minutos: float) -> None:
    """Deja la habitación En Limpieza con su paso a ese estado `minutos` atrás en el historial."""
    db.add(
        EventoHabitacion(
            habitacion_id=habitacion_id,
            estado_anterior="Libre",
            estado_nuevo="En Limpieza",
            origen=MANUAL,
            operador_id=1,
            creado_en=datetime.now(UTC) - timedelta(minutes=minutos),
        )
    )
    await db.execute(update(Habitacion).where(Habitacion.id == habitacion_id).values(estado="En Limpieza"))
    await db.commit()


async def _tarjeta(cliente, habitacion_id: int) -> dict:
    return next(h for h in (await cliente.get(GRILLA)).json() if h["id"] == habitacion_id)


@pytest.mark.parametrize(("minutos", "demora"), [(29, False), (30, False), (31, True)])
async def test_rf_12_la_marca_aparece_pasados_los_30_minutos(client, db, minutos, demora):
    await _en_limpieza_hace(db, 2, minutos)
    tarjeta = await _tarjeta(client, 2)
    assert tarjeta["estado"] == "En Limpieza"
    assert tarjeta["minutos_en_limpieza"] == minutos
    assert tarjeta["demora_limpieza"] is demora


async def test_cuenta_desde_el_ultimo_paso_a_limpieza(client, db):
    # Una limpieza vieja que terminó no cuenta: vale la que empezó hace 5 minutos.
    await _en_limpieza_hace(db, 2, 90)
    await db.execute(update(Habitacion).where(Habitacion.id == 2).values(estado="Libre"))
    await db.commit()
    await _en_limpieza_hace(db, 2, 5)
    tarjeta = await _tarjeta(client, 2)
    assert tarjeta["minutos_en_limpieza"] == 5 and tarjeta["demora_limpieza"] is False


async def test_otros_estados_y_limpiezas_sin_historial_no_se_marcan(client, db):
    await db.execute(update(Habitacion).where(Habitacion.id == 1).values(estado="En Limpieza"))
    await db.commit()
    grilla = {h["id"]: h for h in (await client.get(GRILLA)).json()}
    # La 1 está En Limpieza sin un paso registrado (datos anteriores a la migración 011): sin minutos ni marca.
    assert grilla[1]["minutos_en_limpieza"] is None and grilla[1]["demora_limpieza"] is False
    # La 2 está Libre y la 3 en Mantenimiento.
    assert all(grilla[i]["en_limpieza_desde"] is None and not grilla[i]["demora_limpieza"] for i in (2, 3))


async def test_el_umbral_es_configurable(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEMORA_LIMPIEZA_MIN", 10)
    await _en_limpieza_hace(db, 2, 12)
    assert (await _tarjeta(client, 2))["demora_limpieza"] is True


async def test_cobrar_y_liberar_cuentan_con_el_historial_real(client):
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    cobro = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar",
                              json={"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]})
    assert cobro.status_code == 200, cobro.text
    tarjeta = await _tarjeta(client, 1)
    assert tarjeta["estado"] == "En Limpieza" and tarjeta["minutos_en_limpieza"] == 0
    assert tarjeta["demora_limpieza"] is False
    await client.patch("/api/v1/habitaciones/1/liberar")
    assert (await _tarjeta(client, 1))["minutos_en_limpieza"] is None
