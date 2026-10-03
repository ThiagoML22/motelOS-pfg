from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.articulo import Articulo
from app.models.habitacion import Habitacion
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno

EFECTIVO = "EFECTIVO"


def pagos(*items: tuple[str, float, str | None]) -> dict:
    return {
        "pagos": [
            {"medio_pago": medio, "monto": monto, "comprobante_referencia": comprobante}
            for medio, monto, comprobante in items
        ]
    }


async def _abrir_turno(client: AsyncClient, habitacion_id: int = 1, **extra) -> dict:
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _estado(db, habitacion_id: int) -> str:
    db.expire_all()
    return (await db.execute(select(Habitacion.estado).where(Habitacion.id == habitacion_id))).scalar_one()


async def _envejecer(db, minutos: int) -> None:
    fila = (await db.execute(select(Turno))).scalars().first()
    fila.hora_inicio = datetime.now(UTC) - timedelta(minutes=minutos, seconds=2)
    await db.commit()


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- RF-02 / RN-EXI-01 -------------------------------------------------------------------------


async def test_crear_turno_habitacion_libre(client: AsyncClient, db):
    turno = await _abrir_turno(client, identificador_vehicular="TEST123", tipo_cliente="Moto")

    assert turno["estado"] == "En Curso"
    assert turno["tipo_cliente"] == "Moto"
    assert turno["tarifa_base"] == 8000
    assert turno["total_general"] == 8000
    assert await _estado(db, 1) == "Ocupada"


async def test_el_turno_registra_la_tarifa_vigente(client: AsyncClient, db):
    await _abrir_turno(client)

    fila = (await db.execute(select(Turno))).scalars().first()
    tarifa = (await db.execute(select(Tarifa))).scalars().first()
    assert fila.tarifa_id == tarifa.id


async def test_sin_tarifa_vigente_no_se_abre_turno(client: AsyncClient, db):
    tarifa = (await db.execute(select(Tarifa))).scalars().first()
    tarifa.vigente = False
    await db.commit()

    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": 1})

    assert resp.status_code == 409


async def test_crear_turno_sin_patente_rnf_03(client: AsyncClient):
    turno = await _abrir_turno(client, tipo_cliente="Peaton")
    assert turno["identificador_vehicular"] is None


async def test_crear_turno_habitacion_ocupada_devuelve_409(client: AsyncClient):
    await _abrir_turno(client, habitacion_id=1)

    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": 1})

    assert resp.status_code == 409
    assert "RN-EXI-01" in resp.json()["detail"]


async def test_crear_turno_habitacion_en_mantenimiento_devuelve_409(client: AsyncClient):
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": 3})
    assert resp.status_code == 409


async def test_crear_turno_habitacion_inexistente_devuelve_404(client: AsyncClient):
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": 999})
    assert resp.status_code == 404


async def test_crear_turno_tipo_cliente_invalido_devuelve_422(client: AsyncClient):
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Camion"})
    assert resp.status_code == 422


async def test_turno_no_persiste_datos_personales_rnf_03(client: AsyncClient):
    resp = await client.post(
        "/api/v1/turnos/", json={"habitacion_id": 1, "nombre": "Juan", "dni": "123", "telefono": "555"}
    )
    assert resp.status_code == 201
    campos = set(resp.json())
    assert not campos & {"nombre", "apellido", "dni", "telefono", "email"}


# --- RF-04 / RF-05 / RN-EXI-02 -------------------------------------------------------------------


async def test_consumo_descuenta_stock_y_acumula_totales(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 2})

    assert resp.status_code == 201
    assert resp.json()["subtotal"] == 1600
    db.expire_all()
    assert (await db.get(Articulo, 1)).stock_actual == 3

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["total_consumos"] == 1600
    assert resumen["total_general"] == 9600
    assert len(resumen["consumos"]) == 1


async def test_consumo_con_stock_insuficiente_no_modifica_nada(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 6})

    assert resp.status_code == 400
    assert "RN-EXI-02" in resp.json()["detail"]
    db.expire_all()
    assert (await db.get(Articulo, 1)).stock_actual == 5


async def test_articulo_sin_stock_se_rechaza_y_no_genera_registros_rf_05(client: AsyncClient):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 2, "cantidad": 1})

    assert resp.status_code == 400
    assert "Stock insuficiente" in resp.json()["detail"]
    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["consumos"] == []
    assert resumen["total_consumos"] == 0


async def test_consumo_cantidad_no_positiva_devuelve_422(client: AsyncClient):
    turno = await _abrir_turno(client)
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 0})
    assert resp.status_code == 422


async def test_consumo_articulo_inexistente_devuelve_404(client: AsyncClient):
    turno = await _abrir_turno(client)
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 999, "cantidad": 1})
    assert resp.status_code == 404


async def test_consumo_en_turno_inexistente_devuelve_400(client: AsyncClient):
    resp = await client.post(
        "/api/v1/turnos/00000000-0000-4000-8000-000000000000/consumos", json={"articulo_id": 1, "cantidad": 1}
    )
    assert resp.status_code == 400


# --- RF-03 / RN-DER-01 / RN-DER-02 ----------------------------------------------------------------


async def test_resumen_dentro_de_estadia_base_no_cobra_sobreturno(client: AsyncClient):
    turno = await _abrir_turno(client)

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    assert resumen["total_sobreturno"] == 0
    assert resumen["total_general"] == 8000
    assert resumen["minutos_transcurridos"] == 0
    assert resumen["total_pagado"] == 0
    assert resumen["saldo_pendiente"] == 8000


async def test_resumen_al_exceder_la_base_suma_fracciones_de_30_min(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await _envejecer(db, 170)

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    # 50 min de excedente -> 2 fracciones de 30 min a $2.500
    assert resumen["total_sobreturno"] == 5000
    assert resumen["total_general"] == 13000


async def test_resumen_a_los_121_minutos_cobra_una_fraccion(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await _envejecer(db, 121)

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    assert resumen["total_sobreturno"] == 2500
    assert resumen["total_general"] == 10500


async def test_total_incluye_estadia_sobreturno_y_consumos_rn_der_02(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    await _envejecer(db, 149)  # 29 min de excedente: una fracción

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    assert resumen["total_general"] == 8000 + 2500 + 800


# --- RF-06 / RF-07 / RN-EXI-03: cobro con desglose y saldo exacto -----------------------------------


async def test_cobro_solo_efectivo_cierra_el_turno_y_emite_constancia(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 8000, None)))

    assert resp.status_code == 200
    constancia = resp.json()
    assert constancia["total_general"] == 8000
    assert constancia["total_pagado"] == 8000
    assert constancia["saldo_pendiente"] == 0
    assert constancia["habitacion_numero"] == 1
    assert constancia["pagos"] == [{"medio_pago": EFECTIVO, "monto": 8000, "comprobante_referencia": None}]
    assert await _estado(db, 1) == "En Limpieza"
    db.expire_all()
    assert (await db.execute(select(Turno.estado))).scalar_one() == "FINALIZADO"


async def test_cobro_mixto_registra_un_pago_por_medio_rf_06(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})

    resp = await client.post(
        f"/api/v1/turnos/{turno['id']}/cerrar",
        json=pagos((EFECTIVO, 5000, None), ("POSNET", 3800, "CUPON-0001")),
    )

    assert resp.status_code == 200
    constancia = resp.json()
    assert constancia["total_general"] == 8800
    assert [p["medio_pago"] for p in constancia["pagos"]] == [EFECTIVO, "POSNET"]
    assert constancia["pagos"][1]["comprobante_referencia"] == "CUPON-0001"
    db.expire_all()
    filas = (await db.execute(select(Pago))).scalars().all()
    assert len(filas) == 2
    assert sum(float(p.monto) for p in filas) == 8800


async def test_cobro_con_importe_insuficiente_devuelve_400(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 5000, None)))

    assert resp.status_code == 400
    assert "RN-EXI-03" in resp.json()["detail"]
    assert await _estado(db, 1) == "Ocupada"
    db.expire_all()
    assert (await db.execute(select(Pago))).scalars().all() == []


async def test_cobro_con_importe_excedido_devuelve_400(client: AsyncClient):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 9000, None)))

    assert resp.status_code == 400
    assert "RN-EXI-03" in resp.json()["detail"]


async def test_cobro_electronico_sin_comprobante_devuelve_422(client: AsyncClient):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos(("POSNET", 8000, None)))

    assert resp.status_code == 422


async def test_cobro_sin_pagos_devuelve_422(client: AsyncClient):
    turno = await _abrir_turno(client)
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": []})
    assert resp.status_code == 422


async def test_cobro_liquida_el_sobreturno_vigente(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await _envejecer(db, 149)  # 29 min de excedente: una fracción

    insuficiente = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 8000, None)))
    exacto = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 10500, None)))

    assert insuficiente.status_code == 400
    assert exacto.status_code == 200


async def test_cobro_y_luego_liberar_la_habitacion(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 8000, None)))

    assert (await client.patch("/api/v1/habitaciones/1/liberar")).status_code == 200
    assert await _estado(db, 1) == "Libre"


async def test_cerrar_turno_dos_veces_devuelve_400(client: AsyncClient):
    turno = await _abrir_turno(client)
    payload = pagos((EFECTIVO, 8000, None))
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=payload)).status_code == 200
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=payload)).status_code == 400


async def test_resumen_de_un_turno_finalizado_conserva_sus_importes(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=pagos((EFECTIVO, 8000, None)))

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    assert resumen["estado"] == "FINALIZADO"
    assert resumen["total_general"] == 8000
    assert resumen["total_pagado"] == 8000
    assert resumen["saldo_pendiente"] == 0
