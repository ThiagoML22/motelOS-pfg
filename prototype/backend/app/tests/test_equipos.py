"""Equipos autorizados (migración 019): el conserje entra solo desde los equipos que autorizó la gerencia."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.main import app
from app.models.equipo import IntentoAcceso
from app.services import equipos
from app.tests.conftest import (
    CLAVE_OTRO_MOTEL,
    ENCABEZADOS_APP,
    ESTABLECIMIENTO_OTRO,
    OPERADORES,
    iniciar_sesion,
    nuevo_cliente,
)

LOGIN = "/api/v1/auth/login"
EQUIPOS = "/api/v1/equipos"
CELULAR = "Mozilla/5.0 (Linux; Android 14; SM-A546E) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari"


def _datos(usuario: str, clave: str | None = None) -> dict:
    return {"usuario": usuario, "clave": clave or OPERADORES[usuario][2]}


def _equipo_de(ac: AsyncClient) -> str:
    return ac.cookies.get(settings.COOKIE_EQUIPO)


async def _panel(gerencia: AsyncClient) -> dict:
    resp = await gerencia.get(f"{EQUIPOS}/")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _activar(gerencia: AsyncClient, **ajustes) -> None:
    resp = await gerencia.patch(f"{EQUIPOS}/ajustes", json={"control": True, **ajustes})
    assert resp.status_code == 200, resp.text


async def _autorizar_el_de(client: AsyncClient, gerencia: AsyncClient, nombre: str = "PC Ventanilla") -> int:
    """Autoriza el equipo con el que entró `client` (el único pendiente de ese conserje)."""
    panel = await _panel(gerencia)
    equipo = next(e for e in panel["equipos"] if e["estado"] == "PENDIENTE")
    resp = await gerencia.post(f"{EQUIPOS}/{equipo['id']}/autorizar", json={"nombre": nombre})
    assert resp.status_code == 200, resp.text
    return equipo["id"]


# --- Sin el control activo ----------------------------------------------------------------------------------------


async def test_sin_control_el_conserje_entra_y_su_equipo_queda_para_revisar(client, cliente_como, db):
    gerencia = await cliente_como("gerencia")
    panel = await _panel(gerencia)
    assert panel["control"] is False and panel["redes"] is None
    [equipo] = panel["equipos"]
    assert equipo["estado"] == "PENDIENTE" and equipo["ultimo_operador"] == "Conserje Uno"
    # La base guarda el resumen de la marca, nunca la marca.
    marca = _equipo_de(client)
    assert marca and marca not in str(panel)
    guardada = (await db.execute(select(equipos.Equipo.huella))).scalars().all()
    assert guardada == [equipos.huella_de(marca)]


async def test_no_se_activa_sin_un_equipo_autorizado(cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.patch(f"{EQUIPOS}/ajustes", json={"control": True})
    assert resp.status_code == 409 and "Autorizá al menos un equipo" in resp.json()["detail"]


async def test_el_conserje_no_ve_el_panel(client):
    assert (await client.get(f"{EQUIPOS}/")).status_code == 403
    assert (await client.patch(f"{EQUIPOS}/ajustes", json={"control": False})).status_code == 403


# --- Con el control activo ----------------------------------------------------------------------------------------


async def test_desde_un_equipo_desconocido_el_conserje_no_entra_y_la_gerencia_se_entera(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("192.168.0.77", 5000)),
        base_url="http://test",
        headers={**ENCABEZADOS_APP, "User-Agent": CELULAR},
    ) as celular:
        resp = await celular.post(LOGIN, json=_datos("conserje2"))
        assert resp.status_code == 403 and resp.json()["detail"] == equipos.NO_AUTORIZADO
        # Con la clave equivocada responde lo mismo: desde acá no se pueden probar claves.
        otra = await celular.post(LOGIN, json=_datos("conserje1", "no-es-la-clave"))
        assert otra.status_code == 403 and otra.json()["detail"] == equipos.NO_AUTORIZADO
        inexistente = await celular.post(LOGIN, json=_datos("conserje2") | {"usuario": "nadie"})
        assert inexistente.status_code == 403
        assert _equipo_de(celular), "el equipo recibe su marca para que la gerencia pueda autorizarlo"
    panel = await _panel(gerencia)
    intentos = {(i["usuario"], i["clave_correcta"]) for i in panel["intentos"]}
    assert intentos == {("conserje2", True), ("conserje1", False), (None, False)}
    nuevo = next(i for i in panel["intentos"] if i["usuario"] == "conserje2")
    assert nuevo["ip"] == "192.168.0.77" and nuevo["descripcion"] == "Chrome en Android (celular)"
    assert nuevo["operador"] == "Conserje Dos" and nuevo["equipo_estado"] == "PENDIENTE"
    # El usuario inexistente no deja un equipo nuevo: un texto cualquiera no llena la tabla.
    assert sum(e["estado"] == "PENDIENTE" for e in panel["equipos"]) == 1
    # La campanita.
    recientes = (await gerencia.get(f"{EQUIPOS}/intentos")).json()
    assert len(recientes) == 3 and recientes[0]["creado_en"] >= recientes[-1]["creado_en"]


async def test_un_intento_repetido_enseguida_cuenta_una_vez(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    async with nuevo_cliente() as otro:
        for _ in range(3):
            assert (await otro.post(LOGIN, json=_datos("conserje2"))).status_code == 403
    assert len((await _panel(gerencia))["intentos"]) == 1


async def test_desde_el_equipo_autorizado_entra_cualquier_conserje(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    equipo_id = await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    await client.post("/api/v1/auth/logout")
    assert (await client.post(LOGIN, json=_datos("conserje2"))).status_code == 200
    assert (await client.get("/api/v1/habitaciones/")).status_code == 200
    equipo = next(e for e in (await _panel(gerencia))["equipos"] if e["id"] == equipo_id)
    assert equipo["nombre"] == "PC Ventanilla" and equipo["en_uso"] is True and equipo["decidido_por"] == "Gerencia"


async def test_la_gerencia_autoriza_el_equipo_y_entonces_entra(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    async with nuevo_cliente() as nueva_pc:
        assert (await nueva_pc.post(LOGIN, json=_datos("conserje2"))).status_code == 403
        await _autorizar_el_de(nueva_pc, gerencia, "PC del fondo")
        assert (await nueva_pc.post(LOGIN, json=_datos("conserje2"))).status_code == 200


async def test_quitar_la_autorizacion_corta_la_sesion_abierta(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    equipo_id = await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    assert (await client.get("/api/v1/habitaciones/")).status_code == 200
    assert (await gerencia.post(f"{EQUIPOS}/{equipo_id}/bloquear")).status_code == 200
    resp = await client.get("/api/v1/habitaciones/")
    assert resp.status_code == 401 and resp.json()["detail"] == equipos.SESION_CORTADA
    assert (await client.post(LOGIN, json=_datos("conserje1"))).status_code == 403
    # Lo que hizo la gerencia queda en la actividad.
    acciones = [a["accion"] for a in (await gerencia.get("/api/v1/configuracion/actividad")).json()]
    assert {"EQUIPO_AUTORIZADO", "EQUIPO_BLOQUEADO", "EQUIPOS_CONTROL"} <= set(acciones)


async def test_la_gerencia_entra_desde_cualquier_equipo(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    async with nuevo_cliente() as celular:
        assert (await celular.post(LOGIN, json=_datos("gerencia"))).status_code == 200
        # Y no deja un equipo pendiente ni un intento.
    panel = await _panel(gerencia)
    assert panel["intentos"] == [] and len(panel["equipos"]) == 1


async def test_autorizar_este_equipo_desde_la_sesion_de_la_gerencia(cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.post(f"{EQUIPOS}/este-equipo", json={"nombre": "  PC   Ventanilla "})
    assert resp.status_code == 200, resp.text
    panel = await _panel(gerencia)
    [equipo] = panel["equipos"]
    assert panel["este_equipo_id"] == equipo["id"] and equipo["nombre"] == "PC Ventanilla"
    await _activar(gerencia)
    # El conserje entra desde esa misma PC.
    await gerencia.post("/api/v1/auth/logout")
    assert (await gerencia.post(LOGIN, json=_datos("conserje1"))).status_code == 200


async def test_autorizar_pide_un_nombre(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    equipo = (await _panel(gerencia))["equipos"][0]
    resp = await gerencia.post(f"{EQUIPOS}/{equipo['id']}/autorizar", json={"nombre": "   "})
    assert resp.status_code == 422


# --- Redes --------------------------------------------------------------------------------------------------------


async def test_con_redes_cargadas_el_conserje_tiene_que_estar_en_una(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _autorizar_el_de(client, gerencia)
    await _activar(gerencia, redes="10.0.0.0/8, 192.168.1.20")
    assert (await _panel(gerencia))["redes"] == "10.0.0.0/8, 192.168.1.20/32"
    # El equipo autorizado, desde fuera de la red (127.0.0.1): no entra.
    resp = await client.post(LOGIN, json=_datos("conserje1"))
    assert resp.status_code == 403 and resp.json()["detail"] == equipos.FUERA_DE_LA_RED
    # El mismo equipo dentro de la red: entra.
    marca = {"Cookie": f"{settings.COOKIE_EQUIPO}={_equipo_de(client)}"}
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("10.1.2.3", 5000)),
        base_url="http://test",
        headers={**ENCABEZADOS_APP, **marca},
    ) as en_la_red:
        assert (await en_la_red.post(LOGIN, json=_datos("conserje1"))).status_code == 200
    assert [i["motivo"] for i in (await _panel(gerencia))["intentos"]] == ["RED"]


async def test_una_red_mal_escrita_se_rechaza(cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.patch(f"{EQUIPOS}/ajustes", json={"redes": "192.168.0.0/24, la del motel"})
    assert resp.status_code == 422 and "«la» no es una red válida" in resp.json()["detail"]
    resp = await gerencia.patch(f"{EQUIPOS}/ajustes", json={"redes": ""})
    assert resp.status_code == 200 and resp.json()["redes"] is None


@pytest.mark.parametrize(
    ("ip", "redes", "entra"),
    [
        ("192.168.0.15", "192.168.0.0/24", True),
        ("192.168.1.15", "192.168.0.0/24", False),
        ("::ffff:192.168.0.15", "192.168.0.0/24", True),
        ("192.168.1.15", None, True),
        (None, "192.168.0.0/24", False),
    ],
)
def test_en_las_redes(ip, redes, entra):
    assert equipos.en_las_redes(ip, redes) is entra


# --- Otros --------------------------------------------------------------------------------------------------------


async def test_otro_motel_no_ve_los_equipos(client):
    async with nuevo_cliente() as otro:
        datos = {"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL}
        assert (await otro.post(LOGIN, json=datos)).status_code == 200
        panel = await _panel(otro)
    assert panel["equipos"] == [] and panel["intentos"] == []


@pytest.mark.parametrize(
    ("agente", "descripcion"),
    [
        (CELULAR, "Chrome en Android (celular)"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36 Edg/124.0",
         "Edge en Windows"),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 Version/17.4 Mobile Safari",
         "Safari en iPhone (celular)"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0", "Firefox en Linux"),
        (None, "Navegador en equipo desconocido"),
    ],
)
def test_describir_el_equipo(agente, descripcion):
    assert equipos.describir(agente) == descripcion


async def test_los_intentos_se_borran_a_los_90_dias(db):
    viejo = datetime.now(UTC) - timedelta(days=91)
    db.add(IntentoAcceso(clave_correcta=False, motivo="EQUIPO", descripcion="x", creado_en=viejo))
    db.add(IntentoAcceso(clave_correcta=False, motivo="EQUIPO", descripcion="y"))
    await db.commit()
    assert await equipos.depurar_intentos(db) == 1
    assert (await db.execute(select(IntentoAcceso.descripcion))).scalars().all() == ["y"]


PREGUNTA = "/api/v1/asistente/pregunta"


async def test_mot_le_cuenta_a_la_gerencia_quien_intento_entrar(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    sin_nada = (await gerencia.post(PREGUNTA, json={"texto": "¿alguien intentó entrar desde otro equipo?"})).json()
    assert sin_nada["intencion"] == "equipos" and "nadie intentó entrar" in sin_nada["respuesta"]
    assert "está apagado" in sin_nada["respuesta"]
    await _autorizar_el_de(client, gerencia)
    await _activar(gerencia)
    async with nuevo_cliente() as celular:
        await celular.post(LOGIN, json=_datos("conserje2"))
    for frase in ("¿quién intentó entrar?", "mostrame los dispositivos conectados", "equipos no autorizados"):
        datos = (await gerencia.post(PREGUNTA, json={"texto": frase})).json()
        assert datos["intencion"] == "equipos", frase
        assert "1 intento" in datos["respuesta"] and "Conserje Dos" in datos["respuesta"]
        assert "con la clave correcta" in datos["respuesta"] and "esperando que decidas" in datos["respuesta"]
    como = (await gerencia.post(PREGUNTA, json={"texto": "¿cómo autorizo la PC de la ventanilla?"})).json()
    assert como["intencion"] == "ayuda:equipos"


async def test_al_conserje_mot_no_le_cuenta_los_intentos(client):
    datos = (await client.post(PREGUNTA, json={"texto": "¿quién intentó entrar?"})).json()
    assert datos["intencion"] != "equipos"


async def test_iniciar_sesion_sigue_igual_para_las_pruebas(cliente_como):
    # Sin el control activo nada cambia para nadie (las demás pruebas corren así).
    gerencia = await cliente_como("gerencia")
    async with nuevo_cliente() as otro:
        await iniciar_sesion(otro, "conserje2")
    assert (await _panel(gerencia))["control"] is False
