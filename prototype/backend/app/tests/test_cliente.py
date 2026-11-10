"""El cliente en su habitación: el enlace del ticket, su estadía y sus pedidos, y cómo los atiende la ventanilla."""

import uuid

from sqlalchemy import select

from app.models.articulo import Articulo
from app.models.pedido_cliente import PedidoCliente
from app.services import acceso_cliente

COBRO = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}


async def _turno(cliente, habitacion_id: int = 1, **extra) -> dict:
    resp = await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, "tipo_cliente": "Auto", **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _enlace(cliente, turno: dict) -> str:
    """El token del enlace, sacado del ticket como lo recibe la ventanilla."""
    resp = await cliente.get(f"/api/v1/turnos/{turno['id']}/ticket")
    assert resp.status_code == 200, resp.text
    return resp.json()["direccion"].split("cliente=")[1]


def test_el_enlace_esta_firmado():
    turno = uuid.uuid4()
    token = acceso_cliente.token_de(1, turno)
    assert acceso_cliente.leer_token(token) == (1, turno)
    establecimiento, id_turno, firma = token.split(".")
    # No se puede pasar al turno de otro ni a otro establecimiento.
    assert acceso_cliente.leer_token(f"{establecimiento}.{uuid.uuid4().hex}.{firma}") is None
    assert acceso_cliente.leer_token(f"2.{id_turno}.{firma}") is None
    assert acceso_cliente.leer_token(f"{establecimiento}.{id_turno}.{firma[:-1]}x") is None
    for roto in ("", "abc", "1.2", "x.y.z", f"{token}.mas"):
        assert acceso_cliente.leer_token(roto) is None


async def test_el_ticket_lleva_el_enlace_y_el_qr(client):
    turno = await _turno(client)
    datos = (await client.get(f"/api/v1/turnos/{turno['id']}/ticket")).json()
    assert "?cliente=" in datos["direccion"] and datos["numero"] == 1
    assert datos["qr"].startswith("data:image/svg+xml")


async def test_el_cliente_ve_su_estadia_sin_sesion_ni_datos_de_mas(client, anonimo):
    turno = await _turno(client, identificador_vehicular="ZZ999ZZ")
    await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 2})
    token = await _enlace(client, turno)
    resp = await anonimo.get(f"/api/v1/cliente/{token}")
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["activa"] and datos["numero"] == 1 and datos["total"] == 9600
    assert datos["consumos"][0]["cantidad"] == 2 and datos["proximo_cargo"]["monto"] == 2500
    assert datos["articulos"] and all("stock" not in a for a in datos["articulos"])
    # Ni la patente, ni quién atiende, ni datos internos.
    assert "ZZ999ZZ" not in resp.text and "Conserje" not in resp.text and "fondo" not in resp.text


async def test_consultar_no_guarda_nada(client, anonimo):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    await anonimo.get(f"/api/v1/cliente/{token}")
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()["estado"] == "En Curso"


async def test_el_enlace_vence_al_cerrar_el_turno(client, anonimo):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)).status_code == 200
    datos = (await anonimo.get(f"/api/v1/cliente/{token}")).json()
    assert datos["activa"] is False and "total" not in datos and "numero" not in datos
    assert (await anonimo.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": "TOALLAS"})).status_code == 409


async def test_un_enlace_inventado_no_abre_nada(anonimo):
    for token in ("nada", "1.2.3", f"1.{uuid.uuid4().hex}.firmafalsa"):
        assert (await anonimo.get(f"/api/v1/cliente/{token}")).status_code == 404
    # Bien firmado, pero de un turno que no existe.
    token = acceso_cliente.token_de(1, uuid.uuid4())
    assert (await anonimo.get(f"/api/v1/cliente/{token}")).status_code == 404


async def test_el_turno_de_otro_motel_no_se_ve_con_otro_establecimiento(client, anonimo):
    turno = await _turno(client)
    token = acceso_cliente.token_de(2, uuid.UUID(turno["id"]))
    assert (await anonimo.get(f"/api/v1/cliente/{token}")).status_code == 404


async def test_pedir_no_toca_el_stock_ni_la_cuenta(client, anonimo, db):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    resp = await anonimo.post(
        f"/api/v1/cliente/{token}/pedidos", json={"tipo": "ARTICULO", "articulo_id": 1, "cantidad": 2}
    )
    assert resp.status_code == 201, resp.text
    articulo = (await db.execute(select(Articulo).where(Articulo.id == 1))).scalars().first()
    assert articulo.stock_actual == 5
    datos = (await anonimo.get(f"/api/v1/cliente/{token}")).json()
    assert datos["total"] == 8000 and datos["pedidos"][0]["estado"] == "Pendiente"


async def test_lo_que_no_se_puede_pedir(client, anonimo):
    token = await _enlace(client, await _turno(client))
    pedidos = f"/api/v1/cliente/{token}/pedidos"
    assert (await anonimo.post(pedidos, json={"tipo": "CUALQUIER COSA"})).status_code == 422
    assert (await anonimo.post(pedidos, json={"tipo": "ARTICULO", "articulo_id": 1, "cantidad": 6})).status_code == 422
    assert (await anonimo.post(pedidos, json={"tipo": "ARTICULO", "cantidad": 1})).status_code == 422
    assert (await anonimo.post(pedidos, json={"tipo": "ARTICULO", "articulo_id": 999})).status_code == 409
    # Un aviso repetido no se acumula.
    assert (await anonimo.post(pedidos, json={"tipo": "TOALLAS"})).status_code == 201
    assert (await anonimo.post(pedidos, json={"tipo": "TOALLAS"})).status_code == 409


async def test_no_se_puede_inundar_la_ventanilla(client, anonimo):
    token = await _enlace(client, await _turno(client))
    pedidos = f"/api/v1/cliente/{token}/pedidos"
    for tipo in ("TOALLAS", "LLAMAR", "SALIDA"):
        assert (await anonimo.post(pedidos, json={"tipo": tipo})).status_code == 201
    resp = await anonimo.post(pedidos, json={"tipo": "ARTICULO", "articulo_id": 1})
    assert resp.status_code == 429 and "en camino" in resp.json()["detail"]


async def test_la_ventanilla_entrega_y_recien_ahi_se_carga(client, anonimo, db):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    await anonimo.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": "ARTICULO", "articulo_id": 1, "cantidad": 2})
    pendientes = (await client.get("/api/v1/pedidos-cliente/")).json()
    assert len(pendientes) == 1 and pendientes[0]["numero"] == 1 and pendientes[0]["subtotal"] == 1600
    pedido = pendientes[0]["id"]
    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido}/atender")).status_code == 200
    assert (await client.get("/api/v1/pedidos-cliente/")).json() == []
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()["total_consumos"] == 1600
    articulo = (await db.execute(select(Articulo).where(Articulo.id == 1))).scalars().first()
    assert articulo.stock_actual == 3
    fila = (await db.execute(select(PedidoCliente))).scalars().first()
    assert fila.estado == "Atendido" and fila.atendido_por_id is not None
    # El cliente lo ve entregado y en su cuenta.
    datos = (await anonimo.get(f"/api/v1/cliente/{token}")).json()
    assert datos["pedidos"][0]["estado"] == "Atendido" and datos["total"] == 9600
    # Una sola vez.
    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido}/atender")).status_code == 409


async def test_rechazar_no_carga_nada(client, anonimo):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    await anonimo.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": "ARTICULO", "articulo_id": 1})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    assert (await client.post(f"/api/v1/pedidos-cliente/{pedido}/rechazar")).status_code == 200
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()["total_consumos"] == 0
    assert (await anonimo.get(f"/api/v1/cliente/{token}")).json()["pedidos"][0]["estado"] == "Rechazado"


async def test_si_se_acabo_el_stock_el_pedido_queda_pendiente(client, anonimo, db):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    await anonimo.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": "ARTICULO", "articulo_id": 1, "cantidad": 2})
    articulo = (await db.execute(select(Articulo).where(Articulo.id == 1))).scalars().first()
    articulo.stock_actual = 1
    await db.commit()
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    resp = await client.post(f"/api/v1/pedidos-cliente/{pedido}/atender")
    assert resp.status_code == 400 and "Stock insuficiente" in resp.json()["detail"]
    assert len((await client.get("/api/v1/pedidos-cliente/")).json()) == 1


async def test_atender_exige_la_guardia_propia(client, anonimo, cliente_como):
    token = await _enlace(client, await _turno(client))
    await anonimo.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": "TOALLAS"})
    pedido = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    for usuario in ("gerencia", "conserje2"):
        ajeno = await cliente_como(usuario)
        assert (await ajeno.post(f"/api/v1/pedidos-cliente/{pedido}/atender")).status_code == 409


async def test_los_pedidos_de_un_turno_cerrado_salen_de_la_lista(client, anonimo):
    turno = await _turno(client)
    token = await _enlace(client, turno)
    await anonimo.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": "SALIDA"})
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    assert (await client.get("/api/v1/pedidos-cliente/")).json() == []


async def test_la_ventanilla_necesita_sesion(anonimo):
    assert (await anonimo.get("/api/v1/pedidos-cliente/")).status_code == 401
    assert (await anonimo.get(f"/api/v1/turnos/{uuid.uuid4()}/ticket")).status_code == 401
