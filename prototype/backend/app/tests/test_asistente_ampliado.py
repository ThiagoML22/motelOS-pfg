"""Asistente ampliado: glosario, sinónimos y errores de tipeo, charla, más datos en vivo, seguimientos y búsqueda por
parecido."""

import pytest

from app.services import ayuda
from scripts.cargar_historial import generar_historial

PREGUNTA = "/api/v1/asistente/pregunta"


async def _preguntar(
    cliente, texto: str, anterior: str | None = None, anterior_intencion: str | None = None, pantalla: str | None = None
) -> dict:
    cuerpo = {"texto": texto, "anterior": anterior, "anterior_intencion": anterior_intencion, "pantalla": pantalla}
    resp = await cliente.post(PREGUNTA, json=cuerpo)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize(
    ("pregunta", "definicion"),
    [
        ("¿Qué es la tolerancia?", "tolerancia"),
        ("¿qué significa cierre ciego?", "cierre_ciego"),
        ("¿Para qué sirve el fondo de cambio?", "fondo"),
        ("que es un arqueo", "arqueo"),
        ("¿Qué es el sobreturno?", "sobreturno"),
        ("¿Qué es MotelOS?", "motelos"),
        ("que son las novedades", "novedad"),
    ],
)
async def test_el_glosario(client, pregunta, definicion):
    datos = await _preguntar(client, pregunta)
    assert datos["intencion"] == f"definicion:{definicion}", datos
    assert len(datos["respuesta"]) > 60


async def test_las_definiciones_de_la_gerencia_no_se_le_dan_al_conserje(client, cliente_como):
    assert (await _preguntar(client, "¿Qué es la TDC?"))["intencion"] != "definicion:tdc"
    gerencia = await cliente_como("gerencia")
    assert (await _preguntar(gerencia, "¿Qué es la TDC?"))["intencion"] == "definicion:tdc"


async def test_sinonimos_errores_de_tipeo_y_charla(client):
    assert (await _preguntar(client, "que habitaciones estan lirbes"))["intencion"] == "libres"
    assert (await _preguntar(client, "¿cuánto debe la pieza 1?"))["intencion"] == "cuenta"
    for saludo in ("hola", "Buenas tardes", "gracias!", "¿qué podés hacer?"):
        assert (await _preguntar(client, saludo))["intencion"] == "charla", saludo


async def test_mas_datos_de_la_ventanilla(client):
    guardia = await _preguntar(client, "¿Quién está de guardia?")
    assert guardia["intencion"] == "guardia" and "Conserje Uno" in guardia["respuesta"]
    estado = await _preguntar(client, "¿cómo está la ventanilla?")
    assert estado["intencion"] == "estado" and "1 en mantenimiento" in estado["respuesta"]
    assert "(3)" in (await _preguntar(client, "¿qué habitaciones están en mantenimiento?"))["respuesta"]
    await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})
    ocupadas = await _preguntar(client, "¿qué habitaciones están ocupadas?")
    assert ocupadas["intencion"] == "ocupadas" and "la 1" in ocupadas["respuesta"]
    assert (await _preguntar(client, "¿cuál es el fondo de cambio?"))["intencion"] == "fondo"
    assert (await _preguntar(client, "¿hay pedidos pendientes?"))["intencion"] == "pedidos"
    await client.post("/api/v1/novedades/", json={"texto": "Falta papel en la 2", "importante": True})
    novedades = await _preguntar(client, "¿qué novedades hay?")
    assert novedades["intencion"] == "novedades" and "Falta papel en la 2" in novedades["respuesta"]
    bajo = await _preguntar(client, "¿qué artículos tienen poco stock?")
    assert bajo["intencion"] == "stock" and "Papas Fritas (0)" in bajo["respuesta"]


async def test_seguimiento_de_la_ventanilla(client):
    await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})
    primera = await _preguntar(client, "¿cuánto debe la 1?")
    assert primera["intencion"] == "cuenta" and "debe $8.000" in primera["respuesta"]
    segunda = await _preguntar(client, "¿y la 2?", "¿cuánto debe la 1?", "cuenta")
    assert segunda["intencion"] == "cuenta" and "La 2 no tiene un turno en curso" in segunda["respuesta"]


async def test_seguimiento_del_analisis(db, cliente_como):
    await generar_historial(db, dias=28, semilla=4)
    gerencia = await cliente_como("gerencia")
    primera = await _preguntar(gerencia, "¿cuánto facturamos la semana pasada?")
    assert primera["intencion"] == "ingresos"
    segunda = await _preguntar(gerencia, "¿y en simple?", "¿cuánto facturamos la semana pasada?", "ingresos")
    assert segunda["intencion"] == "ingresos" and "en Simple" in segunda["respuesta"]
    assert segunda["periodo"] == primera["periodo"]
    tercera = await _preguntar(gerencia, "¿y ayer?", "¿cuánto facturamos la semana pasada?", "ingresos")
    assert tercera["intencion"] == "ingresos" and tercera["respuesta"].startswith("Ayer")
    # Con errores de tipeo.
    assert (await _preguntar(gerencia, "cuanto factruamos ayer"))["intencion"] == "ingresos"
    # El conserje puede preguntar por la demanda (no muestra dinero), no por los ingresos.
    conserje = await cliente_como("conserje1")
    assert (await _preguntar(conserje, "¿A qué hora hay más demanda los sábados?"))["intencion"] == "horas"
    assert (await _preguntar(conserje, "¿y ayer?", "¿cuánto facturamos?", "ingresos"))[
        "intencion"
    ] == "fuera_de_alcance"


@pytest.mark.parametrize(
    ("pregunta", "intencion"),
    [
        ("me equivoque en el arqueo, se puede corregir?", "definicion:inmutable"),
        ("por que no veo cuanta plata hay en la caja", "definicion:cierre_ciego"),
        ("el cliente quiere pagar con tarjeta", "definicion:medios"),
        ("se me cerro la sesion", "definicion:sesion"),
        ("como empiezo mi turno de trabajo", "ayuda:abrir_guardia"),
        ("quedan aguas?", "stock"),
        ("estado de la ventanilla", "estado"),
        ("el cliente quiere cambiarse de habitacion", "definicion:cambio_habitacion"),
        ("abri un turno por error, como lo borro", "definicion:turno_error"),
        ("puedo hacerle un descuento?", "definicion:descuentos"),
        ("como cambio el color del sistema", "definicion:colores"),
        ("como funciona el pronostico", "definicion:pronostico_metodo"),
        ("llego el pedido del proveedor", "pedidos"),  # los pendientes, con la indicación de «Recibir»
        ("como recibo la mercaderia de un pedido", "ayuda:recibir_pedido"),
    ],
)
async def test_situaciones_frecuentes_del_conserje(client, pregunta, intencion):
    assert (await _preguntar(client, pregunta))["intencion"] == intencion


async def test_temas_de_la_gerencia(cliente_como):
    gerencia = await cliente_como("gerencia")
    for pregunta, intencion in (
        ("como armo un pedido", "ayuda:armar_pedido"),
        ("como exporto los arqueos del mes", "ayuda:exportar_mes"),
        ("como cambio el color del sistema", "ayuda:apariencia"),
        ("como aplico una sugerencia de tarifa", "ayuda:aplicar_sugerencia"),
        ("quiero cambiar el fondo de cambio", "ayuda:config_fondo"),
    ):
        assert (await _preguntar(gerencia, pregunta))["intencion"] == intencion, pregunta


async def test_la_pantalla_abierta(client, cliente_como):
    caja = await _preguntar(client, "¿qué hago acá?", pantalla="caja")
    assert caja["intencion"] == "pantalla:caja" and caja["respuesta"].startswith("Estás en Cierre de caja")
    assert caja["pasos"] and "¿Cómo cierro la caja?" in caja["sugerencias"]
    assert (await _preguntar(client, "para que sirve esta pantalla", pantalla="inventario"))[
        "intencion"
    ] == "pantalla:inventario"
    assert (await _preguntar(client, "ayuda", pantalla="dashboard"))["intencion"] == "pantalla:dashboard"
    # Una sección de la gerencia no se le explica al conserje, y sin pantalla la pregunta sigue su camino.
    assert (await _preguntar(client, "¿qué hago acá?", pantalla="configuracion"))[
        "intencion"
    ] != "pantalla:configuracion"
    assert not (await _preguntar(client, "¿qué hago acá?"))["intencion"].startswith("pantalla:")
    gerencia = await cliente_como("gerencia")
    config = await _preguntar(gerencia, "explicame esta seccion", pantalla="configuracion")
    assert config["intencion"] == "pantalla:configuracion" and "¿Cómo cambio una tarifa?" in config["sugerencias"]
    # Lo que no se entiende propone las preguntas de la sección abierta.
    nada = await _preguntar(client, "xyzzy plugh", pantalla="caja")
    assert "¿Cómo cierro la caja?" in nada["sugerencias"]


async def test_las_preguntas_sugeridas_de_cada_pantalla_tienen_respuesta(db, client, cliente_como):
    await generar_historial(db, dias=28, semilla=4)
    gerencia = await cliente_como("gerencia")
    for vista, pantalla in ayuda.PANTALLAS.items():
        for cliente, preguntas in ((client, pantalla.preguntas), (gerencia, pantalla.preguntas_gerencia)):
            for pregunta in preguntas:
                datos = await _preguntar(cliente, pregunta, pantalla=vista)
                assert datos["intencion"] not in ("desconocida", "fuera_de_alcance"), (vista, pregunta, datos)


async def test_busqueda_por_parecido(client):
    datos = await _preguntar(client, "necesito ayuda con la mercadería que llegó")
    assert datos["intencion"] == "ayuda:inventario", datos
    otra = await _preguntar(client, "el cliente se quejó porque le cobré de más por quedarse un rato")
    assert otra["intencion"].startswith(("ayuda:", "definicion:")), otra
    nada = await _preguntar(client, "xyzzy plugh")
    assert nada["intencion"] == "desconocida" and nada["sugerencias"]


# --- Mot ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pregunta", ["¿Cómo te llamás?", "¿quién es Mot?", "¿cuál es tu nombre?", "¿Quién sos?", "¿sos Mot?"]
)
async def test_mot_dice_quien_es(client, pregunta):
    datos = await _preguntar(client, pregunta)
    assert datos["intencion"] == "charla" and datos["respuesta"].startswith("Soy Mot")


@pytest.mark.parametrize("saludo", ["Mot", "hola Mot", "Hola, Mot!", "che mot"])
async def test_si_solo_lo_llaman_saluda(client, saludo):
    datos = await _preguntar(client, saludo)
    assert datos["intencion"] == "charla" and datos["respuesta"].startswith("¡Hola! Soy Mot")


async def test_el_agradecimiento_con_su_nombre_sigue_siendo_gracias(client):
    assert (await _preguntar(client, "gracias, Mot"))["respuesta"].startswith("¡De nada!")


@pytest.mark.parametrize(
    "pregunta", ["Mot, ¿cuánto sale la simple?", "¿Mot, cuánto sale la simple?", "¿cuánto sale la simple, Mot?"]
)
async def test_su_nombre_no_cambia_la_pregunta(client, pregunta):
    datos = await _preguntar(client, pregunta)
    assert datos["intencion"] == "tarifas" and "Simple: $8.000" in datos["respuesta"]


async def test_una_orden_por_su_nombre_tambien_se_propone(client):
    datos = await _preguntar(client, "Mot, pasá la 2 a mantenimiento")
    assert datos["intencion"] == "accion:estado" and datos["confirmacion"]["estado"] == "Mantenimiento"


async def test_moto_no_es_su_nombre(client):
    datos = await _preguntar(client, "abrí la 2 para una moto")
    assert datos["intencion"] == "accion:abrir_turno" and datos["confirmacion"]["tipo_cliente"] == "Moto"