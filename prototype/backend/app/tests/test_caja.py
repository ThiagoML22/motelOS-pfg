"""Guardias y cierre de caja ciego: pruebas de aceptación de RF-08 y RF-09 y de sus reglas.

RF-08: «antes de confirmar el recuento ninguna respuesta de la API incluye el total del sistema; al
confirmar se guarda el arqueo con total declarado, total del sistema y diferencia». El bloqueo del
arqueo contra UPDATE y DELETE (RN-RES-02) lo verifica db/verify_caja.sql sobre PostgreSQL.
RF-09: «con D = $50.000 y S = $52.500 el resultado es Faltante de $2.500».
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import Settings, settings
from app.main import app
from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.pago import Pago
from app.services.caja import clasificar_diferencia, franja_para
from app.tests.conftest import abrir_guardia

ARQUEO = "/api/v1/guardias/actual/arqueo"


async def _cobrar_turno(ac: AsyncClient, habitacion_id: int, medio: str = "EFECTIVO", consumos: int = 0) -> float:
    """Abre un turno, agrega aguas ($800 c/u) y lo cobra con un solo medio. Devuelve lo cobrado."""
    turno = (await ac.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id})).json()
    for _ in range(consumos):
        await ac.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    total = 8000 + 800 * consumos
    pago = {"medio_pago": medio, "monto": total, "comprobante_referencia": None if medio == "EFECTIVO" else "C-1"}
    resp = await ac.post(f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": [pago]})
    assert resp.status_code == 200, resp.text
    await ac.patch(f"/api/v1/habitaciones/{habitacion_id}/liberar")
    return total


# --- Reglas puras ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declarado", "sistema", "diferencia", "categoria"),
    [
        ("50000", "52500", "-2500", "Faltante"),  # valores del criterio de aceptación de RF-09
        ("52500", "52500", "0", "Correcto"),
        ("53000", "52500", "500", "Sobrante"),
        ("0.01", "0", "0.01", "Sobrante"),
        ("0", "0.01", "-0.01", "Faltante"),
    ],
)
def test_rn_der_03_diferencia_y_categoria(declarado, sistema, diferencia, categoria):
    assert clasificar_diferencia(Decimal(declarado), Decimal(sistema)) == (Decimal(diferencia), categoria)


@pytest.mark.parametrize(
    ("hora_local", "franja"),
    [
        ("05:50", "06:00"),
        ("06:10", "06:00"),
        ("13:45", "14:00"),
        ("18:00", "14:00"),
        ("21:30", "22:00"),  # se abre antes del recambio de las 22:00
        ("23:59", "22:00"),
        ("02:00", "22:00"),
        ("10:00", "06:00"),
    ],
)
def test_franja_de_la_guardia_segun_la_hora_de_apertura(hora_local, franja):
    # Posadas está en UTC-3 todo el año: la hora local + 3 h es la hora UTC.
    horas, minutos = (int(x) for x in hora_local.split(":"))
    momento = datetime(2026, 10, 20, (horas + 3) % 24, minutos, tzinfo=UTC)
    assert franja_para(momento) == franja


# --- Guardias --------------------------------------------------------------------------------------


async def test_sin_guardia_abierta_no_se_opera_la_ventanilla(cliente_como):
    conserje = await cliente_como("conserje2")
    resp = await conserje.post("/api/v1/turnos/", json={"habitacion_id": 1})
    assert resp.status_code == 409
    assert "Abra su guardia" in resp.json()["detail"]


async def test_una_sola_guardia_abierta_y_otro_operador_no_opera_en_ella(client: AsyncClient, cliente_como):
    otro = await cliente_como("conserje2")

    resp = await otro.post("/api/v1/guardias/")
    assert resp.status_code == 409
    assert "Conserje Uno" in resp.json()["detail"]

    resp = await otro.post("/api/v1/turnos/", json={"habitacion_id": 1})
    assert resp.status_code == 409
    assert "La guardia abierta es de Conserje Uno" in resp.json()["detail"]


async def test_la_sesion_informa_la_guardia_abierta_sin_importes(client: AsyncClient, cliente_como):
    propia = (await client.get("/api/v1/auth/sesion")).json()["guardia"]
    assert propia["es_propia"] is True
    assert propia["operador_nombre"] == "Conserje Uno"

    otro = await cliente_como("conserje2")
    ajena = (await otro.get("/api/v1/auth/sesion")).json()["guardia"]
    assert ajena["es_propia"] is False
    assert set(ajena) == {"id", "franja", "estado", "abierta_en", "cerrada_en", "operador_id", "operador_nombre",
                          "fondo_inicial", "es_propia"}


# --- RF-08 y RN-RES-03 -----------------------------------------------------------------------------


def _rutas_get_sin_parametros() -> list[str]:
    rutas = [
        camino for camino, operaciones in app.openapi()["paths"].items()
        if camino.startswith("/api/") and "get" in operaciones and "{" not in camino
    ]
    assert len(rutas) >= 4, "No se encontraron las rutas de consulta de la API"
    return rutas


async def test_rf_08_ninguna_respuesta_muestra_el_total_antes_del_recuento(client: AsyncClient, cliente_como):
    cobrado = await _cobrar_turno(client, 1, "EFECTIVO", consumos=1)  # 8.800
    cobrado += await _cobrar_turno(client, 2, "POSNET")  # 8.000
    total_sistema = cobrado  # 16.800, distinto de cualquier turno individual
    assert total_sistema == 16800

    gerencia = await cliente_como("gerencia")
    for ac in (client, gerencia):
        for camino in _rutas_get_sin_parametros():
            resp = await ac.get(camino)
            texto = resp.text
            assert "total_sistema" not in texto and "sistema_" not in texto, camino
            assert "16800" not in texto, f"{camino} expone el total de la guardia abierta"



async def test_rf_08_al_confirmar_se_guarda_el_arqueo_y_se_cierra_la_guardia(client: AsyncClient, db):
    await _cobrar_turno(client, 1, "EFECTIVO", consumos=1)  # 8.800 en efectivo
    await _cobrar_turno(client, 2, "POSNET")  # 8.000 en POSNET

    resp = await client.post(ARQUEO, json={"efectivo": 8800, "posnet": 8000, "mercado_pago": 0})

    assert resp.status_code == 201, resp.text
    arqueo = resp.json()
    assert arqueo["total_declarado"] == 16800
    assert arqueo["total_sistema"] == 16800
    assert arqueo["sistema_efectivo"] == 8800 and arqueo["sistema_posnet"] == 8000
    assert arqueo["diferencia"] == 0 and arqueo["categoria"] == "Correcto"
    assert arqueo["operador_nombre"] == "Conserje Uno"

    guardia = (await db.execute(select(Guardia))).scalar_one()
    assert guardia.estado == "Cerrada" and guardia.cerrada_en is not None
    assert (await db.execute(select(ArqueoCaja))).scalar_one().guardia_id == guardia.id

    # Cerrada la guardia no hay otro arqueo ni más operaciones hasta abrir una nueva.
    assert (await client.post(ARQUEO, json={"efectivo": 0})).status_code == 409
    assert (await client.post("/api/v1/turnos/", json={"habitacion_id": 1})).status_code == 409


async def test_rf_09_faltante_sobrante_y_correcto(client: AsyncClient):
    await _cobrar_turno(client, 1)  # 8.000 en efectivo
    resp = await client.post(ARQUEO, json={"efectivo": 5500})
    assert resp.json()["diferencia"] == -2500
    assert resp.json()["categoria"] == "Faltante"

    await abrir_guardia(client)
    await _cobrar_turno(client, 1)
    resp = await client.post(ARQUEO, json={"efectivo": 8500})
    assert (resp.json()["diferencia"], resp.json()["categoria"]) == (500, "Sobrante")

    await abrir_guardia(client)
    resp = await client.post(ARQUEO, json={"efectivo": 0})  # guardia sin cobros
    assert (resp.json()["total_sistema"], resp.json()["categoria"]) == (0, "Correcto")


def test_el_fondo_de_cambio_aprobado_es_de_25000():
    # Acta de validación del 19/10/2026, punto 5: $25.000 por caja.
    assert Settings.model_fields["FONDO_INICIAL_CAJA"].default == Decimal("25000")


async def test_el_fondo_de_cambio_integra_el_efectivo_del_sistema(cliente_como, monkeypatch):
    monkeypatch.setattr(settings, "FONDO_INICIAL_CAJA", Decimal("25000"))
    conserje = await cliente_como("conserje2")
    guardia = await abrir_guardia(conserje)
    assert guardia["fondo_inicial"] == 25000

    await _cobrar_turno(conserje, 1)  # $8.000 en efectivo
    resp = await conserje.post(ARQUEO, json={"efectivo": 33000})
    assert resp.json()["sistema_efectivo"] == 33000
    assert resp.json()["categoria"] == "Correcto"


@pytest.mark.parametrize(
    "cuerpo",
    [{"efectivo": -1}, {"efectivo": 10, "posnet": -5}, {"efectivo": 1.234}, {"efectivo": 1e12}, {}],
)
async def test_declaracion_invalida_responde_422(client: AsyncClient, cuerpo):
    assert (await client.post(ARQUEO, json=cuerpo)).status_code == 422


async def test_solo_el_operador_de_la_guardia_la_arquea(client: AsyncClient, cliente_como):
    otro = await cliente_como("conserje2")
    assert (await otro.post(ARQUEO, json={"efectivo": 0})).status_code == 409
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(ARQUEO, json={"efectivo": 0})).status_code == 409


# --- RN-DER-04: el turno que cruza el recambio -----------------------------------------------------


async def test_rn_der_04_el_cobro_va_a_la_guardia_que_atiende(client: AsyncClient, cliente_como, db):
    # 21:30: Conserje Uno (guardia de las 14:00) abre un turno en la habitación 1.
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1})).json()
    assert turno["abierto_por"] == "Conserje Uno"

    # 22:00: Conserje Uno cierra su guardia sin cobros; el turno sigue en curso.
    arqueo_14 = (await client.post(ARQUEO, json={"efectivo": 0})).json()
    assert arqueo_14["total_sistema"] == 0

    # 23:30: Conserje Dos abre la guardia de las 22:00 y cobra el turno.
    conserje2 = await cliente_como("conserje2")
    guardia_22 = await abrir_guardia(conserje2)
    habitaciones = (await conserje2.get("/api/v1/habitaciones/")).json()
    assert habitaciones[0]["turno_activo"]["abierto_por"] == "Conserje Uno"
    resp = await conserje2.post(
        f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": [{"medio_pago": "EFECTIVO", "monto": 8000}]}
    )
    assert resp.status_code == 200, resp.text

    pago = (await db.execute(select(Pago))).scalar_one()
    assert pago.guardia_id == guardia_22["id"]
    arqueo_22 = (await conserje2.post(ARQUEO, json={"efectivo": 8000})).json()
    assert (arqueo_22["total_sistema"], arqueo_22["categoria"]) == (8000, "Correcto")
