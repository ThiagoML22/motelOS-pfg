"""Historial de estados, clientes perdidos, próxima libre, línea de tiempo y lo que el análisis y el asistente hacen con
ellos (migración 011)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.cliente_perdido import ClientePerdido
from app.models.evento_habitacion import EventoHabitacion
from app.services.rotacion import estimar_restante, tramos_en_estado
from scripts.cargar_historial import generar_historial

PREGUNTA = "/api/v1/asistente/pregunta"
COBRO = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}


async def _abrir(cliente, habitacion_id: int = 1, **extra) -> dict:
    resp = await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, "tipo_cliente": "Auto", **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _cobrar(cliente, turno: dict) -> None:
    resp = await cliente.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    assert resp.status_code == 200, resp.text


async def _eventos(db, habitacion_id: int) -> list[EventoHabitacion]:
    consulta = (
        select(EventoHabitacion).where(EventoHabitacion.habitacion_id == habitacion_id).order_by(EventoHabitacion.id)
    )
    return list((await db.execute(consulta)).scalars())


async def _preguntar(cliente, texto: str, **extra) -> dict:
    resp = await cliente.post(PREGUNTA, json={"texto": texto, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_cada_cambio_de_estado_queda_en_el_historial(client, db):
    turno = await _abrir(client)
    await _cobrar(client, turno)
    assert (await client.patch("/api/v1/habitaciones/1/liberar")).status_code == 200
    eventos = await _eventos(db, 1)
    assert [(e.estado_anterior, e.estado_nuevo, e.origen) for e in eventos] == [
        ("Libre", "Ocupada", "TURNO"),
        ("Ocupada", "En Limpieza", "COBRO"),
        ("En Limpieza", "Libre", "LIBERAR"),
    ]
    assert str(eventos[0].turno_id) == turno["id"] and str(eventos[1].turno_id) == turno["id"]
    assert eventos[2].turno_id is None and len({e.operador_id for e in eventos}) == 1


async def test_liberar_con_el_cambio_de_estado_tambien_es_liberar(client, db):
    await _cobrar(client, await _abrir(client))
    resp = await client.patch("/api/v1/habitaciones/1/estado", json={"estado": "Libre"})
    assert resp.status_code == 200
    assert (await _eventos(db, 1))[-1].origen == "LIBERAR"


async def test_los_cambios_a_mano_quedan_en_el_historial_y_en_actividad(client, cliente_como, db):
    assert (await client.patch("/api/v1/habitaciones/2/estado", json={"estado": "Mantenimiento"})).status_code == 200
    assert (await client.patch("/api/v1/habitaciones/2/estado", json={"estado": "Mantenimiento"})).status_code == 200
    eventos = await _eventos(db, 2)
    assert [(e.estado_nuevo, e.origen) for e in eventos] == [("Mantenimiento", "MANUAL")]  # sin cambio, sin evento
    gerencia = await cliente_como("gerencia")
    actividad = (await gerencia.get("/api/v1/configuracion/actividad")).json()
    entradas = [a for a in actividad if a["categoria"] == "HABITACION"]
    assert len(entradas) == 1 and "pasó de Libre a Mantenimiento" in entradas[0]["descripcion"]
    assert entradas[0]["requiere_revision"] is True


def test_estimar_restante_mira_solo_las_estadias_que_llegaron_hasta_ahi():
    duraciones = [30.0] * 50 + [float(m) for m in range(100, 140)]
    temprano, tipico, tarde = estimar_restante(duraciones, 90, 120)
    assert temprano < tipico < tarde
    # Las estadías de 30 minutos ya no cuentan: a los que pasaron de 90 les faltaban entre 10 y 49.
    assert 10 <= temprano and tarde <= 49 and tipico == pytest.approx(30, abs=1)


def test_estimar_restante_con_pocos_datos_usa_la_estadia_base():
    assert estimar_restante([], 30, 120) == pytest.approx((63, 90, 126))
    # Ya pasada la estadía base, sin nada parecido en la historia: un margen, nunca un número negativo.
    assert estimar_restante([60.0, 70.0], 500, 120)[1] == 15


def test_tramos_de_una_habitacion_y_el_ultimo_abierto():
    momento = datetime(2026, 11, 1, 10, tzinfo=UTC)
    fila = lambda hab, antes, nuevo, minutos, origen="COBRO": EventoHabitacion(  # noqa: E731
        habitacion_id=hab,
        estado_anterior=antes,
        estado_nuevo=nuevo,
        origen=origen,
        operador_id=1,
        creado_en=momento + timedelta(minutes=minutos),
    )
    eventos = [
        fila(1, "Ocupada", "En Limpieza", 0),
        fila(1, "En Limpieza", "Libre", 25, "LIBERAR"),
        fila(1, "Libre", "En Limpieza", 60, "MANUAL"),
        fila(2, "Ocupada", "En Limpieza", 5),
    ]
    primero, sin_turno, abierto = tramos_en_estado(eventos, "En Limpieza")
    assert primero.minutos == 25 and primero.tras_un_turno
    assert sin_turno.fin is None and not sin_turno.tras_un_turno
    assert abierto.habitacion_id == 2 and abierto.minutos is None


async def test_proxima_libre_ordena_por_lo_que_falta(db, client):
    await generar_historial(db, dias=28, semilla=4)
    turno = await _abrir(client, 1)
    await _abrir(client, 2)
    await _cobrar(client, turno)
    datos = (await client.get("/api/v1/habitaciones/proxima-libre")).json()
    assert datos["disponibles"] == 0 and 18 <= datos["limpieza_min"] <= 40
    primera, segunda = datos["proximas"]
    # La 1 está en limpieza: se libera antes que la 2, que recién empieza su turno y después necesita limpieza.
    assert primera["numero"] == 1 and primera["estado"] == "En Limpieza"
    assert primera["minutos"] <= datos["limpieza_min"]
    assert segunda["numero"] == 2 and segunda["estado"] == "Ocupada" and segunda["minutos"] > datos["limpieza_min"]
    assert segunda["minimo"] <= segunda["minutos"] <= segunda["maximo"]
    assert datos["categorias"][0]["disponibles"] == 0 and datos["categorias"][0]["proxima_min"] == primera["minutos"]


async def test_linea_de_tiempo_con_los_tramos_y_sin_datos_del_cliente(client, cliente_como):
    turno = await _abrir(client, 1, identificador_vehicular="AB123CD")
    await _cobrar(client, turno)
    await _abrir(client, 2)
    assert (await client.patch("/api/v1/habitaciones/1/estado", json={"estado": "Mantenimiento"})).status_code == 200
    gerencia = await cliente_como("gerencia")
    for cliente in (client, gerencia):
        resp = await cliente.get("/api/v1/habitaciones/linea-de-tiempo")
        assert resp.status_code == 200
        assert "AB123CD" not in resp.text and "8000" not in resp.text
    datos = resp.json()
    por_numero = {f["numero"]: f for f in datos["habitaciones"]}
    assert [t["tipo"] for t in por_numero[1]["tramos"]][:1] == ["ocupada"]
    assert {t["tipo"] for t in por_numero[1]["tramos"]} >= {"ocupada", "mantenimiento"}
    en_curso = por_numero[2]["tramos"][0]
    assert en_curso["tipo"] == "ocupada" and en_curso["en_curso"] is True
    assert datos["resumen"]["turnos"] == 2


async def test_linea_de_tiempo_de_un_dia_pasado(db, client):
    await generar_historial(db, dias=7, semilla=4)
    ayer = date.today() - timedelta(days=2)
    datos = (await client.get("/api/v1/habitaciones/linea-de-tiempo", params={"dia": ayer.isoformat()})).json()
    tramos = [t for f in datos["habitaciones"] for t in f["tramos"]]
    assert {"ocupada", "limpieza"} <= {t["tipo"] for t in tramos}
    assert all(not t["en_curso"] for t in tramos)
    assert all(datos["desde"] <= t["desde"] and t["hasta"] <= datos["hasta"] for t in tramos)
    assert 0 < datos["resumen"]["ocupacion"] <= 1 and datos["resumen"]["limpieza_min"]


async def test_clientes_perdidos_los_registra_quien_atiende(client, cliente_como, db):
    primero = await client.post("/api/v1/clientes-perdidos/", json={"motivo": "SIN_LUGAR", "categoria_id": 1})
    assert primero.status_code == 201 and primero.json() == {"en_la_guardia": 1}
    segundo = await client.post("/api/v1/clientes-perdidos/", json={"motivo": "PRECIO"})
    assert segundo.json() == {"en_la_guardia": 2}
    assert (await client.post("/api/v1/clientes-perdidos/", json={"motivo": "OTRO"})).status_code == 422
    resp = await client.post("/api/v1/clientes-perdidos/", json={"categoria_id": 999})
    assert resp.status_code == 404
    # Sin guardia propia no se registra: ni la gerencia ni otro conserje.
    for usuario in ("gerencia", "conserje2"):
        ajeno = await cliente_como(usuario)
        assert (await ajeno.post("/api/v1/clientes-perdidos/", json={})).status_code == 409
    filas = list((await db.execute(select(ClientePerdido).order_by(ClientePerdido.id))).scalars())
    assert [f.motivo for f in filas] == ["SIN_LUGAR", "PRECIO"]
    assert all(f.operador_id == filas[0].operador_id and f.guardia_id for f in filas)


async def test_el_tablero_analiza_clientes_perdidos_y_limpiezas(db, cliente_como):
    historial = await generar_historial(db, dias=42, semilla=3, intensidad=2.5)
    assert historial["registrados"] > 0
    gerencia = await cliente_como("gerencia")
    tablero = (await gerencia.get("/api/v1/inteligencia/tablero")).json()
    perdidos = tablero["clientes_perdidos"]
    assert perdidos["total"] > 0 and perdidos["valor_estimado"] > 0 and 0 < perdidos["parte"] < 1
    assert sum(m["cantidad"] for m in perdidos["motivos"]) == perdidos["total"]
    assert sum(h["cantidad"] for h in perdidos["horas"]) == perdidos["total"]
    assert perdidos["franja"]["cantidad"] <= perdidos["total"]
    rotacion = tablero["rotacion"]
    assert 18 <= rotacion["mediana"] <= 40 and rotacion["p90"] >= rotacion["mediana"]
    assert rotacion["por_franja"] and rotacion["sin_turno"] > 0
    titulos = [a["titulo"] for a in tablero["alertas"]]
    assert any("limpiezas sin un turno" in t for t in titulos), titulos
    assert any(p for p in tablero["resumen"]["puntos"] if "se fueron" in p["texto"])


async def test_sin_datos_nuevos_el_tablero_sigue_funcionando(cliente_como):
    gerencia = await cliente_como("gerencia")
    tablero = (await gerencia.get("/api/v1/inteligencia/tablero")).json()
    assert tablero["clientes_perdidos"]["total"] == 0 and tablero["clientes_perdidos"]["franja"] is None
    assert tablero["rotacion"]["mediana"] is None


async def test_el_asistente_responde_sobre_la_rotacion(db, client, cliente_como):
    await generar_historial(db, dias=28, semilla=4)
    await _abrir(client, 1)
    proxima = await _preguntar(client, "¿cuándo se libera la próxima?")
    assert proxima["intencion"] == "proxima" and "la 2" not in proxima["respuesta"].split(".")[0]
    assert "Ahora hay 1 disponible." in proxima["respuesta"] and "estimación" in proxima["detalle"]
    assert (await _preguntar(client, "cuanto falta para que se libere la 1"))["intencion"] == "proxima"
    assert (await _preguntar(client, "¿cuánto tarda la limpieza?"))["intencion"] == "limpieza"
    assert (await _preguntar(client, "se fue un cliente, qué hago"))["intencion"] == "ayuda:cliente_perdido"
    assert (await _preguntar(client, "¿qué es un cliente perdido?"))["intencion"] == "definicion:cliente_perdido"
    assert (await _preguntar(client, "como veo la linea de tiempo"))["intencion"] == "ayuda:linea_tiempo"
    assert (await _preguntar(client, "¿cuántos clientes perdimos?"))["intencion"] == "fuera_de_alcance"
    gerencia = await cliente_como("gerencia")
    assert (await _preguntar(gerencia, "¿cuántos clientes perdimos el mes pasado?"))["intencion"] == "perdidos"
    assert (await _preguntar(gerencia, "¿qué es una limpieza sin turno?"))[
        "intencion"
    ] == "definicion:limpieza_sin_turno"
