"""Categorías de habitación con su tarifa y perfil de cada usuario (migración 008)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.services.billing_service import ParametrosTarifa, calcular_sobreturno
from app.tests.conftest import CLAVE_OTRO_MOTEL, CLAVE_PLATAFORMA, ESTABLECIMIENTO_OTRO, OPERADORES, nuevo_cliente

CATEGORIAS = "/api/v1/configuracion/categorias"
VIP = {
    "nombre": "VIP",
    "descripcion": "Jacuzzi y sauna",
    "color": "#7c3aed",
    "orden": 3,
    "tarifa": {
        "tarifa_base": 15000,
        "estadia_base_min": 180,
        "fraccion_min": 60,
        "tarifa_fraccion": 5000,
        "tolerancia_min": 10,
        "tope": 30000,
    },
}


# --- Liquidación con tolerancia y tope ---------------------------------------------------------------------------


def _tarifa(**cambios) -> ParametrosTarifa:
    base = {
        "tarifa_base": Decimal("15000"),
        "estadia_base_min": 180,
        "tolerancia_min": 0,
        "fraccion_min": 60,
        "tarifa_fraccion": Decimal("5000"),
        "tope": None,
    }
    return ParametrosTarifa(**{**base, **cambios})


def test_la_tolerancia_demora_la_primera_fraccion():
    tarifa = _tarifa(tolerancia_min=10)
    assert calcular_sobreturno(timedelta(minutes=189), tarifa) == 0
    # Superada la tolerancia, la fracción se cuenta desde el fin de la estadía base.
    assert calcular_sobreturno(timedelta(minutes=191), tarifa) == Decimal("5000")


def test_el_tope_limita_la_estadia_completa():
    tarifa = _tarifa(tope=Decimal("30000"))
    assert calcular_sobreturno(timedelta(hours=5), tarifa) == Decimal("10000")
    # 12 horas darían 9 fracciones ($45.000), pero la estadía no supera el tope de $30.000.
    assert calcular_sobreturno(timedelta(hours=12), tarifa) == Decimal("15000")


# --- Categorías ------------------------------------------------------------------------------------------------------


async def test_la_gerencia_crea_una_categoria_con_su_tarifa(cliente_como):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(CATEGORIAS, json=VIP)
    assert alta.status_code == 201, alta.text
    vip = alta.json()
    assert vip["tarifa"]["tarifa_base"] == 15000 and vip["tarifa"]["tope"] == 30000
    assert vip["tarifa"]["tolerancia_min"] == 10 and vip["habitaciones"] == 0
    assert (await gerencia.post(CATEGORIAS, json={**VIP, "nombre": "vip"})).status_code == 409
    nombres = [c["nombre"] for c in (await gerencia.get(CATEGORIAS)).json()]
    assert nombres == ["Simple", "VIP"]
    actividad = [e["accion"] for e in (await gerencia.get("/api/v1/configuracion/actividad")).json()]
    assert "CATEGORIA_ALTA" in actividad


@pytest.mark.parametrize(
    "tarifa",
    [
        {**VIP["tarifa"], "tope": 1000},  # tope menor que la base
        {**VIP["tarifa"], "fraccion_min": 0},
        {**VIP["tarifa"], "tolerancia_min": -5},
    ],
)
async def test_una_tarifa_invalida_se_rechaza(cliente_como, tarifa):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(CATEGORIAS, json={**VIP, "tarifa": tarifa})).status_code == 422


async def test_el_turno_toma_la_tarifa_de_la_categoria_de_la_habitacion(client: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    vip = (await gerencia.post(CATEGORIAS, json=VIP)).json()
    asignada = await gerencia.patch("/api/v1/configuracion/habitaciones/2", json={"categoria_id": vip["id"]})
    assert asignada.status_code == 200 and asignada.json()["categoria_id"] == vip["id"]

    grilla = {h["numero"]: h for h in (await client.get("/api/v1/habitaciones/")).json()}
    assert grilla[2]["categoria_id"] == vip["id"] and grilla[1]["categoria_id"] != vip["id"]

    vip_turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 2, "tipo_cliente": "Auto"})).json()
    simple_turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    assert vip_turno["tarifa_base"] == 15000 and simple_turno["tarifa_base"] == 8000
    resumen = (await client.get(f"/api/v1/turnos/{vip_turno['id']}/resumen")).json()
    assert resumen["tarifa"]["categoria"] == "VIP" and resumen["tarifa"]["estadia_base_min"] == 180

    # Cambiar la tarifa VIP o la categoría de la habitación no toca el turno en curso (RN-DER-06).
    nueva = {**VIP["tarifa"], "tarifa_base": 20000, "tope": None, "categoria_id": vip["id"]}
    assert (await gerencia.post("/api/v1/configuracion/tarifas", json=nueva)).status_code == 201
    assert (await gerencia.patch("/api/v1/configuracion/habitaciones/2", json={"categoria_id": 1})).status_code == 200
    resumen = (await client.get(f"/api/v1/turnos/{vip_turno['id']}/resumen")).json()
    assert resumen["tarifa_base"] == 15000 and resumen["tarifa"]["categoria"] == "VIP"


async def test_cambiar_la_tarifa_de_una_categoria_no_toca_las_demas(cliente_como):
    gerencia = await cliente_como("gerencia")
    vip = (await gerencia.post(CATEGORIAS, json=VIP)).json()
    cambio = {
        "tarifa_base": 18000,
        "estadia_base_min": 120,
        "fraccion_min": 30,
        "tarifa_fraccion": 4000,
        "categoria_id": vip["id"],
    }
    assert (await gerencia.post("/api/v1/configuracion/tarifas", json=cambio)).status_code == 201
    categorias = {c["nombre"]: c for c in (await gerencia.get(CATEGORIAS)).json()}
    assert categorias["VIP"]["tarifa"]["tarifa_base"] == 18000
    assert categorias["Simple"]["tarifa"]["tarifa_base"] == 8000
    historial = (await gerencia.get("/api/v1/configuracion/tarifas", params={"categoria_id": vip["id"]})).json()
    assert [t["vigente"] for t in historial] == [True, False]


async def test_una_categoria_con_habitaciones_no_se_da_de_baja(cliente_como):
    gerencia = await cliente_como("gerencia")
    vip = (await gerencia.post(CATEGORIAS, json=VIP)).json()
    await gerencia.patch("/api/v1/configuracion/habitaciones/1", json={"categoria_id": vip["id"]})
    baja = await gerencia.patch(f"{CATEGORIAS}/{vip['id']}", json={"activa": False})
    assert baja.status_code == 409 and "reasígnelas" in baja.json()["detail"]

    await gerencia.patch("/api/v1/configuracion/habitaciones/1", json={"categoria_id": 1})
    assert (await gerencia.patch(f"{CATEGORIAS}/{vip['id']}", json={"activa": False})).json()["activa"] is False
    # A una categoría dada de baja no se le asignan habitaciones.
    assert (
        await gerencia.patch("/api/v1/configuracion/habitaciones/1", json={"categoria_id": vip["id"]})
    ).status_code == 409
    alta = await gerencia.post("/api/v1/configuracion/habitaciones", json={"numero": 30, "categoria_id": vip["id"]})
    assert alta.status_code == 409


async def test_la_gerencia_edita_nombre_color_y_descripcion(cliente_como):
    gerencia = await cliente_como("gerencia")
    cambio = await gerencia.patch(
        f"{CATEGORIAS}/1", json={"nombre": "Clásica", "color": "#0f766e", "descripcion": "Cama queen"}
    )
    assert cambio.status_code == 200
    assert (cambio.json()["nombre"], cambio.json()["color"]) == ("Clásica", "#0f766e")
    assert (await gerencia.patch(f"{CATEGORIAS}/1", json={"color": "verde"})).status_code == 422


async def test_el_conserje_lee_las_categorias_pero_no_las_cambia(client: AsyncClient):
    categorias = (await client.get("/api/v1/categorias/")).json()
    assert [c["nombre"] for c in categorias] == ["Simple"] and categorias[0]["tarifa"]["tarifa_base"] == 8000
    assert (await client.post(CATEGORIAS, json=VIP)).status_code == 403


async def test_las_categorias_son_de_cada_establecimiento(cliente_como):
    gerencia = await cliente_como("gerencia")
    vip = (await gerencia.post(CATEGORIAS, json=VIP)).json()
    async with nuevo_cliente() as otra:
        await otra.post(
            "/api/v1/auth/login",
            json={"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL},
        )
        assert [c["nombre"] for c in (await otra.get(CATEGORIAS)).json()] == ["Simple"]
        assert (await otra.patch(f"{CATEGORIAS}/{vip['id']}", json={"color": "#000000"})).status_code == 404
        propias = (await otra.get("/api/v1/configuracion/habitaciones")).json()
        asignar = await otra.patch(
            f"/api/v1/configuracion/habitaciones/{propias[0]['id']}", json={"categoria_id": vip["id"]}
        )
        assert asignar.status_code == 404


# --- Perfil ----------------------------------------------------------------------------------------------------------


async def test_el_perfil_muestra_los_datos_y_la_actividad(client: AsyncClient):
    perfil = (await client.get("/api/v1/perfil/")).json()
    assert perfil["usuario"] == "conserje1" and perfil["rol"] == "OPERADOR"
    assert perfil["establecimiento_nombre"] == "Motel de prueba" and perfil["guardias_30_dias"] == 1
    assert "hash" not in str(perfil)


async def test_cada_usuario_cambia_su_nombre_visible(client: AsyncClient, cliente_como):
    resp = await client.patch("/api/v1/perfil/", json={"nombre_visible": "  Conserje Uno (turno noche) "})
    assert resp.status_code == 200 and resp.json()["nombre_visible"] == "Conserje Uno (turno noche)"
    assert (await client.get("/api/v1/auth/sesion")).json()["operador"][
        "nombre_visible"
    ] == "Conserje Uno (turno noche)"
    assert (await client.patch("/api/v1/perfil/", json={"nombre_visible": "   "})).status_code == 422
    gerencia = await cliente_como("gerencia")
    entrada = (await gerencia.get("/api/v1/configuracion/actividad", params={"categoria": "PERFIL"})).json()[0]
    assert entrada["accion"] == "PERFIL_NOMBRE" and entrada["requiere_revision"]


async def test_cambio_de_la_clave_propia(anonimo: AsyncClient, cliente_como):
    conserje = await cliente_como("conserje2")
    actual = OPERADORES["conserje2"][2]
    mala = await conserje.post("/api/v1/perfil/clave", json={"actual": "no-es-esta", "nueva": "clave-nueva-larga"})
    assert mala.status_code == 400
    assert (await conserje.post("/api/v1/perfil/clave", json={"actual": actual, "nueva": actual})).status_code == 422
    assert (await conserje.post("/api/v1/perfil/clave", json={"actual": actual, "nueva": "corta"})).status_code == 422
    assert (
        await conserje.post("/api/v1/perfil/clave", json={"actual": actual, "nueva": "clave-nueva-larga"})
    ).status_code == 204
    # La sesión sigue abierta; la clave vieja ya no sirve y la nueva sí.
    assert (await conserje.get("/api/v1/perfil/")).status_code == 200
    vieja = await anonimo.post("/api/v1/auth/login", json={"usuario": "conserje2", "clave": actual})
    assert vieja.status_code == 401
    nueva = await anonimo.post("/api/v1/auth/login", json={"usuario": "conserje2", "clave": "clave-nueva-larga"})
    assert nueva.status_code == 200


async def test_la_gerencia_restablece_la_clave_de_un_conserje(anonimo: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.post("/api/v1/operadores/2/clave", json={"nueva": "clave-restablecida-1"})
    assert resp.status_code == 200 and resp.json()["usuario"] == "conserje2"
    login = await anonimo.post("/api/v1/auth/login", json={"usuario": "conserje2", "clave": "clave-restablecida-1"})
    assert login.status_code == 200
    # No a la gerencia, no a un inexistente, y un conserje no puede usarlo.
    assert (
        await gerencia.post("/api/v1/operadores/3/clave", json={"nueva": "clave-restablecida-1"})
    ).status_code == 409
    assert (
        await gerencia.post("/api/v1/operadores/99/clave", json={"nueva": "clave-restablecida-1"})
    ).status_code == 404
    conserje = await cliente_como("conserje1")
    assert (
        await conserje.post("/api/v1/operadores/2/clave", json={"nueva": "clave-restablecida-1"})
    ).status_code == 403
    entrada = (await gerencia.get("/api/v1/configuracion/actividad", params={"categoria": "PERFIL"})).json()[0]
    assert entrada["accion"] == "CLAVE_RESTABLECIDA" and not entrada["requiere_revision"]


async def test_la_plataforma_tambien_tiene_perfil(session_factory):
    async with nuevo_cliente() as plataforma:
        await plataforma.post(
            "/api/v1/auth/login",
            json={"establecimiento": "plataforma", "usuario": "plataforma", "clave": CLAVE_PLATAFORMA},
        )
        perfil = (await plataforma.get("/api/v1/perfil/")).json()
        assert perfil["rol"] == "PLATAFORMA" and perfil["establecimiento_nombre"] is None
        assert (await plataforma.patch("/api/v1/perfil/", json={"nombre_visible": "Soporte"})).status_code == 200


# --- Reporte por categoría --------------------------------------------------------------------------------------------


async def test_la_gerencia_ve_ingresos_y_ocupacion_por_categoria(client: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    vip = (await gerencia.post(CATEGORIAS, json=VIP)).json()
    await gerencia.patch("/api/v1/configuracion/habitaciones/2", json={"categoria_id": vip["id"]})
    cobrado = (await client.post("/api/v1/turnos/", json={"habitacion_id": 2, "tipo_cliente": "Auto"})).json()
    cobro = await client.post(
        f"/api/v1/turnos/{cobrado['id']}/cerrar", json={"pagos": [{"monto": 15000, "medio_pago": "EFECTIVO"}]}
    )
    assert cobro.status_code == 200, cobro.text

    # RN-RES-03: mientras la guardia está abierta, su cobro no aparece (revelaría el total antes del cierre ciego).
    resumen = {c["nombre"]: c for c in (await gerencia.get("/api/v1/arqueos/por-categoria")).json()}
    assert resumen["VIP"]["turnos"] == 0 and resumen["VIP"]["ingresos"] == 0
    otro = await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})
    await client.post(
        f"/api/v1/turnos/{otro.json()['id']}/cerrar", json={"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
    )
    assert (await client.post("/api/v1/guardias/actual/arqueo", json={"efectivo": 23000})).status_code == 201
    await client.post("/api/v1/guardias/")  # guardia siguiente
    resumen = {c["nombre"]: c for c in (await gerencia.get("/api/v1/arqueos/por-categoria")).json()}
    assert resumen["VIP"]["turnos"] == 1 and resumen["VIP"]["ingresos"] == 15000
    assert resumen["VIP"]["ticket_promedio"] == 15000 and resumen["VIP"]["habitaciones"] == 1
    # El turno en curso no suma ingresos, pero la habitación cuenta como ocupada.
    await client.patch("/api/v1/habitaciones/1/liberar")
    await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})  # queda en curso
    resumen = {c["nombre"]: c for c in (await gerencia.get("/api/v1/arqueos/por-categoria")).json()}
    assert resumen["Simple"]["turnos"] == 1 and resumen["Simple"]["ocupadas"] == 1
    assert (await client.get("/api/v1/arqueos/por-categoria")).status_code == 403
