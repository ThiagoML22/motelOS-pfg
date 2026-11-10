"""Asistente de ayuda para todo el personal y resumen de arqueos por mes."""

import re

import pytest

from scripts.cargar_historial import generar_historial

PREGUNTA = "/api/v1/asistente/pregunta"


async def _preguntar(cliente, texto: str) -> dict:
    resp = await cliente.post(PREGUNTA, json={"texto": texto})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize(
    ("pregunta", "tema", "vista"),
    [
        ("¿Cómo abro un turno?", "abrir_turno", "dashboard"),
        ("como cargo un consumo del minibar", "consumo", "dashboard"),
        ("¿Cómo cierro la caja?", "cierre_caja", "caja"),
        ("Se cortó la conexión, ¿qué hago?", "conexion", None),
        ("como reponer mercaderia", "inventario", "inventario"),
        ("quiero cambiar mi clave", "clave", "perfil"),
        ("¿cómo se calcula el sobreturno?", "tarifa", "dashboard"),
    ],
)
async def test_el_conserje_recibe_los_pasos(client, pregunta, tema, vista):
    datos = await _preguntar(client, pregunta)
    assert datos["intencion"] == f"ayuda:{tema}", datos
    assert len(datos["pasos"]) >= 2
    assert [a["vista"] for a in datos["acciones"]] == ([vista] if vista else [])


async def test_la_ventanilla_ahora(client):
    libres = await _preguntar(client, "¿Qué habitaciones están libres?")
    assert libres["intencion"] == "libres" and re.search(r"\b1, 2\b", libres["respuesta"])
    assert {a["habitacion_id"] for a in libres["acciones"]} == {1, 2}

    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    vencen = await _preguntar(client, "¿cuál vence primero?")
    assert vencen["intencion"] == "vencimientos" and "la 1" in vencen["respuesta"]
    cuenta = await _preguntar(client, "¿cuánto debe la 1?")
    assert cuenta["intencion"] == "cuenta" and "debe $8.800" in cuenta["respuesta"], cuenta
    # La consulta no guardó nada: el turno sigue igual.
    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["estado"] == "En Curso"

    stock = await _preguntar(client, "¿cuántas aguas quedan?")
    assert stock["intencion"] == "stock" and "Quedan 4 de «Agua Mineral 500ml»" in stock["respuesta"]
    tarifa = await _preguntar(client, "¿cuánto sale la simple?")
    assert tarifa["intencion"] == "tarifas" and "Simple: $8.000 por 2 h" in tarifa["respuesta"]


async def test_rn_res_03_el_conserje_no_ve_dinero_de_la_caja(client):
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 2, "tipo_cliente": "Auto"})).json()
    cobro = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=cobro)).status_code == 200
    llevo = await _preguntar(client, "¿Cuánto llevo cobrado?")
    assert llevo["intencion"] == "ayuda:total_caja" and "8.000" not in str(llevo)
    for pregunta in ("¿cuánto facturamos la semana pasada?", "¿quién tuvo más faltantes?", "¿cómo venimos?"):
        datos = await _preguntar(client, pregunta)
        assert datos["intencion"] == "fuera_de_alcance", (pregunta, datos)
        assert "$" not in datos["respuesta"]


async def test_la_gerencia_tiene_ayuda_y_analisis(cliente_como):
    gerencia = await cliente_como("gerencia")
    for pregunta in ("¿Cómo cambio la tarifa de una categoría?", "¿Cómo cambio una tarifa?"):
        como = await _preguntar(gerencia, pregunta)
        assert como["intencion"] == "ayuda:config_tarifas" and como["acciones"][0]["vista"] == "configuracion"
    analisis = await _preguntar(gerencia, "¿cuánto facturamos la semana pasada?")
    assert analisis["intencion"] == "ingresos" and analisis["pasos"] == [] and analisis["acciones"] == []
    # Los temas de la gerencia no se le ofrecen a un conserje.
    conserje = await cliente_como("conserje2")
    assert (await _preguntar(conserje, "como doy de alta un conserje"))["intencion"] != "ayuda:conserjes"


async def test_arqueos_por_mes(db, cliente_como):
    historial = await generar_historial(db, dias=42, semilla=5)
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.get("/api/v1/arqueos/meses")
    assert resp.status_code == 200, resp.text
    meses = resp.json()
    assert [m["mes"] for m in meses] == sorted((m["mes"] for m in meses), reverse=True)
    assert sum(m["arqueos"] for m in meses) == historial["arqueos"]
    for m in meses:
        assert m["desde"].startswith(m["mes"]) and m["hasta"].startswith(m["mes"])
        assert m["arqueos"] == m["correctos"] + m["faltantes"] + m["sobrantes"]
    uno = (await gerencia.get("/api/v1/arqueos/meses", params={"operador_id": 2})).json()
    assert sum(m["arqueos"] for m in uno) < historial["arqueos"]
    conserje = await cliente_como("conserje1")
    assert (await conserje.get("/api/v1/arqueos/meses")).status_code == 403
