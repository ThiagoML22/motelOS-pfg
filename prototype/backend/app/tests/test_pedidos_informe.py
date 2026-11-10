"""Pedidos de reposición (migración 010) e informe mensual de arqueos en PDF."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.tests.conftest import CLAVE_OTRO_MOTEL, ESTABLECIMIENTO_OTRO, nuevo_cliente
from scripts.cargar_historial import generar_historial

PEDIDOS = "/api/v1/pedidos/"


async def _stock(cliente, articulo_id: int) -> int:
    return next(a for a in (await cliente.get("/api/v1/articulos/")).json() if a["id"] == articulo_id)["stock_actual"]


async def test_la_gerencia_arma_el_pedido_y_el_conserje_lo_recibe(cliente_como):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(
        PEDIDOS,
        json={
            "proveedor": "Distribuidora Norte",
            "nota": "Entregar a la mañana",
            "items": [{"articulo_id": 1, "cantidad": 24}, {"articulo_id": 2, "cantidad": 12}],
        },
    )
    assert alta.status_code == 201, alta.text
    pedido = alta.json()
    assert pedido["estado"] == "Pendiente" and pedido["creado_por_nombre"] == "Gerencia"
    assert {i["articulo_id"]: i["cantidad"] for i in pedido["items"]} == {1: 24, 2: 12}

    pdf = await gerencia.get(f"/api/v1/pedidos/{pedido['id']}/pedido.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and b"Distribuidora Norte" in pdf.content

    conserje = await cliente_como("conserje1")
    antes = await _stock(conserje, 1)
    # Llegaron 20 aguas de las 24 y ninguna papa.
    recibido = await conserje.post(
        f"{PEDIDOS}{pedido['id']}/recepcion",
        json={
            "items": [{"articulo_id": 1, "recibida": 20}, {"articulo_id": 2, "recibida": 0}],
        },
    )
    assert recibido.status_code == 200, recibido.text
    datos = recibido.json()
    assert datos["estado"] == "Recibido" and datos["cerrado_por_nombre"] == "Conserje Uno"
    assert await _stock(conserje, 1) == antes + 20 and await _stock(conserje, 2) == 0
    # No se recibe dos veces.
    otra = await conserje.post(
        f"{PEDIDOS}{pedido['id']}/recepcion",
        json={"items": [{"articulo_id": 1, "recibida": 1}, {"articulo_id": 2, "recibida": 0}]},
    )
    assert otra.status_code == 409

    actividad = (await gerencia.get("/api/v1/configuracion/actividad")).json()
    recepcion = next(e for e in actividad if e["accion"] == "ARTICULO_REPOSICION")
    assert "se pidieron 24" in recepcion["descripcion"] and recepcion["requiere_revision"]
    assert any(e["accion"] == "PEDIDO_ALTA" for e in actividad)


async def test_reglas_de_los_pedidos(cliente_como):
    gerencia = await cliente_como("gerencia")
    conserje = await cliente_como("conserje1")
    item = {"items": [{"articulo_id": 1, "cantidad": 6}]}
    assert (await conserje.post(PEDIDOS, json=item)).status_code == 403
    assert (await gerencia.post(PEDIDOS, json={"items": []})).status_code == 422
    repetido = {"items": [{"articulo_id": 1, "cantidad": 6}, {"articulo_id": 1, "cantidad": 2}]}
    assert (await gerencia.post(PEDIDOS, json=repetido)).status_code == 422
    assert (await gerencia.post(PEDIDOS, json={"items": [{"articulo_id": 999, "cantidad": 1}]})).status_code == 404

    pedido = (await gerencia.post(PEDIDOS, json=item)).json()
    incompleta = await conserje.post(
        f"{PEDIDOS}{pedido['id']}/recepcion", json={"items": [{"articulo_id": 2, "recibida": 1}]}
    )
    assert incompleta.status_code == 422
    assert (await conserje.post(f"{PEDIDOS}{pedido['id']}/anulacion")).status_code == 403
    anulado = await gerencia.post(f"{PEDIDOS}{pedido['id']}/anulacion")
    assert anulado.status_code == 200 and anulado.json()["estado"] == "Anulado"
    recibir = await conserje.post(
        f"{PEDIDOS}{pedido['id']}/recepcion", json={"items": [{"articulo_id": 1, "recibida": 6}]}
    )
    assert recibir.status_code == 409
    estados = [p["estado"] for p in (await conserje.get(PEDIDOS)).json()]
    assert estados == ["Anulado"]

    # Otro motel no ve ni recibe los pedidos de este.
    async with nuevo_cliente() as otro:
        login = {"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL}
        assert (await otro.post("/api/v1/auth/login", json=login)).status_code == 200
        assert (await otro.get(PEDIDOS)).json() == []
        assert (await otro.get(f"/api/v1/pedidos/{pedido['id']}/pedido.pdf")).status_code == 404


async def test_pedido_sugerido_e_informe_mensual(db, cliente_como):
    await generar_historial(db, dias=42, semilla=9)
    gerencia = await cliente_como("gerencia")
    sugerido = await gerencia.get("/api/v1/pedidos/sugerido")
    assert sugerido.status_code == 200 and all(s["sugerido"] > 0 for s in sugerido.json())

    mes = datetime.now(UTC).astimezone(ZoneInfo(settings.ZONA_HORARIA)).strftime("%Y-%m")
    meses = (await gerencia.get("/api/v1/arqueos/meses")).json()
    mes = meses[0]["mes"] if meses else mes
    informe = await gerencia.get(f"/api/v1/arqueos/meses/{mes}/informe.pdf")
    assert informe.status_code == 200 and informe.headers["content-type"] == "application/pdf"
    assert (
        informe.content.startswith(b"%PDF")
        and b"Informe de arqueos" in informe.content
        and b"Conserje Uno" in informe.content
    )
    assert (await gerencia.get("/api/v1/arqueos/meses/2026-13/informe.pdf")).status_code == 422
    conserje = await cliente_como("conserje1")
    assert (await conserje.get(f"/api/v1/arqueos/meses/{mes}/informe.pdf")).status_code == 403
    assert (await conserje.get("/api/v1/pedidos/sugerido")).status_code == 403
