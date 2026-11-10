"""Apariencia y avisos de cada motel, marca pública del ingreso y novedades de guardia (migración 009)."""

from app.tests.conftest import CLAVE_OTRO_MOTEL, ESTABLECIMIENTO_OTRO, ESTABLECIMIENTO_PRUEBA, nuevo_cliente

ESTABLECIMIENTO = "/api/v1/configuracion/establecimiento"
NOVEDADES = "/api/v1/novedades/"


async def test_la_gerencia_personaliza_su_motel_y_queda_en_la_sesion(cliente_como):
    gerencia = await cliente_como("gerencia")
    cambio = {"color_marca": "#B4235A", "eslogan": "Tu lugar", "aviso_por_vencer_min": 0, "alertas_sonoras": True}
    resp = await gerencia.patch(ESTABLECIMIENTO, json=cambio)
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    # El color se guarda en minúsculas; 0 minutos (sin aviso) y False son valores válidos, no «vacíos».
    assert datos["color_marca"] == "#b4235a" and datos["aviso_por_vencer_min"] == 0 and datos["alertas_sonoras"]
    sesion = (await gerencia.get("/api/v1/auth/sesion")).json()["establecimiento"]
    assert sesion["color_marca"] == "#b4235a" and sesion["eslogan"] == "Tu lugar"
    assert (await gerencia.patch(ESTABLECIMIENTO, json={"alertas_sonoras": False})).json()["alertas_sonoras"] is False
    # Vaciar el color vuelve al azul de MotelOS.
    assert (await gerencia.patch(ESTABLECIMIENTO, json={"color_marca": ""})).json()["color_marca"] is None
    acciones = [e["descripcion"] for e in (await gerencia.get("/api/v1/configuracion/actividad")).json()]
    assert "Cambio de color de marca" in acciones and "Cambio de alertas sonoras" in acciones


async def test_valores_invalidos_de_apariencia(cliente_como):
    gerencia = await cliente_como("gerencia")
    for cambio in (
        {"color_marca": "rojo"},
        {"color_marca": "#12345"},
        {"aviso_por_vencer_min": 500},
        {"aviso_por_vencer_min": -1},
    ):
        assert (await gerencia.patch(ESTABLECIMIENTO, json=cambio)).status_code == 422, cambio
    conserje = await cliente_como("conserje1")
    assert (await conserje.patch(ESTABLECIMIENTO, json={"eslogan": "x"})).status_code == 403


async def test_la_marca_publica_del_ingreso(cliente_como, anonimo):
    gerencia = await cliente_como("gerencia")
    await gerencia.patch(ESTABLECIMIENTO, json={"color_marca": "#0f766e", "eslogan": "Bienvenidos"})
    resp = await anonimo.get("/api/v1/auth/marca", params={"codigo": f" {ESTABLECIMIENTO_PRUEBA.upper()} "})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "codigo": ESTABLECIMIENTO_PRUEBA,
        "nombre": "Motel de prueba",
        "color_marca": "#0f766e",
        "eslogan": "Bienvenidos",
    }
    assert (await anonimo.get("/api/v1/auth/marca", params={"codigo": "no-existe"})).status_code == 404


async def test_el_conserje_deja_novedades_en_su_guardia(client, cliente_como):
    resp = await client.post(
        NOVEDADES, json={"texto": "  La 2 tiene la ducha floja  ", "importante": True, "habitacion_id": 2}
    )
    assert resp.status_code == 201, resp.text
    novedad = resp.json()
    assert novedad["texto"] == "La 2 tiene la ducha floja" and novedad["importante"]
    assert novedad["operador_nombre"] == "Conserje Uno" and novedad["franja"] and novedad["habitacion_numero"] == 2
    assert (await client.post(NOVEDADES, json={"texto": "   "})).status_code == 422
    assert (await client.post(NOVEDADES, json={"texto": "x", "habitacion_id": 999})).status_code == 404

    # Sin guardia propia, el conserje no escribe; la gerencia sí (sin guardia).
    otro = await cliente_como("conserje2")
    assert (await otro.post(NOVEDADES, json={"texto": "hola"})).status_code == 409
    gerencia = await cliente_como("gerencia")
    aviso = (await gerencia.post(NOVEDADES, json={"texto": "Mañana viene el técnico del aire"})).json()
    assert aviso["guardia_id"] is None and aviso["operador_nombre"] == "Gerencia"
    lista = (await otro.get(NOVEDADES)).json()
    assert [n["texto"] for n in lista] == ["Mañana viene el técnico del aire", "La 2 tiene la ducha floja"]


async def test_las_novedades_no_cruzan_de_motel(client):
    await client.post(NOVEDADES, json={"texto": "Solo de este motel"})
    async with nuevo_cliente() as otro:
        login = {"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL}
        assert (await otro.post("/api/v1/auth/login", json=login)).status_code == 200
        assert (await otro.get(NOVEDADES)).json() == []
        # Una habitación de otro motel no se puede citar.
        propias = (await client.get("/api/v1/habitaciones/")).json()
        assert (await otro.post(NOVEDADES, json={"texto": "x", "habitacion_id": propias[0]["id"]})).status_code == 404
