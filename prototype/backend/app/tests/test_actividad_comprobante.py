"""Registro de actividad para la gerencia (migración 007) y comprobante del arqueo en PDF (RF-10)."""

import pytest
from httpx import AsyncClient

from app.models.configuracion import ConfiguracionCaja
from app.services.actividad import pesos
from app.services.pdf import DocumentoPDF
from app.tests.conftest import CLAVE_OTRO_MOTEL, ESTABLECIMIENTO_OTRO, nuevo_cliente

ACTIVIDAD = "/api/v1/configuracion/actividad"
NUEVO = {
    "codigo": "SNA-009", "descripcion": "Turrón", "precio_unitario": 900, "stock_actual": 12, "categoria": "Snacks"
}


async def _pendientes(gerencia: AsyncClient) -> int:
    return (await gerencia.get(f"{ACTIVIDAD}/pendientes")).json()["pendientes"]


# --- Registro de actividad -----------------------------------------------------------------------------------------


async def test_el_alta_de_un_conserje_queda_por_revisar_para_la_gerencia(client: AsyncClient, cliente_como):
    alta = await client.post("/api/v1/articulos/", json=NUEVO)
    assert alta.status_code == 201

    gerencia = await cliente_como("gerencia")
    assert await _pendientes(gerencia) == 1
    entrada = (await gerencia.get(ACTIVIDAD, params={"pendientes": True})).json()[0]
    assert entrada["accion"] == "ARTICULO_ALTA" and entrada["categoria"] == "INVENTARIO"
    assert entrada["operador_nombre"] == "Conserje Uno"
    assert entrada["guardia_id"] is not None  # el conserje tenía su guardia abierta
    assert entrada["articulo_id"] == alta.json()["id"] and entrada["cantidad"] == 12
    assert "Turrón" in entrada["descripcion"] and entrada["valor_nuevo"] == "$ 900"
    assert entrada["requiere_revision"] and entrada["revisado_en"] is None


async def test_la_reposicion_suma_stock_y_queda_registrada(client: AsyncClient, cliente_como):
    resp = await client.post("/api/v1/articulos/1/reposicion", json={"cantidad": 6})
    assert resp.status_code == 200 and resp.json()["stock_actual"] == 11

    gerencia = await cliente_como("gerencia")
    entrada = (await gerencia.get(ACTIVIDAD)).json()[0]
    assert entrada["accion"] == "ARTICULO_REPOSICION" and entrada["cantidad"] == 6
    assert (entrada["valor_anterior"], entrada["valor_nuevo"]) == ("5 u.", "11 u.")


@pytest.mark.parametrize("cantidad", [0, -3, 20000])
async def test_la_reposicion_rechaza_cantidades_invalidas(client: AsyncClient, cantidad):
    assert (await client.post("/api/v1/articulos/1/reposicion", json={"cantidad": cantidad})).status_code == 422


async def test_no_se_repone_un_articulo_dado_de_baja_ni_inexistente(client: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.patch("/api/v1/configuracion/articulos/2", json={"activo": False})).status_code == 200
    assert (await client.post("/api/v1/articulos/2/reposicion", json={"cantidad": 1})).status_code == 404
    assert (await client.post("/api/v1/articulos/999/reposicion", json={"cantidad": 1})).status_code == 404


async def test_los_cambios_de_la_gerencia_se_registran_sin_revision(cliente_como, db):
    db.add(ConfiguracionCaja(establecimiento_id=1, fondo_cambio=25000))  # la crea la migración 005
    await db.commit()
    gerencia = await cliente_como("gerencia")
    await gerencia.patch("/api/v1/configuracion/articulos/1", json={"precio_unitario": 950, "descripcion": "Agua 500"})
    await gerencia.patch("/api/v1/configuracion/caja", json={"fondo_cambio": 30000})
    await gerencia.post(
        "/api/v1/configuracion/tarifas",
        json={"tarifa_base": 9000, "estadia_base_min": 120, "fraccion_min": 30, "tarifa_fraccion": 2800},
    )
    await gerencia.post("/api/v1/configuracion/habitaciones", json={"numero": 20})

    acciones = {e["accion"]: e for e in (await gerencia.get(ACTIVIDAD)).json()}
    assert {"ARTICULO_PRECIO", "ARTICULO_DATOS", "FONDO_CAMBIO", "TARIFA_NUEVA", "HABITACION_ALTA"} <= set(acciones)
    assert (acciones["ARTICULO_PRECIO"]["valor_anterior"], acciones["ARTICULO_PRECIO"]["valor_nuevo"]) == (
        "$ 800",
        "$ 950",
    )
    assert acciones["FONDO_CAMBIO"]["valor_nuevo"] == "$ 30.000"
    assert not any(e["requiere_revision"] for e in acciones.values())
    assert await _pendientes(gerencia) == 0
    # Un PATCH que no cambia nada no deja entradas.
    antes = len((await gerencia.get(ACTIVIDAD)).json())
    await gerencia.patch("/api/v1/configuracion/articulos/1", json={"precio_unitario": 950})
    assert len((await gerencia.get(ACTIVIDAD)).json()) == antes
    solo_tarifa = (await gerencia.get(ACTIVIDAD, params={"categoria": "TARIFA"})).json()
    assert [e["accion"] for e in solo_tarifa] == ["TARIFA_NUEVA"]


async def test_la_gerencia_marca_lo_revisado(client: AsyncClient, cliente_como):
    await client.post("/api/v1/articulos/", json=NUEVO)
    await client.post("/api/v1/articulos/1/reposicion", json={"cantidad": 2})
    gerencia = await cliente_como("gerencia")
    entradas = (await gerencia.get(ACTIVIDAD, params={"pendientes": True})).json()
    assert len(entradas) == 2

    resp = await gerencia.post(f"{ACTIVIDAD}/revision", json={"ids": [entradas[0]["id"]]})
    assert resp.json() == {"pendientes": 1}
    resp = await gerencia.post(f"{ACTIVIDAD}/revision", json={})
    assert resp.json() == {"pendientes": 0}
    revisada = next(e for e in (await gerencia.get(ACTIVIDAD)).json() if e["id"] == entradas[0]["id"])
    assert revisada["revisado_por_nombre"] == "Gerencia" and revisada["revisado_en"] is not None
    assert (await gerencia.post(f"{ACTIVIDAD}/revision", json={"ids": []})).status_code == 422


async def test_el_conserje_no_ve_ni_revisa_el_registro(client: AsyncClient):
    assert (await client.get(ACTIVIDAD)).status_code == 403
    assert (await client.post(f"{ACTIVIDAD}/revision", json={})).status_code == 403


async def test_el_registro_es_de_cada_establecimiento(client: AsyncClient):
    await client.post("/api/v1/articulos/", json=NUEVO)
    async with nuevo_cliente() as otra:
        await otra.post(
            "/api/v1/auth/login",
            json={"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL},
        )
        assert (await otra.get(ACTIVIDAD)).json() == []
        assert (await otra.get(f"{ACTIVIDAD}/pendientes")).json() == {"pendientes": 0}


def test_formato_de_pesos():
    assert pesos(25000) == "$ 25.000"
    assert pesos(1234.5) == "$ 1.234,50"
    assert pesos(0) == "$ 0"


# --- Comprobante en PDF (RF-10) ----------------------------------------------------------------------------------


async def _arqueo_con_un_cobro(client: AsyncClient) -> dict:
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Peaton"})).json()
    cobro = await client.post(
        f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
    )
    assert cobro.status_code == 200, cobro.text
    arqueo = await client.post("/api/v1/guardias/actual/arqueo", json={"efectivo": 7500})
    assert arqueo.status_code == 201, arqueo.text
    return arqueo.json()


async def test_el_conserje_descarga_el_comprobante_de_su_arqueo(client: AsyncClient):
    arqueo = await _arqueo_con_un_cobro(client)
    resp = await client.get(f"/api/v1/guardias/arqueos/{arqueo['id']}/comprobante.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert f'filename="arqueo-{arqueo["id"]}.pdf"' in resp.headers["content-disposition"]
    cuerpo = resp.content
    assert cuerpo.startswith(b"%PDF-1.4") and cuerpo.rstrip().endswith(b"%%EOF")
    assert b"Motel de prueba" in cuerpo
    assert "Faltante de $ 500".encode("cp1252") in cuerpo
    assert "Habitación 1".encode("cp1252") in cuerpo


async def test_solo_el_dueno_de_la_caja_y_la_gerencia_descargan_el_comprobante(client: AsyncClient, cliente_como):
    arqueo = await _arqueo_con_un_cobro(client)
    otro = await cliente_como("conserje2")
    assert (await otro.get(f"/api/v1/guardias/arqueos/{arqueo['id']}/comprobante.pdf")).status_code == 404
    assert (await otro.get(f"/api/v1/arqueos/{arqueo['id']}/comprobante.pdf")).status_code == 403
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.get(f"/api/v1/arqueos/{arqueo['id']}/comprobante.pdf")
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    assert (await gerencia.get("/api/v1/arqueos/999/comprobante.pdf")).status_code == 404


async def test_el_comprobante_lleva_los_datos_del_establecimiento(client: AsyncClient, cliente_como):
    gerencia = await cliente_como("gerencia")
    await gerencia.patch(
        "/api/v1/configuracion/establecimiento",
        json={"domicilio": "Calle Falsa 123", "leyenda_comprobante": "Conservar este comprobante (original)."},
    )
    arqueo = await _arqueo_con_un_cobro(client)
    cuerpo = (await gerencia.get(f"/api/v1/arqueos/{arqueo['id']}/comprobante.pdf")).content
    assert b"Calle Falsa 123" in cuerpo
    assert b"Conservar este comprobante \\(original\\)." in cuerpo  # los paréntesis van escapados


def test_el_pdf_tiene_una_tabla_de_referencias_valida():
    documento = DocumentoPDF("Prueba")
    documento.nueva_pagina().texto(50, 800, "Año: ñandú")
    cuerpo = documento.generar()
    inicio_xref = int(cuerpo.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0])
    assert cuerpo[inicio_xref:].startswith(b"xref\n")
    # Cada entrada de la tabla apunta al comienzo de su objeto.
    entradas = cuerpo[inicio_xref:].split(b"\n")[3:]
    for numero, entrada in enumerate(entradas, start=1):
        if not entrada.endswith(b" n "):
            break
        posicion = int(entrada[:10])
        assert cuerpo[posicion:].startswith(b"%d 0 obj" % numero)
    assert "Año: ñandú".encode("cp1252") in cuerpo
