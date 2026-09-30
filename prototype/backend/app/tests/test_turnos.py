from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.models.articulo import Articulo
from app.models.habitacion import Habitacion
from app.models.turno import Turno


async def _abrir_turno(client: AsyncClient, habitacion_id: int = 1, **extra) -> dict:
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _estado(db, habitacion_id: int) -> str:
    db.expire_all()
    return (await db.execute(select(Habitacion.estado).where(Habitacion.id == habitacion_id))).scalar_one()


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --- RN-EXI-01 -------------------------------------------------------------------------------


async def test_crear_turno_habitacion_libre(client: AsyncClient, db):
    turno = await _abrir_turno(client, identificador_vehicular="TEST123", tipo_cliente="Moto")

    assert turno["estado"] == "En Curso"
    assert turno["tipo_cliente"] == "Moto"
    assert turno["total_general"] == 12000
    assert await _estado(db, 1) == "Ocupada"


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


# --- RN-EXI-02 -------------------------------------------------------------------------------


async def test_consumo_descuenta_stock_y_acumula_totales(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 2})

    assert resp.status_code == 201
    assert resp.json()["subtotal"] == 1600
    db.expire_all()
    assert (await db.get(Articulo, 1)).stock_actual == 3

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["total_consumos"] == 1600
    assert resumen["total_general"] == 13600
    assert len(resumen["consumos"]) == 1


async def test_consumo_con_stock_insuficiente_no_modifica_nada(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 6})

    assert resp.status_code == 400
    assert "RN-EXI-02" in resp.json()["detail"]
    db.expire_all()
    assert (await db.get(Articulo, 1)).stock_actual == 5


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


# --- RN-DER-01 (comportamiento actual del resumen) ----------------------------------------------


async def test_resumen_dentro_de_estadia_base_no_cobra_sobreturno(client: AsyncClient):
    turno = await _abrir_turno(client)

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    assert resumen["total_sobreturno"] == 0
    assert resumen["total_general"] == 12000
    assert resumen["minutos_transcurridos"] == 0


async def test_resumen_con_excedente_suma_fracciones_de_30_min(client: AsyncClient, db):
    turno = await _abrir_turno(client)
    fila = (await db.execute(select(Turno))).scalars().first()
    fila.hora_inicio = datetime.now(UTC) - timedelta(minutes=170)
    await db.commit()

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()

    # 50 min de excedente -> 2 fracciones de 30 min
    assert resumen["total_sobreturno"] == 7000
    assert resumen["total_general"] == 19000


# --- RN-EXI-03 y cierre ------------------------------------------------------------------------


async def test_cerrar_turno_con_pago_insuficiente_devuelve_400(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json={"monto": 5000, "medio_pago": "EFECTIVO"})

    assert resp.status_code == 400
    assert "RN-EXI-03" in resp.json()["detail"]
    assert await _estado(db, 1) == "Ocupada"


async def test_cerrar_turno_con_pago_completo_pasa_a_limpieza_y_luego_libre(client: AsyncClient, db):
    turno = await _abrir_turno(client)

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json={"monto": 12000, "medio_pago": "POSNET"})

    assert resp.status_code == 200
    assert await _estado(db, 1) == "En Limpieza"
    db.expire_all()
    assert (await db.execute(select(Turno.estado))).scalar_one() == "FINALIZADO"

    assert (await client.patch("/api/v1/habitaciones/1/liberar")).status_code == 200
    assert await _estado(db, 1) == "Libre"


async def test_cerrar_turno_dos_veces_devuelve_400(client: AsyncClient):
    turno = await _abrir_turno(client)
    payload = {"monto": 12000, "medio_pago": "EFECTIVO"}
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=payload)).status_code == 200
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=payload)).status_code == 400


async def test_cerrar_turno_medio_de_pago_invalido_devuelve_422(client: AsyncClient):
    turno = await _abrir_turno(client)
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json={"monto": 12000, "medio_pago": "TRUEQUE"})
    assert resp.status_code == 422
