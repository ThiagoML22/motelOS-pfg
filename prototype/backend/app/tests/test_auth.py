"""RNF-04: autenticación, sesión en cookie httpOnly, roles y atribución de cada operación al operador."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.seguridad import crear_token
from app.main import app
from app.models.consumo import Consumo
from app.models.operador import Operador
from app.models.pago import Pago
from app.models.turno import Turno
from app.tests.conftest import OPERADORES, nuevo_cliente

LOGIN = "/api/v1/auth/login"


async def _login(ac: AsyncClient, usuario: str, clave: str):
    return await ac.post(LOGIN, json={"usuario": usuario, "clave": clave})


async def _id_operador(db, usuario: str) -> int:
    return (await db.execute(select(Operador.id).where(Operador.usuario == usuario))).scalar_one()


# --- Inicio de sesión ----------------------------------------------------------------------------


async def test_login_correcto_entrega_cookie_httponly_y_strict(anonimo: AsyncClient):
    resp = await _login(anonimo, "conserje1", OPERADORES["conserje1"][2])

    assert resp.status_code == 200
    assert resp.json()["operador"] == {"id": 1, "usuario": "conserje1", "nombre_visible": "Conserje Uno",
                                       "rol": "OPERADOR"}
    cookie = resp.headers["set-cookie"].lower()
    # Criterio de RNF-04: el token no es visible desde document.cookie.
    assert f"{settings.COOKIE_NOMBRE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api" in cookie
    # Nunca se devuelve el hash ni el token en el cuerpo.
    assert "hash" not in resp.text and "token" not in resp.text


async def test_usuario_inexistente_y_clave_incorrecta_dan_el_mismo_mensaje(anonimo: AsyncClient):
    a = await _login(anonimo, "nadie", "lo-que-sea")
    b = await _login(anonimo, "conserje1", "clave-equivocada")

    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() == {"detail": "Usuario o clave incorrectos."}


async def test_operador_dado_de_baja_no_inicia_sesion(anonimo: AsyncClient):
    resp = await _login(anonimo, "baja", OPERADORES["baja"][2])
    assert resp.status_code == 401


async def test_el_usuario_no_distingue_mayusculas_ni_espacios(anonimo: AsyncClient):
    resp = await _login(anonimo, "  Conserje1 ", OPERADORES["conserje1"][2])
    assert resp.status_code == 200


async def test_bloqueo_tras_cinco_intentos_fallidos(anonimo: AsyncClient, db):
    for _ in range(settings.LOGIN_MAX_INTENTOS):
        assert (await _login(anonimo, "conserje2", "mal")).status_code == 401

    # El sexto intento se rechaza aunque la clave sea la correcta.
    resp = await _login(anonimo, "conserje2", OPERADORES["conserje2"][2])
    assert resp.status_code == 429

    operador = (await db.execute(select(Operador).where(Operador.usuario == "conserje2"))).scalar_one()
    assert operador.bloqueado_hasta is not None


async def test_el_bloqueo_vence_y_un_acceso_correcto_reinicia_los_intentos(anonimo: AsyncClient, db):
    operador = (await db.execute(select(Operador).where(Operador.usuario == "conserje2"))).scalar_one()
    operador.bloqueado_hasta = datetime.now(UTC) - timedelta(minutes=1)
    operador.intentos_fallidos = 3
    await db.commit()

    assert (await _login(anonimo, "conserje2", OPERADORES["conserje2"][2])).status_code == 200
    db.expire_all()
    operador = (await db.execute(select(Operador).where(Operador.usuario == "conserje2"))).scalar_one()
    assert operador.intentos_fallidos == 0
    assert operador.bloqueado_hasta is None
    assert operador.ultimo_acceso is not None


# --- Sesión ---------------------------------------------------------------------------------------


async def test_sesion_devuelve_el_operador(client: AsyncClient):
    resp = await client.get("/api/v1/auth/sesion")
    assert resp.status_code == 200
    assert resp.json()["operador"]["usuario"] == "conserje1"


async def test_logout_cierra_la_sesion(client: AsyncClient):
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.get("/api/v1/habitaciones/")).status_code == 401


def _rutas_protegidas() -> list[tuple[str, str]]:
    """Todas las rutas de la API según su esquema OpenAPI, salvo las públicas."""
    publicas = {"/health", "/api/v1/auth/login", "/api/v1/auth/logout"}
    rutas = []
    for camino, operaciones in sorted(app.openapi()["paths"].items()):
        if not camino.startswith("/api/") or camino in publicas:
            continue
        for metodo in sorted(m.upper() for m in operaciones):
            concreto = camino.replace("{turno_id}", str(uuid.uuid4())).replace("{habitacion_id}", "1")
            concreto = concreto.replace("{arqueo_id}", "1").replace("{guardia_id}", "1")
            rutas.append((metodo, concreto))
    assert len(rutas) >= 8, "No se encontraron las rutas de la API"
    return rutas


@pytest.mark.parametrize(("metodo", "camino"), _rutas_protegidas())
async def test_toda_ruta_de_la_api_exige_sesion(anonimo: AsyncClient, metodo: str, camino: str):
    resp = await anonimo.request(metodo, camino, json={})
    assert resp.status_code == 401, f"{metodo} {camino} respondió {resp.status_code}"


async def test_token_adulterado_o_vencido_responde_401(anonimo: AsyncClient):
    # Control: el mismo mecanismo con un token válido sí da acceso.
    anonimo.cookies.set(settings.COOKIE_NOMBRE, crear_token(1, "OPERADOR"), path="/api")
    assert (await anonimo.get("/api/v1/habitaciones/")).status_code == 200

    vencido = crear_token(1, "OPERADOR", ahora=datetime.now(UTC) - timedelta(hours=settings.SESION_HORAS + 1))
    firma = crear_token(1, "OPERADOR")
    adulterado = firma[:-4] + ("AAAA" if not firma.endswith("AAAA") else "BBBB")
    for token in (vencido, adulterado):
        anonimo.cookies.set(settings.COOKIE_NOMBRE, token, path="/api")
        assert (await anonimo.get("/api/v1/habitaciones/")).status_code == 401


async def test_token_con_otro_rol_que_el_del_operador_responde_401(anonimo: AsyncClient):
    # Un token que diga ADMINISTRADOR para un conserje (firmado o no) no da permisos de gerencia.
    anonimo.cookies.set(settings.COOKIE_NOMBRE, crear_token(1, "ADMINISTRADOR"), path="/api")
    assert (await anonimo.get("/api/v1/habitaciones/")).status_code == 401


async def test_operador_desactivado_pierde_la_sesion_abierta(client: AsyncClient, db):
    operador = (await db.execute(select(Operador).where(Operador.usuario == "conserje1"))).scalar_one()
    operador.activo = False
    await db.commit()
    assert (await client.get("/api/v1/habitaciones/")).status_code == 401


# --- CSRF -----------------------------------------------------------------------------------------


async def test_peticion_que_modifica_sin_el_encabezado_de_la_app_responde_403(session_factory):
    async with nuevo_cliente() as ac:
        await _login(ac, "conserje1", OPERADORES["conserje1"][2])
        del ac.headers["X-Requested-With"]
        resp = await ac.post("/api/v1/turnos/", json={"habitacion_id": 1})
        assert resp.status_code == 403
        # Las consultas no cambian datos y no lo necesitan.
        assert (await ac.get("/api/v1/habitaciones/")).status_code == 200


# --- Atribución -----------------------------------------------------------------------------------


async def test_turno_consumo_y_cobro_quedan_a_nombre_del_operador_de_la_sesion(client: AsyncClient, db):
    conserje1 = await _id_operador(db, "conserje1")
    conserje2 = await _id_operador(db, "conserje2")

    # El cuerpo intenta atribuir el turno a otro operador: se ignora.
    turno = (await client.post(
        "/api/v1/turnos/", json={"habitacion_id": 1, "operador_apertura_id": conserje2}
    )).json()
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    cobro = await client.post(
        f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": [{"medio_pago": "EFECTIVO", "monto": 8800}]}
    )
    assert cobro.status_code == 200, cobro.text

    fila = (await db.execute(select(Turno))).scalar_one()
    assert fila.operador_apertura_id == conserje1
    assert fila.operador_cierre_id == conserje1
    assert (await db.execute(select(Consumo.operador_id))).scalar_one() == conserje1
    assert (await db.execute(select(Pago.operador_id))).scalar_one() == conserje1
