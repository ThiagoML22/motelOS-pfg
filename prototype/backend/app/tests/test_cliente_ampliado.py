"""La página del cliente ampliada (migración 015): carrito, pedido en camino, avisos con dato, Mot y calificación."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.articulo import Articulo
from app.models.calificacion import Calificacion
from app.models.pedido_cliente import PedidoCliente
from app.models.turno import Turno
from app.services import inteligencia as ia
from app.services import rotacion
from scripts.cargar_historial import agregar_opiniones, generar_historial

COBRO = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
CONFIG = "/api/v1/configuracion"


async def _turno(cliente, habitacion_id: int = 1, **extra) -> dict:
    resp = await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, "tipo_cliente": "Auto", **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _enlace(cliente, turno: dict) -> str:
    resp = await cliente.get(f"/api/v1/turnos/{turno['id']}/ticket")
    assert resp.status_code == 200, resp.text
    return "/api/v1/cliente/" + resp.json()["direccion"].split("cliente=")[1]


async def _con_stock(db) -> list[int]:
    articulos = list((await db.execute(select(Articulo).order_by(Articulo.id))).scalars())
    for articulo in articulos:
        articulo.stock_actual = 10
    await db.commit()
    return [a.id for a in articulos]


@pytest.mark.parametrize(
    ("ruta", "cuerpo"),
    [
        ("carrito", {"lineas": [{"articulo_id": 1, "cantidad": 1}]}),
        ("calificacion", {"puntaje": 5}),
    ],
)
async def test_enlaces_inventados_en_las_rutas_nuevas(anonimo, ruta, cuerpo):
    for token in ("nada", f"1.{uuid.uuid4().hex}.firmafalsa"):
        assert (await anonimo.post(f"/api/v1/cliente/{token}/{ruta}", json=cuerpo)).status_code == 404


# --- Carrito --------------------------------------------------------------------------------------------------------


async def test_un_carrito_es_un_solo_pedido(client, anonimo, db):
    uno, dos = await _con_stock(db)
    enlace = await _enlace(client, await _turno(client))
    lineas = [{"articulo_id": uno, "cantidad": 2}, {"articulo_id": dos, "cantidad": 1}]
    resp = await anonimo.post(f"{enlace}/carrito", json={"lineas": lineas})
    assert resp.status_code == 201, resp.text

    filas = list((await db.execute(select(PedidoCliente))).scalars())
    assert len(filas) == 2 and filas[0].lote is not None and filas[0].lote == filas[1].lote
    pedidos = (await anonimo.get(enlace)).json()["pedidos"]
    assert {p["lote"] for p in pedidos} == {str(filas[0].lote)}
    # No toca el stock ni la cuenta.
    assert (await anonimo.get(enlace)).json()["total"] == 8000


async def test_cuatro_articulos_distintos_entran_de_una(client, anonimo, db):
    """Con un pedido por artículo, el límite de pendientes cortaba un carrito por la mitad."""
    for numero in range(4):
        db.add(Articulo(codigo=f"X-{numero}", descripcion=f"Extra {numero}", precio_unitario=100, stock_actual=9))
    await db.commit()
    ids = await _con_stock(db)
    enlace = await _enlace(client, await _turno(client))
    resp = await anonimo.post(f"{enlace}/carrito", json={"lineas": [{"articulo_id": i, "cantidad": 1} for i in ids]})
    assert resp.status_code == 201, resp.text
    # Cuenta como uno: quedan lugares para otros dos pedidos.
    assert (await anonimo.post(f"{enlace}/pedidos", json={"tipo": "TOALLAS"})).status_code == 201
    assert (await anonimo.post(f"{enlace}/pedidos", json={"tipo": "LLAMAR"})).status_code == 201
    assert (await anonimo.post(f"{enlace}/pedidos", json={"tipo": "SALIDA"})).status_code == 429


async def test_el_carrito_entra_completo_o_no_entra(client, anonimo, db):
    uno, dos = await _con_stock(db)
    articulo = await db.get(Articulo, dos)
    articulo.stock_actual = 1
    await db.commit()
    enlace = await _enlace(client, await _turno(client))
    lineas = [{"articulo_id": uno, "cantidad": 1}, {"articulo_id": dos, "cantidad": 2}]
    resp = await anonimo.post(f"{enlace}/carrito", json={"lineas": lineas})
    assert resp.status_code == 409 and articulo.descripcion in resp.json()["detail"]
    assert (await db.execute(select(PedidoCliente))).scalars().first() is None


async def test_el_mismo_articulo_repetido_se_junta(client, anonimo, db):
    uno, _ = await _con_stock(db)
    enlace = await _enlace(client, await _turno(client))
    lineas = [{"articulo_id": uno, "cantidad": 2}, {"articulo_id": uno, "cantidad": 2}]
    assert (await anonimo.post(f"{enlace}/carrito", json={"lineas": lineas})).status_code == 201
    fila = (await db.execute(select(PedidoCliente))).scalars().one()
    assert fila.cantidad == 4
    # Junto no puede pasar del máximo por artículo.
    enlace_dos = await _enlace(client, await _turno(client, 2))
    lineas = [{"articulo_id": uno, "cantidad": 3}, {"articulo_id": uno, "cantidad": 3}]
    assert (await anonimo.post(f"{enlace_dos}/carrito", json={"lineas": lineas})).status_code == 422


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"lineas": []},
        {"lineas": [{"articulo_id": 1, "cantidad": 0}]},
        {"lineas": [{"articulo_id": 1, "cantidad": 6}]},
        {"lineas": [{"articulo_id": 1, "cantidad": 1}] * 9},
    ],
)
async def test_carritos_invalidos(client, anonimo, cuerpo):
    enlace = await _enlace(client, await _turno(client))
    assert (await anonimo.post(f"{enlace}/carrito", json=cuerpo)).status_code == 422


async def test_un_turno_cerrado_no_recibe_carritos(client, anonimo):
    turno = await _turno(client)
    enlace = await _enlace(client, turno)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    resp = await anonimo.post(f"{enlace}/carrito", json={"lineas": [{"articulo_id": 1, "cantidad": 1}]})
    assert resp.status_code == 409


# --- En camino -------------------------------------------------------------------------------------------------------


async def test_el_pedido_recorre_su_camino(client, anonimo, db):
    uno, _ = await _con_stock(db)
    enlace = await _enlace(client, await _turno(client))
    await anonimo.post(f"{enlace}/carrito", json={"lineas": [{"articulo_id": uno, "cantidad": 1}]})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]
    assert pedido["estado"] == "Pendiente" and pedido["lote"]

    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido['id']}/llevar")).status_code == 200
    assert (await anonimo.get(enlace)).json()["pedidos"][0]["estado"] == "En camino"
    # Sigue a la vista de la ventanilla, y todavía no se cargó.
    assert (await client.get("/api/v1/pedidos-cliente/")).json()[0]["estado"] == "En camino"
    assert (await anonimo.get(enlace)).json()["total"] == 8000
    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido['id']}/llevar")).status_code == 409

    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido['id']}/atender")).status_code == 200
    datos = (await anonimo.get(enlace)).json()
    assert datos["pedidos"][0]["estado"] == "Atendido" and datos["total"] == 8800
    assert (await client.get("/api/v1/pedidos-cliente/")).json() == []
    fila = (await db.execute(select(PedidoCliente))).scalars().one()
    assert fila.llevado_por_id == fila.atendido_por_id is not None


async def test_lo_que_iba_en_camino_tambien_se_puede_rechazar(client, anonimo, db):
    uno, _ = await _con_stock(db)
    enlace = await _enlace(client, await _turno(client))
    await anonimo.post(f"{enlace}/pedidos", json={"tipo": "ARTICULO", "articulo_id": uno, "cantidad": 1})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    await client.post(f"/api/v1/pedidos-cliente/{pedido}/llevar")
    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido}/rechazar")).status_code == 200
    assert (await anonimo.get(enlace)).json()["pedidos"][0]["estado"] == "Rechazado"


async def test_un_aviso_no_se_lleva(client, anonimo):
    enlace = await _enlace(client, await _turno(client))
    await anonimo.post(f"{enlace}/pedidos", json={"tipo": "TOALLAS"})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido}/llevar")).status_code == 409


async def test_llevar_exige_la_guardia_propia(client, anonimo, db, cliente_como):
    uno, _ = await _con_stock(db)
    enlace = await _enlace(client, await _turno(client))
    await anonimo.post(f"{enlace}/pedidos", json={"tipo": "ARTICULO", "articulo_id": uno, "cantidad": 1})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(f"/api/v1/pedidos-cliente/{pedido}/llevar")).status_code == 409


async def test_llevar_necesita_sesion(anonimo):
    assert (await anonimo.post("/api/v1/pedidos-cliente/1/llevar")).status_code == 401


# --- Quedarse más y pedir la cuenta ------------------------------------------------------------------------------


async def test_cuanto_costaria_quedarse_mas(client, anonimo):
    datos = (await anonimo.get(await _enlace(client, await _turno(client)))).json()
    opciones = {o["minutos"]: o["suma"] for o in datos["opciones_tiempo"]}
    # Fracción de 30 min a $2.500, contando desde el fin de la estadía base.
    assert opciones == {30: 2500, 60: 5000, 120: 10000}
    inicio = datetime.fromisoformat(datos["hora_inicio"])
    hasta = datetime.fromisoformat(datos["opciones_tiempo"][0]["hasta"])
    assert round((hasta - inicio).total_seconds() / 60) == 150


async def test_pasada_la_base_se_cuenta_desde_ahora(client, anonimo, db):
    turno = await _turno(client)
    fila = await db.get(Turno, uuid.UUID(turno["id"]))
    fila.hora_inicio = datetime.now(UTC) - timedelta(minutes=170)
    await db.commit()
    datos = (await anonimo.get(await _enlace(client, turno))).json()
    # A los 170 min ya van 2 fracciones; a los 200 se llega a 3: suma una.
    assert datos["total_sobreturno"] == 5000
    assert {o["minutos"]: o["suma"] for o in datos["opciones_tiempo"]}[30] == 2500


async def test_avisar_que_se_queda_no_cobra_nada(client, anonimo):
    enlace = await _enlace(client, await _turno(client))
    assert (await anonimo.post(f"{enlace}/pedidos", json={"tipo": "TIEMPO", "minutos": 60})).status_code == 201
    datos = (await anonimo.get(enlace)).json()
    assert datos["total"] == 8000 and datos["pedidos"][0]["descripcion"] == "Se queda 1 h más"
    ventanilla = (await client.get("/api/v1/pedidos-cliente/")).json()[0]
    assert ventanilla["tipo"] == "TIEMPO" and ventanilla["descripcion"] == "Se queda 1 h más"


@pytest.mark.parametrize("minutos", [None, 0, 45, 500])
async def test_solo_se_elige_entre_las_opciones(client, anonimo, minutos):
    enlace = await _enlace(client, await _turno(client))
    assert (await anonimo.post(f"{enlace}/pedidos", json={"tipo": "TIEMPO", "minutos": minutos})).status_code == 422


async def test_pedir_la_cuenta_le_avisa_a_la_ventanilla_como_paga(client, anonimo):
    enlace = await _enlace(client, await _turno(client))
    resp = await anonimo.post(f"{enlace}/pedidos", json={"tipo": "SALIDA", "medio_pago": "MERCADO_PAGO"})
    assert resp.status_code == 201, resp.text
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]
    assert pedido["medio_pago"] == "MERCADO_PAGO" and pedido["descripcion"] == "Pide la cuenta: paga con mercado pago"
    assert (await anonimo.get(enlace)).json()["total"] == 8000


async def test_un_medio_de_pago_inventado_no_entra(client, anonimo):
    enlace = await _enlace(client, await _turno(client))
    assert (await anonimo.post(f"{enlace}/pedidos", json={"tipo": "SALIDA", "medio_pago": "CHEQUE"})).status_code == 422


async def test_los_datos_de_mas_de_un_aviso_no_se_guardan(client, anonimo, db):
    enlace = await _enlace(client, await _turno(client))
    cuerpo = {"tipo": "TOALLAS", "minutos": 30, "medio_pago": "EFECTIVO"}
    assert (await anonimo.post(f"{enlace}/pedidos", json=cuerpo)).status_code == 201
    fila = (await db.execute(select(PedidoCliente))).scalars().one()
    assert fila.minutos is None and fila.medio_pago is None


async def test_la_pagina_solo_ofrece_los_avisos_directos(client, anonimo):
    datos = (await anonimo.get(await _enlace(client, await _turno(client)))).json()
    assert [a["tipo"] for a in datos["avisos"]] == ["TOALLAS", "LLAMAR"]
    assert [m["medio"] for m in datos["medios_pago"]] == ["EFECTIVO", "POSNET", "MERCADO_PAGO"]


async def test_lo_que_avisa_el_cliente_mejora_la_proxima_libre(client, anonimo, db):
    uno = await _turno(client, 1)
    dos = await _turno(client, 2)
    await anonimo.post(f"{await _enlace(client, uno)}/pedidos", json={"tipo": "SALIDA"})
    await anonimo.post(f"{await _enlace(client, dos)}/pedidos", json={"tipo": "TIEMPO", "minutos": 120})
    datos = await rotacion.proxima_libre(db)
    por_numero = {p["numero"]: p for p in datos["proximas"]}
    limpieza = datos["limpieza_min"]
    assert por_numero[1]["aviso"] == "SALIDA" and por_numero[1]["minutos"] == 8 + limpieza
    assert por_numero[2]["aviso"] == "TIEMPO"
    # 120 de estadía base más 120 avisados, menos lo poco que lleva.
    assert abs(por_numero[2]["minutos"] - (240 + limpieza)) <= 1
    assert datos["proximas"][0]["numero"] == 1


async def test_un_aviso_rechazado_no_cuenta_para_la_proxima_libre(client, anonimo, db):
    enlace = await _enlace(client, await _turno(client, 1))
    await anonimo.post(f"{enlace}/pedidos", json={"tipo": "SALIDA"})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    await client.post(f"/api/v1/pedidos-cliente/{pedido}/rechazar")
    assert (await rotacion.proxima_libre(db))["proximas"][0]["aviso"] is None


async def test_un_aviso_atendido_sigue_contando(client, anonimo, db):
    enlace = await _enlace(client, await _turno(client, 1))
    await anonimo.post(f"{enlace}/pedidos", json={"tipo": "TIEMPO", "minutos": 60})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    await client.post(f"/api/v1/pedidos-cliente/{pedido}/atender")
    assert (await rotacion.proxima_libre(db))["proximas"][0]["aviso"] == "TIEMPO"


# --- Mot ---------------------------------------------------------------------------------------------------------


async def _gerencia_con_wifi(cliente_como):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.patch(
        f"{CONFIG}/establecimiento",
        json={"wifi_nombre": "Motel-Invitados", "wifi_clave": "clave123", "bienvenida": "Hola, bienvenidos."},
    )
    assert resp.status_code == 200, resp.text
    return gerencia


async def test_mot_responde_con_los_datos_de_la_estadia(client, anonimo, cliente_como):
    await _gerencia_con_wifi(cliente_como)
    datos = (await anonimo.get(await _enlace(client, await _turno(client)))).json()
    respuestas = {r["id"]: r["respuesta"] for r in datos["mot"]}
    assert datos["bienvenida"] == "Hola, bienvenidos."
    assert "Motel-Invitados" in respuestas["wifi"] and "clave123" in respuestas["wifi"]
    assert "llega hasta las" in respuestas["salida"] and "2 h" in respuestas["salida"]
    assert "$ 8.000" in respuestas["gasto"]
    assert all(r["pregunta"].startswith("¿") for r in datos["mot"])


async def test_sin_wifi_cargado_mot_no_lo_ofrece(client, anonimo):
    datos = (await anonimo.get(await _enlace(client, await _turno(client)))).json()
    assert "wifi" not in {r["id"] for r in datos["mot"]}


async def test_la_clave_del_wifi_solo_la_ve_quien_tiene_el_enlace_activo(client, anonimo, cliente_como):
    await _gerencia_con_wifi(cliente_como)
    turno = await _turno(client)
    enlace = await _enlace(client, turno)
    assert "clave123" in (await anonimo.get(enlace)).text
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    assert "clave123" not in (await anonimo.get(enlace)).text


async def test_el_cambio_del_wifi_queda_en_la_actividad(cliente_como):
    gerencia = await _gerencia_con_wifi(cliente_como)
    entradas = (await gerencia.get(f"{CONFIG}/actividad")).json()
    assert any("Wi-Fi" in e["descripcion"] for e in entradas)


# --- Calificación --------------------------------------------------------------------------------------------------


async def test_se_califica_una_sola_vez_sin_datos_de_la_persona(client, anonimo, db):
    turno = await _turno(client, identificador_vehicular="AA111AA")
    enlace = await _enlace(client, turno)
    assert (await anonimo.get(enlace)).json()["calificada"] is False
    resp = await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 2, "problemas": 1 | 4})
    assert resp.status_code == 201, resp.text
    assert (await anonimo.get(enlace)).json()["calificada"] is True
    assert (await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 5})).status_code == 409
    fila = (await db.execute(select(Calificacion))).scalars().one()
    assert (fila.puntaje, fila.problemas, fila.habitacion_id) == (2, 5, 1)
    assert not {"nombre", "patente", "texto", "comentario"} & set(Calificacion.__table__.columns.keys())


async def test_al_cobrar_todavia_se_puede_calificar(client, anonimo):
    turno = await _turno(client)
    enlace = await _enlace(client, turno)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    datos = (await anonimo.get(enlace)).json()
    assert datos["activa"] is False and datos["puede_calificar"] is True and len(datos["problemas"]) == 6
    assert (await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 4})).status_code == 201
    assert (await anonimo.get(enlace)).json()["puede_calificar"] is False


async def test_pasada_la_hora_ya_no_se_califica(client, anonimo, db):
    turno = await _turno(client)
    enlace = await _enlace(client, turno)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    fila = (await db.execute(select(Turno))).scalars().one()
    await db.refresh(fila)
    fila.hora_fin = datetime.now(UTC) - timedelta(minutes=61)
    await db.commit()
    assert (await anonimo.get(enlace)).json()["puede_calificar"] is False
    assert (await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 4})).status_code == 409


@pytest.mark.parametrize(
    "cuerpo", [{"puntaje": 0}, {"puntaje": 6}, {"puntaje": 3, "problemas": 64}, {"puntaje": 3, "problemas": -1}, {}]
)
async def test_calificaciones_invalidas(client, anonimo, cuerpo):
    enlace = await _enlace(client, await _turno(client))
    assert (await anonimo.post(f"{enlace}/calificacion", json=cuerpo)).status_code == 422


async def test_la_ventanilla_no_ve_lo_que_opinan(client):
    assert (await client.get("/api/v1/inteligencia/tablero")).status_code == 403


# --- La gerencia -------------------------------------------------------------------------------------------------


async def test_la_gerencia_ve_totales_y_nunca_una_opinion_suelta(db, cliente_como):
    await generar_historial(db, dias=42, semilla=3, intensidad=2.0, habitacion_poco_usada=2)
    cantidad = await agregar_opiniones(db, 3, 2)
    await db.commit()
    assert cantidad > 0

    gerencia = await cliente_como("gerencia")
    datos = (await gerencia.get("/api/v1/inteligencia/tablero")).json()
    opiniones = datos["opiniones"]
    assert opiniones["cantidad"] > 0 and 1 <= opiniones["promedio"] <= 5
    assert sum(p["cantidad"] for p in opiniones["puntajes"]) == opiniones["cantidad"]
    # Ni turnos ni horas: solo totales.
    assert "turno" not in str(opiniones).replace("turnos", "") and "momento" not in str(opiniones)
    peor = opiniones["habitaciones"][0]
    assert peor["numero"] == 2 and peor["problema"] == "Aire o calefacción"
    assert any("Aire o calefacción" in a["titulo"] for a in datos["alertas"])


async def test_una_sola_opinion_no_marca_a_una_habitacion(client, anonimo, cliente_como, db):
    enlace = await _enlace(client, await _turno(client))
    await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 1, "problemas": 1})
    gerencia = await cliente_como("gerencia")
    datos = (await gerencia.get("/api/v1/inteligencia/tablero")).json()
    assert datos["opiniones"]["cantidad"] == 1 and datos["opiniones"]["habitaciones"] == []


async def test_sin_opiniones_el_tablero_no_se_rompe(cliente_como):
    gerencia = await cliente_como("gerencia")
    datos = (await gerencia.get("/api/v1/inteligencia/tablero")).json()
    assert datos["opiniones"]["cantidad"] == 0 and datos["opiniones"]["promedio"] is None


async def test_mot_le_cuenta_a_la_gerencia_y_no_al_conserje(client, anonimo, cliente_como):
    enlace = await _enlace(client, await _turno(client))
    await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 3, "problemas": 2})
    gerencia = await cliente_como("gerencia")
    datos = (await gerencia.post("/api/v1/asistente/pregunta", json={"texto": "¿qué dicen los clientes?"})).json()
    assert datos["intencion"] == "opiniones" and "3 de 5" in datos["respuesta"].replace(",0", "")
    assert "ruido" in datos["respuesta"]
    conserje = (await client.post("/api/v1/asistente/pregunta", json={"texto": "¿qué dicen los clientes?"})).json()
    assert conserje["intencion"] == "fuera_de_alcance"


def test_problemas_de_una_mascara():
    assert ia.problemas_de(1 | 4) == ["Limpieza", "Aire o calefacción"]
    assert ia.problemas_de(0) == []
