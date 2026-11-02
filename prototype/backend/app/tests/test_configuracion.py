"""RF-11 ampliado: panel de configuración de la gerencia (acta del 27/10/2026) y RN-DER-06.

Criterio de aceptación del catálogo v5: con rol Administrador, un turno finalizado con tarifa_base $8.000, un
consumo registrado y una guardia abierta con fondo de $25.000, los cambios de tarifa, precio y fondo rigen hacia
adelante; la habitación y el conserje dados de baja conservan su historial; un conserje recibe 403.
"""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.configuracion import ConfiguracionCaja
from app.models.consumo import Consumo
from app.models.guardia import Guardia
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.tests.conftest import abrir_guardia, nuevo_cliente

CONFIG = "/api/v1/configuracion"
OPERADORES = "/api/v1/operadores/"
ARQUEO = "/api/v1/guardias/actual/arqueo"
TARIFA_9000 = {"tarifa_base": 9000, "estadia_base_min": 120, "fraccion_min": 30, "tarifa_fraccion": 2500}


async def _cobrar(ac: AsyncClient, habitacion_id: int, monto: float) -> dict:
    turno = (await ac.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id})).json()
    resp = await ac.post(f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": [{"medio_pago": "EFECTIVO",
                                                                                  "monto": monto}]})
    assert resp.status_code == 200, resp.text
    await ac.patch(f"/api/v1/habitaciones/{habitacion_id}/liberar")
    return turno


# --- Criterio de aceptación de RF-11 ------------------------------------------------------------------------------


async def test_rf_11_la_tarifa_nueva_rige_para_los_turnos_nuevos(client: AsyncClient, cliente_como, db):
    finalizado = await _cobrar(client, 1, 8000)
    en_curso = (await client.post("/api/v1/turnos/", json={"habitacion_id": 2})).json()
    gerencia = await cliente_como("gerencia")

    resp = await gerencia.post(f"{CONFIG}/tarifas", json=TARIFA_9000)

    assert resp.status_code == 201, resp.text
    assert resp.json()["vigente"] is True and resp.json()["tarifa_base"] == 9000
    tarifas = (await gerencia.get(f"{CONFIG}/tarifas")).json()
    assert [t["vigente"] for t in tarifas] == [True, False]
    assert tarifas[1]["tarifa_base"] == 8000

    # El turno finalizado conserva $8.000 y sus importes; el que estaba en curso, su tarifa original.
    turno_viejo = await db.get(Turno, uuid.UUID(finalizado["id"]))
    assert turno_viejo.tarifa_base == Decimal("8000") and turno_viejo.total_general == Decimal("8000")
    assert (await db.get(Turno, uuid.UUID(en_curso["id"]))).tarifa_id == tarifas[1]["id"]

    nuevo = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1})).json()
    assert nuevo["tarifa_base"] == 9000


async def test_rf_11_el_turno_en_curso_se_liquida_con_su_tarifa(client: AsyncClient, cliente_como):
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1})).json()
    gerencia = await cliente_como("gerencia")
    await gerencia.post(f"{CONFIG}/tarifas", json={**TARIFA_9000, "tarifa_fraccion": 4000})

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["tarifa_base"] == 8000 and resumen["total_general"] == 8000


async def test_rf_11_el_precio_nuevo_no_cambia_los_consumos_registrados(client: AsyncClient, cliente_como, db):
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1})).json()
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    gerencia = await cliente_como("gerencia")

    resp = await gerencia.patch(f"{CONFIG}/articulos/1", json={"precio_unitario": 1000})

    assert resp.status_code == 200 and resp.json()["precio_unitario"] == 1000
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    precios = sorted(c.precio_unitario for c in (await db.execute(select(Consumo))).scalars().all())
    assert precios == [Decimal("800"), Decimal("1000")]


async def test_rf_11_el_fondo_nuevo_rige_desde_la_guardia_siguiente(cliente_como, db):
    db.add(ConfiguracionCaja(id=1, fondo_cambio=25000))
    await db.commit()
    conserje = await cliente_como("conserje1")
    abierta = await abrir_guardia(conserje)
    assert abierta["fondo_inicial"] == 25000
    gerencia = await cliente_como("gerencia")

    resp = await gerencia.patch(f"{CONFIG}/caja", json={"fondo_cambio": 30000})

    assert resp.status_code == 200 and resp.json()["fondo_cambio"] == 30000
    assert (await gerencia.get(f"{CONFIG}/caja")).json()["fondo_cambio"] == 30000
    arqueo = (await conserje.post(ARQUEO, json={"efectivo": 25000})).json()
    assert arqueo["sistema_efectivo"] == 25000 and arqueo["categoria"] == "Correcto"
    siguiente = await abrir_guardia(await cliente_como("conserje2"))
    assert siguiente["fondo_inicial"] == 30000


async def test_sin_la_fila_de_configuracion_el_fondo_no_se_cambia(cliente_como):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.get(f"{CONFIG}/caja")).json()["fondo_cambio"] == 0  # FONDO_INICIAL_CAJA de las pruebas
    assert (await gerencia.patch(f"{CONFIG}/caja", json={"fondo_cambio": 1})).status_code == 409


# --- Habitaciones -----------------------------------------------------------------------------------------------


async def test_rf_11_alta_y_baja_de_habitacion_conservan_el_historial(client: AsyncClient, cliente_como, db):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(f"{CONFIG}/habitaciones", json={"numero": 14})
    assert alta.status_code == 201 and alta.json()["activa"] is True
    nueva_id = alta.json()["id"]
    assert any(h["numero"] == 14 for h in (await client.get("/api/v1/habitaciones/")).json())

    await _cobrar(client, nueva_id, 8000)
    baja = await gerencia.patch(f"{CONFIG}/habitaciones/{nueva_id}", json={"activa": False})

    assert baja.status_code == 200 and baja.json()["activa"] is False
    assert all(h["numero"] != 14 for h in (await client.get("/api/v1/habitaciones/")).json())
    assert any(h["numero"] == 14 for h in (await gerencia.get(f"{CONFIG}/habitaciones")).json())
    historial = (await db.execute(select(Turno).where(Turno.habitacion_id == nueva_id))).scalars().all()
    assert len(historial) == 1 and historial[0].estado == "FINALIZADO"
    assert (await client.post("/api/v1/turnos/", json={"habitacion_id": nueva_id})).status_code == 409


async def test_habitacion_ocupada_no_se_da_de_baja_ni_cambia_de_numero(client: AsyncClient, cliente_como):
    await client.post("/api/v1/turnos/", json={"habitacion_id": 1})
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.patch(f"{CONFIG}/habitaciones/1", json={"activa": False})).status_code == 409
    assert (await gerencia.patch(f"{CONFIG}/habitaciones/1", json={"numero": 20})).status_code == 409


async def test_numero_de_habitacion_repetido_responde_409(cliente_como):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(f"{CONFIG}/habitaciones", json={"numero": 2})).status_code == 409
    assert (await gerencia.patch(f"{CONFIG}/habitaciones/1", json={"numero": 2})).status_code == 409
    cambio = await gerencia.patch(f"{CONFIG}/habitaciones/1", json={"numero": 21})
    assert cambio.status_code == 200 and cambio.json()["numero"] == 21
    assert (await gerencia.patch(f"{CONFIG}/habitaciones/999", json={"activa": False})).status_code == 404


# --- Artículos --------------------------------------------------------------------------------------------------


async def test_articulo_dado_de_baja_sale_de_la_ventanilla(client: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.patch(f"{CONFIG}/articulos/1", json={"activo": False, "descripcion": "Agua 500 ml"})

    assert resp.status_code == 200 and resp.json()["activo"] is False
    assert all(a["id"] != 1 for a in (await client.get("/api/v1/articulos/")).json())
    assert any(a["id"] == 1 for a in (await gerencia.get(f"{CONFIG}/articulos")).json())
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1})).json()
    consumo = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    assert consumo.status_code == 409


@pytest.mark.parametrize("cuerpo", [{"precio_unitario": -1}, {"stock_actual": -2}, {"descripcion": None}])
async def test_articulo_con_datos_invalidos_responde_422(cliente_como, cuerpo):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.patch(f"{CONFIG}/articulos/1", json=cuerpo)).status_code == 422


async def test_articulo_inexistente_responde_404(cliente_como):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.patch(f"{CONFIG}/articulos/999", json={"precio_unitario": 1})).status_code == 404


# --- Conserjes --------------------------------------------------------------------------------------------------


async def test_rf_11_alta_y_baja_de_conserje(cliente_como, db):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(OPERADORES, json={"usuario": "conserje3", "nombre_visible": "Conserje Tres",
                                                 "clave": "clave-prueba-conserje3"})
    assert alta.status_code == 201, alta.text
    assert alta.json()["rol"] == "OPERADOR" and alta.json()["activo"] is True
    async with nuevo_cliente() as nuevo:
        login = await nuevo.post("/api/v1/auth/login", json={"usuario": "conserje3", "clave": "clave-prueba-conserje3"})
        assert login.status_code == 200

    # conserje2 trabajó una guardia completa: su baja no toca esa historia.
    conserje2 = await cliente_como("conserje2")
    await abrir_guardia(conserje2)
    await _cobrar(conserje2, 1, 8000)
    await conserje2.post(ARQUEO, json={"efectivo": 8000})

    baja = await gerencia.patch(f"{OPERADORES}2", json={"activo": False})

    assert baja.status_code == 200 and baja.json()["activo"] is False
    assert (await conserje2.get("/api/v1/auth/sesion")).status_code == 401  # la sesión abierta deja de valer
    async with nuevo_cliente() as otro:
        login = await otro.post("/api/v1/auth/login", json={"usuario": "conserje2", "clave": "clave-prueba-conserje2"})
        assert login.status_code == 401
    guardia = (await db.execute(select(Guardia).where(Guardia.operador_id == 2))).scalar_one()
    assert guardia.estado == "Cerrada"
    assert len((await db.execute(select(Turno).where(Turno.operador_apertura_id == 2))).scalars().all()) == 1
    assert len((await gerencia.get("/api/v1/arqueos/", params={"operador_id": 2})).json()) == 1


async def test_no_se_da_de_baja_a_la_gerencia_ni_a_quien_tiene_la_guardia_abierta(client: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.patch(f"{OPERADORES}3", json={"activo": False})).status_code == 409
    assert (await gerencia.patch(f"{OPERADORES}1", json={"activo": False})).status_code == 409  # guardia abierta
    assert (await gerencia.patch(f"{OPERADORES}999", json={"activo": False})).status_code == 404
    reactivado = await gerencia.patch(f"{OPERADORES}4", json={"activo": True})
    assert reactivado.status_code == 200 and reactivado.json()["activo"] is True


@pytest.mark.parametrize(
    ("cuerpo", "codigo"),
    [
        ({"usuario": "conserje1", "nombre_visible": "Repetido", "clave": "clave-larga-1"}, 409),
        ({"usuario": "Con Espacios", "nombre_visible": "X", "clave": "clave-larga-1"}, 422),
        ({"usuario": "conserje9", "nombre_visible": "X", "clave": "corta"}, 422),
        ({"usuario": "conserje9", "nombre_visible": "", "clave": "clave-larga-1"}, 422),
    ],
)
async def test_alta_de_conserje_valida_los_datos(cliente_como, cuerpo, codigo):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(OPERADORES, json=cuerpo)).status_code == codigo


async def test_el_alta_no_permite_elegir_el_rol(cliente_como, db):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(OPERADORES, json={"usuario": "conserje4", "nombre_visible": "Cuatro",
                                                 "clave": "clave-prueba-4444", "rol": "ADMINISTRADOR"})
    assert alta.status_code == 201 and alta.json()["rol"] == "OPERADOR"


# --- Permisos y validaciones de la tarifa -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("get", f"{CONFIG}/tarifas", None),
        ("post", f"{CONFIG}/tarifas", TARIFA_9000),
        ("patch", f"{CONFIG}/caja", {"fondo_cambio": 1}),
        ("get", f"{CONFIG}/articulos", None),
        ("patch", f"{CONFIG}/articulos/1", {"precio_unitario": 1}),
        ("post", f"{CONFIG}/habitaciones", {"numero": 30}),
        ("patch", f"{CONFIG}/habitaciones/1", {"activa": False}),
        ("post", OPERADORES, {"usuario": "x.y.z", "nombre_visible": "X", "clave": "clave-larga-1"}),
        ("patch", f"{OPERADORES}2", {"activo": False}),
    ],
)
async def test_rf_11_un_conserje_recibe_403(client: AsyncClient, metodo, ruta, cuerpo):
    kwargs = {"json": cuerpo} if cuerpo is not None else {}
    assert (await getattr(client, metodo)(ruta, **kwargs)).status_code == 403


@pytest.mark.parametrize(
    "cambio",
    [{"tarifa_base": 0}, {"estadia_base_min": 0}, {"fraccion_min": 2000}, {"tarifa_fraccion": -1}],
)
async def test_tarifa_invalida_responde_422(cliente_como, cambio):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(f"{CONFIG}/tarifas", json={**TARIFA_9000, **cambio})).status_code == 422


async def test_queda_una_sola_tarifa_vigente(cliente_como, db):
    gerencia = await cliente_como("gerencia")
    for base in (9000, 9500, 10000):
        assert (await gerencia.post(f"{CONFIG}/tarifas", json={**TARIFA_9000, "tarifa_base": base})).status_code == 201
    vigentes = (await db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)))).scalars().all()
    assert len(vigentes) == 1 and vigentes[0].tarifa_base == Decimal("10000")
    assert vigentes[0].creada_por_id == 3
