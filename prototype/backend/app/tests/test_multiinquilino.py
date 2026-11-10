"""Multiinquilino (migración 006): aislamiento entre establecimientos y rutas de la plataforma.

En SQLite se prueba la capa de la aplicación (filtro del ORM y establecimiento tomado del token). La capa de la
base (Row Level Security y claves foráneas compuestas) la verifica db/verify_multiinquilino.sql con motel_app.
"""

from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.seguridad import crear_token
from app.models.establecimiento import Establecimiento
from app.tests.conftest import (
    CLAVE_OTRO_MOTEL,
    CLAVE_PLATAFORMA,
    ESTABLECIMIENTO_OTRO,
    OPERADORES,
    abrir_guardia,
    nuevo_cliente,
)

LOGIN = "/api/v1/auth/login"
PLATAFORMA = "/api/v1/plataforma/establecimientos"

ALTA = {
    "codigo": "luna",
    "nombre": "Motel Luna",
    "domicilio": "Av. Siempreviva 742",
    "habitaciones": 5,
    "tarifa_base": 10000,
    "tarifa_fraccion": 3000,
    "fondo_cambio": 20000,
    "gerente_usuario": "gerencia",
    "gerente_nombre": "Gerencia Luna",
    "gerente_clave": "clave-gerencia-luna",
}


async def _entrar(ac: AsyncClient, establecimiento: str | None, usuario: str, clave: str) -> dict:
    resp = await ac.post(LOGIN, json={"establecimiento": establecimiento, "usuario": usuario, "clave": clave})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _cliente(establecimiento: str | None, usuario: str, clave: str) -> AsyncClient:
    ac = nuevo_cliente()
    await _entrar(ac, establecimiento, usuario, clave)
    return ac


# --- Aislamiento -------------------------------------------------------------------------------------------------


async def test_cada_establecimiento_ve_solo_sus_habitaciones_y_articulos(session_factory):
    async with nuevo_cliente() as propio, nuevo_cliente() as ajeno:
        sesion = await _entrar(propio, None, "conserje1", OPERADORES["conserje1"][2])
        assert sesion["establecimiento"]["codigo"] == "prueba"
        await _entrar(ajeno, ESTABLECIMIENTO_OTRO, "conserje1", CLAVE_OTRO_MOTEL)

        assert sorted(h["numero"] for h in (await propio.get("/api/v1/habitaciones/")).json()) == [1, 2, 3]
        assert sorted(h["numero"] for h in (await ajeno.get("/api/v1/habitaciones/")).json()) == [1, 7]
        articulos_ajenos = (await ajeno.get("/api/v1/articulos/")).json()
        assert [a["descripcion"] for a in articulos_ajenos] == ["Agua del otro motel"]
        assert all(a["descripcion"] != "Agua del otro motel" for a in (await propio.get("/api/v1/articulos/")).json())


async def test_el_mismo_usuario_en_otro_establecimiento_es_otra_persona(anonimo: AsyncClient):
    # La clave de conserje1 del establecimiento de prueba no sirve en el otro motel, y al revés.
    cuerpo = {"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "conserje1", "clave": OPERADORES["conserje1"][2]}
    malo = await anonimo.post(LOGIN, json=cuerpo)
    assert malo.status_code == 401
    malo = await anonimo.post(LOGIN, json={"usuario": "conserje1", "clave": CLAVE_OTRO_MOTEL})
    assert malo.status_code == 401
    inexistente = await anonimo.post(LOGIN, json={"establecimiento": "no-existe", "usuario": "x", "clave": "y"})
    assert inexistente.status_code == 401
    assert inexistente.json()["detail"] == malo.json()["detail"]


async def test_un_token_con_otro_establecimiento_no_da_acceso(anonimo: AsyncClient):
    # Operador 1 es conserje1 del establecimiento 1: un token que diga establecimiento 2 no vale.
    anonimo.cookies.set(settings.COOKIE_NOMBRE, crear_token(1, "OPERADOR", 2), path="/api")
    assert (await anonimo.get("/api/v1/habitaciones/")).status_code == 401
    anonimo.cookies.set(settings.COOKIE_NOMBRE, crear_token(1, "OPERADOR", 0), path="/api")
    assert (await anonimo.get("/api/v1/habitaciones/")).status_code == 401


async def test_no_se_opera_sobre_filas_de_otro_establecimiento(session_factory, cliente_como):
    gerencia_otra = await _cliente(ESTABLECIMIENTO_OTRO, "gerencia", CLAVE_OTRO_MOTEL)
    try:
        propios = (await gerencia_otra.get("/api/v1/configuracion/articulos")).json()
        assert len(propios) == 1
        # El artículo 1 es del establecimiento de prueba: para el otro motel no existe.
        ajeno = await gerencia_otra.patch("/api/v1/configuracion/articulos/1", json={"precio_unitario": 1})
        assert ajeno.status_code == 404
        assert (await gerencia_otra.patch("/api/v1/operadores/1", json={"activo": False})).status_code == 404
        habitaciones = (await gerencia_otra.get("/api/v1/configuracion/habitaciones")).json()
        assert {h["numero"] for h in habitaciones} == {1, 7}
    finally:
        await gerencia_otra.aclose()

    gerencia = await cliente_como("gerencia")
    precio = (await gerencia.get("/api/v1/configuracion/articulos")).json()
    assert any(a["id"] == 1 and a["precio_unitario"] == 800 for a in precio)


async def test_cada_establecimiento_tiene_su_propia_guardia_abierta(session_factory, cliente_como):
    conserje = await cliente_como("conserje1")
    await abrir_guardia(conserje)
    otro = await _cliente(ESTABLECIMIENTO_OTRO, "conserje1", CLAVE_OTRO_MOTEL)
    try:
        guardia = await abrir_guardia(otro)
        assert guardia["operador_nombre"] == "Conserje del otro motel"
        sesion = (await otro.get("/api/v1/auth/sesion")).json()
        assert sesion["guardia"]["id"] == guardia["id"]
    finally:
        await otro.aclose()


async def test_un_turno_usa_la_tarifa_de_su_establecimiento(session_factory):
    otro = await _cliente(ESTABLECIMIENTO_OTRO, "conserje1", CLAVE_OTRO_MOTEL)
    try:
        await abrir_guardia(otro)
        habitaciones = (await otro.get("/api/v1/habitaciones/")).json()
        libre = next(h for h in habitaciones if h["numero"] == 7)
        resp = await otro.post("/api/v1/turnos/", json={"habitacion_id": libre["id"], "tipo_cliente": "Peaton"})
        assert resp.status_code in (200, 201), resp.text
        assert resp.json()["tarifa_base"] == 9000
    finally:
        await otro.aclose()


# --- Plataforma ----------------------------------------------------------------------------------------------------


async def test_la_plataforma_ve_el_resumen_pero_no_la_operacion(session_factory):
    plataforma = await _cliente("plataforma", "plataforma", CLAVE_PLATAFORMA)
    try:
        sesion = (await plataforma.get("/api/v1/auth/sesion")).json()
        assert sesion["operador"]["rol"] == "PLATAFORMA" and sesion["establecimiento"] is None

        resumen = {e["codigo"]: e for e in (await plataforma.get(PLATAFORMA)).json()}
        assert set(resumen) == {"prueba", "otro"}
        assert resumen["prueba"]["habitaciones"] == 3 and resumen["prueba"]["usuarios"] == 3
        assert resumen["otro"]["ocupadas"] == 1

        rutas = ("/api/v1/habitaciones/", "/api/v1/articulos/", "/api/v1/arqueos/", "/api/v1/configuracion/tarifas")
        for ruta in rutas:
            assert (await plataforma.get(ruta)).status_code == 403, ruta
    finally:
        await plataforma.aclose()


async def test_la_gerencia_y_los_conserjes_no_usan_las_rutas_de_la_plataforma(cliente_como):
    for usuario in ("gerencia", "conserje1"):
        cliente = await cliente_como(usuario)
        assert (await cliente.get(PLATAFORMA)).status_code == 403
        assert (await cliente.post(PLATAFORMA, json=ALTA)).status_code == 403


async def test_la_plataforma_no_entra_con_el_codigo_de_un_motel(anonimo: AsyncClient):
    cuerpo = {"establecimiento": "prueba", "usuario": "plataforma", "clave": CLAVE_PLATAFORMA}
    resp = await anonimo.post(LOGIN, json=cuerpo)
    assert resp.status_code == 401
    # Y un gerente no entra como plataforma.
    resp = await anonimo.post(
        LOGIN, json={"establecimiento": "plataforma", "usuario": "gerencia", "clave": OPERADORES["gerencia"][2]}
    )
    assert resp.status_code == 401


async def test_alta_de_un_establecimiento_lo_deja_listo_para_operar(session_factory):
    plataforma = await _cliente("plataforma", "plataforma", CLAVE_PLATAFORMA)
    try:
        alta = await plataforma.post(PLATAFORMA, json=ALTA)
        assert alta.status_code == 201, alta.text
        assert alta.json()["codigo"] == "luna" and alta.json()["activo"]
        assert (await plataforma.post(PLATAFORMA, json=ALTA)).status_code == 409
        assert (await plataforma.post(PLATAFORMA, json={**ALTA, "codigo": "plataforma"})).status_code == 409
        resumen = {e["codigo"]: e for e in (await plataforma.get(PLATAFORMA)).json()}
        assert resumen["luna"]["habitaciones"] == 5 and resumen["luna"]["usuarios"] == 1
    finally:
        await plataforma.aclose()

    gerencia = await _cliente("luna", "gerencia", "clave-gerencia-luna")
    try:
        sesion = (await gerencia.get("/api/v1/auth/sesion")).json()
        assert sesion["operador"]["rol"] == "ADMINISTRADOR"
        assert sesion["establecimiento"]["nombre"] == "Motel Luna"
        assert len((await gerencia.get("/api/v1/habitaciones/")).json()) == 5
        tarifas = (await gerencia.get("/api/v1/configuracion/tarifas")).json()
        assert len(tarifas) == 1 and tarifas[0]["tarifa_base"] == 10000 and tarifas[0]["tarifa_fraccion"] == 3000
        assert (await gerencia.get("/api/v1/configuracion/caja")).json()["fondo_cambio"] == 20000
        assert (await gerencia.get("/api/v1/configuracion/articulos")).json() == []
        # La gerencia nueva da de alta su primer conserje y este abre la guardia con el fondo del establecimiento.
        conserje = {"usuario": "conserje1", "nombre_visible": "Conserje Luna", "clave": "clave-conserje-luna"}
        assert (await gerencia.post("/api/v1/operadores/", json=conserje)).status_code == 201
    finally:
        await gerencia.aclose()

    conserje = await _cliente("luna", "conserje1", "clave-conserje-luna")
    try:
        assert (await abrir_guardia(conserje))["fondo_inicial"] == 20000
    finally:
        await conserje.aclose()


async def test_suspender_un_establecimiento_corta_sus_sesiones(session_factory, cliente_como, db):
    conserje = await cliente_como("conserje1")
    assert (await conserje.get("/api/v1/habitaciones/")).status_code == 200
    plataforma = await _cliente("plataforma", "plataforma", CLAVE_PLATAFORMA)
    try:
        assert (await plataforma.patch(f"{PLATAFORMA}/1", json={"activo": False})).json()["activo"] is False
        resp = await conserje.get("/api/v1/habitaciones/")
        assert resp.status_code == 401 and "suspendido" in resp.json()["detail"]
        async with nuevo_cliente() as nuevo:
            login = await nuevo.post(LOGIN, json={"usuario": "conserje1", "clave": OPERADORES["conserje1"][2]})
            assert login.status_code == 401
        # El otro motel sigue operando.
        otro = await _cliente(ESTABLECIMIENTO_OTRO, "conserje1", CLAVE_OTRO_MOTEL)
        assert (await otro.get("/api/v1/habitaciones/")).status_code == 200
        await otro.aclose()

        assert (await plataforma.patch(f"{PLATAFORMA}/1", json={"activo": True})).json()["activo"] is True
        assert (await conserje.get("/api/v1/habitaciones/")).status_code == 200
    finally:
        await plataforma.aclose()
    assert (await db.execute(select(Establecimiento).where(Establecimiento.id == 1))).scalar_one().activo


async def test_la_gerencia_edita_los_datos_de_su_establecimiento(cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.patch(
        "/api/v1/configuracion/establecimiento",
        json={"nombre": "Motel de prueba S.A.", "telefono": "3764-000000", "leyenda_comprobante": "Gracias."},
    )
    assert resp.status_code == 200
    datos = (await gerencia.get("/api/v1/configuracion/establecimiento")).json()
    assert datos["nombre"] == "Motel de prueba S.A." and datos["codigo"] == "prueba"
    assert datos["leyenda_comprobante"] == "Gracias."
    assert (await gerencia.patch("/api/v1/configuracion/establecimiento", json={"nombre": " "})).status_code == 422
    conserje = await cliente_como("conserje1")
    assert (await conserje.get("/api/v1/configuracion/establecimiento")).status_code == 403
