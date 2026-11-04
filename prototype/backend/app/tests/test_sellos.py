"""Comprobantes verificables (migración 012): huellas encadenadas, alteraciones detectadas y verificación por código."""

from decimal import Decimal

from sqlalchemy import select, update

from app.models.arqueo import ArqueoCaja
from app.models.pago import Pago
from app.models.sello_arqueo import SelloArqueo
from app.services import sellos
from app.tests.conftest import abrir_guardia
from scripts.cargar_historial import generar_historial

ARQUEO = "/api/v1/guardias/actual/arqueo"
COBRO = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}


async def _guardia_con_cobro(cliente, habitacion_id: int = 1) -> dict:
    """Cobra un turno y cierra la guardia con el recuento correcto. Devuelve el arqueo."""
    turno = (
        await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, "tipo_cliente": "Auto"})
    ).json()
    assert (await cliente.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)).status_code == 200
    await cliente.patch(f"/api/v1/habitaciones/{habitacion_id}/liberar")
    guardia = (await cliente.get("/api/v1/guardias/actual")).json()
    resp = await cliente.post(ARQUEO, json={"efectivo": float(guardia["fondo_inicial"]) + 8000})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


async def _dos_arqueos(client, cliente_como) -> list[dict]:
    primero = await _guardia_con_cobro(client)
    await abrir_guardia(client)
    segundo = await _guardia_con_cobro(client, 2)
    gerencia = await cliente_como("gerencia")
    return [(await gerencia.get(f"/api/v1/arqueos/{a['id']}")).json() for a in (primero, segundo)]


def test_el_codigo_se_lee_en_grupos_y_se_normaliza():
    huella = "abcdef0123456789" + "0" * 48
    assert sellos.codigo_de(huella) == "ABCD-EF01-2345-6789"
    assert sellos.normalizar_codigo(" ABCD-ef01 2345.6789 ") == "abcdef0123456789"


async def test_cada_arqueo_queda_encadenado_con_el_anterior(client, cliente_como, db):
    primero, segundo = await _dos_arqueos(client, cliente_como)
    assert (primero["secuencia"], segundo["secuencia"]) == (1, 2)
    assert len(primero["huella"]) == 64 and primero["codigo"].count("-") == 3
    filas = list((await db.execute(select(SelloArqueo).order_by(SelloArqueo.secuencia))).scalars())
    assert filas[0].huella_anterior == sellos.HUELLA_INICIAL and filas[1].huella_anterior == filas[0].huella
    assert filas[0].huella != filas[1].huella


async def test_la_verificacion_pasa_si_nada_cambio(client, cliente_como):
    await _dos_arqueos(client, cliente_como)
    gerencia = await cliente_como("gerencia")
    resultado = (await gerencia.get("/api/v1/arqueos/integridad")).json()
    assert (resultado["total"], resultado["integros"], resultado["alterados"], resultado["sin_sello"]) == (2, 2, [], 0)


async def test_detecta_un_importe_cambiado_en_la_base(client, cliente_como, db):
    primero, segundo = await _dos_arqueos(client, cliente_como)
    await db.execute(update(ArqueoCaja).where(ArqueoCaja.id == primero["id"]).values(declarado_efectivo=Decimal("1")))
    await db.commit()
    gerencia = await cliente_como("gerencia")
    resultado = (await gerencia.get("/api/v1/arqueos/integridad")).json()
    assert resultado["integros"] == 1 and len(resultado["alterados"]) == 1
    alterado = resultado["alterados"][0]
    assert alterado["arqueo_id"] == primero["id"] and "no coinciden" in alterado["motivo"]
    assert alterado["operador_nombre"] == "Conserje Uno"
    # El segundo sigue íntegro: la alteración queda señalada en el comprobante exacto.
    assert all(a["arqueo_id"] != segundo["id"] for a in resultado["alterados"])


async def test_detecta_un_cobro_cambiado_aunque_el_arqueo_siga_igual(client, cliente_como, db):
    primero, _ = await _dos_arqueos(client, cliente_como)
    guardia_id = primero["guardia_id"]
    await db.execute(update(Pago).where(Pago.guardia_id == guardia_id).values(monto=Decimal("1")))
    await db.commit()
    gerencia = await cliente_como("gerencia")
    resultado = (await gerencia.get("/api/v1/arqueos/integridad")).json()
    assert [a["arqueo_id"] for a in resultado["alterados"]] == [primero["id"]]


async def test_recalcular_una_huella_corta_la_cadena_con_el_siguiente(client, cliente_como, db):
    primero, segundo = await _dos_arqueos(client, cliente_como)
    arqueo = await db.get(ArqueoCaja, primero["id"])
    arqueo.declarado_efectivo = Decimal("1")
    await db.flush()
    pagos = list((await db.execute(select(Pago).where(Pago.guardia_id == arqueo.guardia_id))).scalars())
    # Quien altera también recalcula la huella del arqueo: su eslabón coincide, pero el siguiente ya no.
    nueva = sellos.huella_de(sellos.HUELLA_INICIAL, 1, sellos.contenido_de(arqueo, pagos))
    await db.execute(update(SelloArqueo).where(SelloArqueo.arqueo_id == arqueo.id).values(huella=nueva))
    await db.commit()
    gerencia = await cliente_como("gerencia")
    resultado = (await gerencia.get("/api/v1/arqueos/integridad")).json()
    assert [a["arqueo_id"] for a in resultado["alterados"]] == [segundo["id"]]
    assert "se corta" in resultado["alterados"][0]["motivo"]


async def test_verificar_por_el_codigo_impreso(client, cliente_como, db):
    primero, _ = await _dos_arqueos(client, cliente_como)
    gerencia = await cliente_como("gerencia")
    bien = (await gerencia.get(f"/api/v1/arqueos/verificar/{primero['codigo']}")).json()
    assert bien["encontrado"] and bien["coincide"] and bien["arqueo_id"] == primero["id"]
    assert bien["operador_nombre"] == "Conserje Uno" and bien["categoria"] == "Correcto"
    minusculas = (await gerencia.get(f"/api/v1/arqueos/verificar/{primero['codigo'].lower()}")).json()
    assert minusculas["coincide"]
    inventado = (await gerencia.get("/api/v1/arqueos/verificar/AAAA-BBBB-CCCC-DDDD")).json()
    assert not inventado["encontrado"] and "no salió de este sistema" in inventado["detalle"]
    corto = (await gerencia.get("/api/v1/arqueos/verificar/12")).json()
    assert not corto["encontrado"]

    await db.execute(update(ArqueoCaja).where(ArqueoCaja.id == primero["id"]).values(total_declarado=Decimal("1")))
    await db.commit()
    cambiado = (await gerencia.get(f"/api/v1/arqueos/verificar/{primero['codigo']}")).json()
    assert cambiado["encontrado"] and not cambiado["coincide"]


async def test_el_comprobante_en_pdf_lleva_la_huella_y_el_qr(client, cliente_como):
    primero, _ = await _dos_arqueos(client, cliente_como)
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.get(f"/api/v1/arqueos/{primero['id']}/comprobante.pdf")
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    assert b"Comprobante verificable" in resp.content
    assert primero["codigo"].encode() in resp.content and primero["huella"].encode() in resp.content
    assert b" re f Q" in resp.content  # el QR, dibujado como celdas


async def test_el_cierre_supervisado_tambien_se_sella(client, cliente_como):
    guardia = (await client.get("/api/v1/guardias/actual")).json()
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.post(
        f"/api/v1/arqueos/guardias/{guardia['id']}/cierre-supervisado",
        json={"efectivo": 7000, "observacion": "Se retiró sin cerrar su guardia."},
    )
    assert resp.status_code == 201, resp.text
    detalle = (await gerencia.get(f"/api/v1/arqueos/{resp.json()['id']}")).json()
    assert detalle["secuencia"] == 1
    assert (await gerencia.get("/api/v1/arqueos/integridad")).json()["integros"] == 1


async def test_solo_la_gerencia_verifica(client):
    assert (await client.get("/api/v1/arqueos/integridad")).status_code == 403


async def test_el_historial_de_ejemplo_queda_sellado_y_sigue_la_cadena(db, client, cliente_como):
    generado = await generar_historial(db, dias=7, semilla=2)
    gerencia = await cliente_como("gerencia")
    resultado = (await gerencia.get("/api/v1/arqueos/integridad")).json()
    assert resultado["total"] == generado["arqueos"] == resultado["integros"]
    # Una guardia real continúa la cadena de lo anterior.
    arqueo = await _guardia_con_cobro(client)
    detalle = (await gerencia.get(f"/api/v1/arqueos/{arqueo['id']}")).json()
    assert detalle["secuencia"] == generado["arqueos"] + 1
    assert (await gerencia.get("/api/v1/arqueos/integridad")).json()["alterados"] == []
