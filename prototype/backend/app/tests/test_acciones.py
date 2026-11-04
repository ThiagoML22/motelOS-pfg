"""El asistente que actúa: propone, quien atiende confirma, y nada se ejecuta antes de eso."""

import pytest
from sqlalchemy import select

from app.models.habitacion import Habitacion

PREGUNTA = "/api/v1/asistente/pregunta"


async def _decir(cliente, texto: str) -> dict:
    resp = await cliente.post(PREGUNTA, json={"texto": texto})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _estado(db, numero: int) -> str:
    habitacion = (await db.execute(select(Habitacion).where(Habitacion.numero == numero))).scalars().first()
    await db.refresh(habitacion)
    return habitacion.estado


async def test_propone_pero_no_ejecuta(client, db):
    datos = await _decir(client, "pasá la 2 a mantenimiento")
    assert datos["intencion"] == "accion:estado"
    confirmacion = datos["confirmacion"]
    assert confirmacion["tipo"] == "estado" and confirmacion["estado"] == "Mantenimiento"
    assert "la 2" in confirmacion["titulo"] and confirmacion["habitacion_id"] == 2
    assert await _estado(db, 2) == "Libre"


async def test_confirmar_es_llamar_al_servicio_de_siempre(client, db):
    confirmacion = (await _decir(client, "pone la 2 en mantenimiento"))["confirmacion"]
    resp = await client.patch(
        f"/api/v1/habitaciones/{confirmacion['habitacion_id']}/estado", json={"estado": confirmacion["estado"]}
    )
    assert resp.status_code == 200
    assert await _estado(db, 2) == "Mantenimiento"


@pytest.mark.parametrize(
    ("orden", "estado"),
    [
        ("pasa la 2 a mantenimiento", "Mantenimiento"),
        ("por favor poné la habitación 2 fuera de servicio", "Mantenimiento"),
        ("dale, pasá la 2 a limpieza", "En Limpieza"),
        ("mandá la pieza 2 a limpieza", "En Limpieza"),
    ],
)
async def test_las_formas_de_pedir_un_cambio_de_estado(client, orden, estado):
    datos = await _decir(client, orden)
    assert datos["confirmacion"] and datos["confirmacion"]["estado"] == estado, datos


async def test_liberar_y_habilitar(client):
    assert (await _decir(client, "habilitá la 3"))["confirmacion"]["estado"] == "Libre"  # está en mantenimiento
    assert (await _decir(client, "dejá la 3 disponible"))["confirmacion"]["estado"] == "Libre"


async def test_lo_que_ya_se_sabe_que_no_se_puede(client):
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    ocupada = await _decir(client, "pasá la 1 a mantenimiento")
    assert ocupada["confirmacion"] is None and "ocupada" in ocupada["respuesta"]
    assert ocupada["acciones"][0]["habitacion_id"] == 1
    assert (await _decir(client, "pasá la 99 a limpieza"))["confirmacion"] is None
    igual = await _decir(client, "dejá la 2 disponible")
    assert igual["confirmacion"] is None and "ya está" in igual["respuesta"]
    assert turno["id"]


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿cómo paso una habitación a mantenimiento?",
        "como abro un turno",
        "qué es el mantenimiento",
        "¿qué habitaciones están libres?",
        "pasa algo con la 7?",
    ],
)
async def test_las_preguntas_siguen_siendo_preguntas(client, pregunta):
    datos = await _decir(client, pregunta)
    assert datos.get("confirmacion") is None
    assert not datos["intencion"].startswith("accion:"), datos


async def test_abrir_un_turno(client, db):
    datos = await _decir(client, "abrí la 2 para un auto patente ab123cd")
    confirmacion = datos["confirmacion"]
    assert confirmacion["tipo"] == "abrir_turno" and confirmacion["habitacion_id"] == 2
    assert confirmacion["tipo_cliente"] == "Auto" and confirmacion["patente"] == "AB123CD"
    assert await _estado(db, 2) == "Libre"
    moto = (await _decir(client, "abrí la 2 para una moto"))["confirmacion"]
    assert moto["tipo_cliente"] == "Moto" and moto["patente"] is None
    pie = (await _decir(client, "abrí la 2, viene a pie"))["confirmacion"]
    assert pie["tipo_cliente"] == "Peaton"
    alguna = (await _decir(client, "abrí una habitación"))["confirmacion"]
    assert alguna["tipo"] == "abrir_turno"


async def test_abrir_un_turno_sin_guardia_o_ocupada(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    sin_guardia = await _decir(gerencia, "abrí la 2")
    assert sin_guardia["confirmacion"] is None and "guardia" in sin_guardia["respuesta"]
    await client.post("/api/v1/turnos/", json={"habitacion_id": 2, "tipo_cliente": "Auto"})
    assert (await _decir(client, "abrí la 2"))["confirmacion"] is None


async def test_cargar_un_consumo(client):
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    datos = await _decir(client, "cargale dos aguas a la 1")
    confirmacion = datos["confirmacion"]
    assert confirmacion["tipo"] == "consumo", datos
    assert (
        confirmacion["turno_id"] == turno["id"] and confirmacion["articulo_id"] == 1 and confirmacion["cantidad"] == 2
    )
    assert "1.600" in datos["detalle"]
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()["total_consumos"] == 0
    resp = await client.post(
        f"/api/v1/turnos/{confirmacion['turno_id']}/consumos",
        json={"articulo_id": confirmacion["articulo_id"], "cantidad": confirmacion["cantidad"]},
    )
    assert resp.status_code == 201


async def test_un_consumo_que_no_se_puede(client):
    await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})
    assert "inventario" in (await _decir(client, "cargale un helicóptero a la 1"))["respuesta"]
    assert "no tiene un turno" in (await _decir(client, "cargale un agua a la 2"))["respuesta"]
    assert "Quedan" in (await _decir(client, "cargale 50 aguas a la 1"))["respuesta"]


async def test_dejar_una_novedad_con_el_texto_tal_cual(client):
    datos = await _decir(client, "Dejá una novedad: falta papel en la 2")
    confirmacion = datos["confirmacion"]
    assert confirmacion["tipo"] == "novedad" and confirmacion["texto"] == "falta papel en la 2"
    assert confirmacion["habitacion_id"] == 2 and confirmacion["importante"] is False
    importante = await _decir(client, "anotá una novedad importante: se cortó el agua")
    assert importante["confirmacion"]["importante"] is True
    assert "qué querés dejar" in (await _decir(client, "dejá una novedad"))["respuesta"]


async def test_registrar_un_cliente_perdido(client, cliente_como):
    datos = await _decir(client, "registrá un cliente perdido, no quiso esperar")
    assert datos["confirmacion"]["tipo"] == "cliente_perdido" and datos["confirmacion"]["motivo"] == "ESPERA"
    caro = await _decir(client, "anotá que se fue un cliente, le pareció caro")
    assert caro["confirmacion"]["motivo"] == "PRECIO"
    gerencia = await cliente_como("gerencia")
    assert (await _decir(gerencia, "registrá un cliente perdido"))["confirmacion"] is None


async def test_el_cobro_no_lo_hace_el_asistente(client):
    await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})
    datos = await _decir(client, "cobrale a la 1")
    assert datos["confirmacion"] is None and "no lo hago yo" in datos["respuesta"]
    assert datos["acciones"][0]["habitacion_id"] == 1


async def test_la_ayuda_conoce_lo_nuevo(client):
    assert (await _decir(client, "¿qué es el ticket con qr?"))["intencion"] == "definicion:ticket_cliente"
    assert (await _decir(client, "como le doy el ticket al cliente"))["intencion"] == "ayuda:imprimir_ticket"
    assert (await _decir(client, "como atiendo un pedido del cliente"))["intencion"] == "ayuda:atender_pedido"
