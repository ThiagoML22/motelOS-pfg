"""RF-12: la grilla marca las habitaciones que superan 30 min En Limpieza (catálogo v6, validado en el acta del 23/09).

Criterio: habitación En Limpieza desde hace más de 30 min; al refrescar la grilla, la tarjeta muestra la marca con los
minutos transcurridos; con 30 min o menos no se muestra. Los minutos los calcula el servidor.

En PostgreSQL cada evento toma la hora de la base (trigger de la migración 011): no se puede fabricar una limpieza que
empezó hace 31 minutos. Por eso las pruebas recorren el flujo real (cobro → limpieza) y adelantan el reloj del servidor.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.models.evento_habitacion import EventoHabitacion
from app.models.habitacion import Habitacion
from app.services import rotacion

GRILLA = "/api/v1/habitaciones/"
COBRO = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}


async def _cobrar(cliente, habitacion_id: int = 1) -> None:
    datos = {"habitacion_id": habitacion_id, "tipo_cliente": "Auto"}
    turno = (await cliente.post("/api/v1/turnos/", json=datos)).json()
    resp = await cliente.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    assert resp.status_code == 200, resp.text


async def _inicio_de_la_limpieza(db, habitacion_id: int):
    consulta = select(EventoHabitacion.creado_en).where(
        EventoHabitacion.habitacion_id == habitacion_id, EventoHabitacion.estado_nuevo == "En Limpieza"
    ).order_by(EventoHabitacion.id.desc())
    return rotacion.con_zona((await db.execute(consulta)).scalars().first())


def _adelantar_reloj(monkeypatch, desde, minutos: int) -> None:
    # Unos segundos más que los minutos enteros: así se ve que se cuentan minutos completos.
    monkeypatch.setattr(rotacion, "reloj", lambda: desde + timedelta(minutes=minutos, seconds=20))


async def _tarjeta(cliente, habitacion_id: int) -> dict:
    return next(h for h in (await cliente.get(GRILLA)).json() if h["id"] == habitacion_id)


@pytest.mark.parametrize(("minutos", "demora"), [(29, False), (30, False), (31, True)])
async def test_rf_12_la_marca_aparece_pasados_los_30_minutos(client, db, monkeypatch, minutos, demora):
    await _cobrar(client)
    _adelantar_reloj(monkeypatch, await _inicio_de_la_limpieza(db, 1), minutos)
    tarjeta = await _tarjeta(client, 1)
    assert tarjeta["estado"] == "En Limpieza"
    assert tarjeta["minutos_en_limpieza"] == minutos
    assert tarjeta["demora_limpieza"] is demora


async def test_recien_cobrada_lleva_cero_minutos_y_al_liberar_no_cuenta(client):
    await _cobrar(client)
    tarjeta = await _tarjeta(client, 1)
    assert tarjeta["minutos_en_limpieza"] == 0 and tarjeta["demora_limpieza"] is False
    await client.patch("/api/v1/habitaciones/1/liberar")
    liberada = await _tarjeta(client, 1)
    assert liberada["minutos_en_limpieza"] is None and liberada["en_limpieza_desde"] is None


async def test_cuenta_desde_el_ultimo_paso_a_limpieza(client, db, monkeypatch):
    await _cobrar(client)
    await client.patch("/api/v1/habitaciones/1/liberar")
    await _cobrar(client)
    segunda = await _inicio_de_la_limpieza(db, 1)
    _adelantar_reloj(monkeypatch, segunda, 5)
    tarjeta = await _tarjeta(client, 1)
    assert tarjeta["minutos_en_limpieza"] == 5 and tarjeta["demora_limpieza"] is False


async def test_otros_estados_y_limpiezas_sin_historial_no_se_marcan(client, db):
    await db.execute(update(Habitacion).where(Habitacion.id == 2).values(estado="En Limpieza"))
    await db.commit()
    grilla = {h["id"]: h for h in (await client.get(GRILLA)).json()}
    # La 2 está En Limpieza sin un paso registrado (datos anteriores a la migración 011): sin minutos ni marca.
    assert grilla[2]["minutos_en_limpieza"] is None and grilla[2]["demora_limpieza"] is False
    # La 1 está Libre y la 3 en Mantenimiento.
    assert all(grilla[i]["en_limpieza_desde"] is None and not grilla[i]["demora_limpieza"] for i in (1, 3))


async def test_el_umbral_es_configurable(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEMORA_LIMPIEZA_MIN", 10)
    await _cobrar(client)
    _adelantar_reloj(monkeypatch, await _inicio_de_la_limpieza(db, 1), 11)
    assert (await _tarjeta(client, 1))["demora_limpieza"] is True
