"""QR fijo de la habitación (migración 020): el primer celular que escanea se queda con la estadía, sin ticket y sin
hablar con la ventanilla; los demás ven solo la carta."""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.vinculo_cliente import POR_QR, VinculoCliente
from app.services import qr_habitacion
from app.tests.conftest import nuevo_cliente

COBRO = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}


async def _turno(cliente, habitacion_id: int = 1) -> dict:
    resp = await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, "tipo_cliente": "Auto"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _qrs(cliente_como) -> dict[int, str]:
    """El token de cada QR fijo, sacado de lo que imprime la gerencia."""
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.get("/api/v1/configuracion/qr-habitaciones")
    assert resp.status_code == 200, resp.text
    return {q["numero"]: q["direccion"].split("habitacion=")[1] for q in resp.json()}


async def _entrar(celular, qr: str) -> dict:
    resp = await celular.post(f"/api/v1/cliente/habitacion/{qr}/entrar")
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
async def celulares(session_factory):
    """Celulares de clientes: cada uno con su propia cookie."""
    abiertos = []

    def crear():
        ac = nuevo_cliente()
        abiertos.append(ac)
        return ac

    yield crear
    for ac in abiertos:
        await ac.aclose()


def test_el_qr_esta_firmado():
    class Hab:
        establecimiento_id, id, qr_version = 1, 7, 2

    token = qr_habitacion.qr_de(Hab)
    assert qr_habitacion.leer_qr(token) == (1, 7, 2)
    est, hab, version, firma = token.split(".")
    for tocado in (f"{est}.8.{version}.{firma}", f"2.{hab}.{version}.{firma}", f"{est}.{hab}.3.{firma}"):
        assert qr_habitacion.leer_qr(tocado) is None
    for roto in ("", "x", "1.2.3", "1.2.3.4.5", "١.2.3.firma", f"{token}.mas"):
        assert qr_habitacion.leer_qr(roto) is None
    # Una firma de un uso no sirve para otro.
    assert qr_habitacion.leer_token_de_vinculo(f"v.{est}.{hab}.{firma}") is None


async def test_el_primero_que_escanea_se_queda_con_la_estadia(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    await _turno(client)
    pareja, otro = celulares(), celulares()
    vinculado = await _entrar(pareja, qr)
    assert vinculado["estado"] == "vinculado" and vinculado["token"].startswith("v.")
    estadia = (await pareja.get(f"/api/v1/cliente/{vinculado['token']}")).json()
    assert estadia["activa"] and estadia["numero"] == 1 and estadia["total"] == 8000
    # Volver a escanear desde el mismo celular abre lo mismo.
    assert (await _entrar(pareja, qr))["token"] == vinculado["token"]
    # Otro celular ve solo la carta, y el enlace copiado no le sirve.
    carta = await _entrar(otro, qr)
    assert carta["estado"] == "libre" and "token" not in carta and "total" not in carta
    copiado = f"/api/v1/cliente/{vinculado['token']}"
    assert (await otro.get(copiado)).status_code == 404
    assert (await otro.post(f"{copiado}/pedidos", json={"tipo": "TOALLAS"})).status_code == 404


async def test_ocupada_o_libre_el_qr_muestra_lo_mismo(client, cliente_como, celulares):
    qrs = await _qrs(cliente_como)
    await _turno(client, 1)
    await _entrar(celulares(), qrs[1])
    curioso = celulares()
    ocupada, libre = await _entrar(curioso, qrs[1]), await _entrar(curioso, qrs[2])
    assert ocupada.keys() == libre.keys() and ocupada["articulos"] == libre["articulos"]
    assert ocupada["numero"] == 1 and libre["numero"] == 2
    # Lo que no tiene stock no se ofrece.
    assert [a["descripcion"] for a in libre["articulos"]] == ["Agua Mineral 500ml"]


async def test_un_qr_inventado_o_de_otra_version_no_abre_nada(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    celular = celulares()
    est, hab, version, firma = qr.split(".")
    for token in ("nada", f"{est}.{hab}.{int(version) + 1}.{firma}", f"{est}.2.{version}.{firma}"):
        assert (await celular.post(f"/api/v1/cliente/habitacion/{token}/entrar")).status_code == 404
    # Bien firmado, pero con una versión que la habitación todavía no tiene.
    class Hab:
        establecimiento_id, id, qr_version = 1, 1, 9

    otro = qr_habitacion.qr_de(Hab)
    assert (await celular.post(f"/api/v1/cliente/habitacion/{otro}/entrar")).status_code == 404


async def test_la_gerencia_regenera_el_qr_y_el_impreso_deja_de_servir(client, cliente_como, celulares):
    viejo = (await _qrs(cliente_como))[1]
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.post("/api/v1/configuracion/habitaciones/1/qr")
    assert resp.status_code == 200 and resp.json()["version"] == 2
    nuevo = resp.json()["direccion"].split("habitacion=")[1]
    celular = celulares()
    assert (await celular.post(f"/api/v1/cliente/habitacion/{viejo}/entrar")).status_code == 404
    assert (await _entrar(celular, nuevo))["estado"] == "libre"
    actividad = (await gerencia.get("/api/v1/configuracion/actividad")).json()
    assert any(a["accion"] == "HABITACION_QR" for a in actividad)
    # El conserje no imprime ni regenera.
    assert (await client.get("/api/v1/configuracion/qr-habitaciones")).status_code == 403
    assert (await client.post("/api/v1/configuracion/habitaciones/1/qr")).status_code == 403


async def test_se_suman_celulares_desde_el_vinculado_hasta_tres(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    turno = await _turno(client)
    primero = celulares()
    token = (await _entrar(primero, qr))["token"]
    resp = await primero.post(f"/api/v1/cliente/{token}/invitacion")
    assert resp.status_code == 200, resp.text
    invitacion = resp.json()
    assert invitacion["qr"].startswith("data:image/svg+xml") and "?sumar=" in invitacion["direccion"]
    codigo = invitacion["direccion"].split("sumar=")[1]
    segundo, tercero, cuarto = celulares(), celulares(), celulares()
    for celular in (segundo, tercero):
        resp = await celular.post(f"/api/v1/cliente/sumar/{codigo}")
        assert resp.status_code == 200 and resp.json()["estado"] == "vinculado"
        assert (await celular.get(f"/api/v1/cliente/{resp.json()['token']}")).json()["numero"] == 1
    # Sumarse dos veces no ocupa otro lugar.
    assert (await segundo.post(f"/api/v1/cliente/sumar/{codigo}")).status_code == 200
    resp = await cuarto.post(f"/api/v1/cliente/sumar/{codigo}")
    assert resp.status_code == 409 and "3 celulares" in resp.json()["detail"]
    assert (await primero.post(f"/api/v1/cliente/{token}/invitacion")).status_code == 409
    # La ventanilla ve cuántos hay.
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/ticket")).json()["vinculados"] == 3


async def test_la_invitacion_vence_y_no_se_inventa(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    await _turno(client)
    primero = celulares()
    token = (await _entrar(primero, qr))["token"]
    codigo = (await primero.post(f"/api/v1/cliente/{token}/invitacion")).json()["direccion"].split("sumar=")[1]
    invitacion = qr_habitacion.leer_invitacion(codigo)
    assert invitacion is not None and not qr_habitacion.vencida(invitacion)
    assert qr_habitacion.vencida(invitacion, ahora=time.time() + 11 * 60)
    est, vinculo, expira, firma = codigo.split(".")
    otro = celulares()
    for falso in (f"{est}.{vinculo}.{int(expira) + 3600}.{firma}", "nada", token):
        resp = await otro.post(f"/api/v1/cliente/sumar/{falso}")
        assert resp.status_code == 404 and "venció" in resp.json()["detail"]


async def test_una_invitacion_vencida_no_suma_pero_no_deja_afuera_al_que_ya_se_sumo(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    await _turno(client)
    primero = celulares()
    token = (await _entrar(primero, qr))["token"]
    codigo = (await primero.post(f"/api/v1/cliente/{token}/invitacion")).json()["direccion"].split("sumar=")[1]
    sumado, tarde = celulares(), celulares()
    assert (await sumado.post(f"/api/v1/cliente/sumar/{codigo}")).status_code == 200
    momento = time.time() + 11 * 60
    with patch("app.services.qr_habitacion.time.time", return_value=momento):
        assert (await tarde.post(f"/api/v1/cliente/sumar/{codigo}")).status_code == 404
        resp = await sumado.post(f"/api/v1/cliente/sumar/{codigo}")
        assert resp.status_code == 200 and resp.json()["estado"] == "vinculado"
    # El enlace del ticket no suma celulares.
    assert (await tarde.post("/api/v1/cliente/1.abc.firma/invitacion")).status_code == 409


async def test_al_irse_califica_y_no_se_queda_con_la_estadia_siguiente(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    turno = await _turno(client)
    anterior = celulares()
    token = (await _entrar(anterior, qr))["token"]
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)).status_code == 200
    datos = (await anterior.get(f"/api/v1/cliente/{token}")).json()
    assert datos["activa"] is False and datos["puede_calificar"] and "total" not in datos
    # Escanear de nuevo lo lleva a calificar, no a la carta.
    assert await _entrar(anterior, qr) == {"estado": "terminada", "token": token}
    calificacion = {"puntaje": 5, "problemas": 0}
    assert (await anterior.post(f"/api/v1/cliente/{token}/calificacion", json=calificacion)).status_code == 201
    # Llega otro cliente: quien guardó el enlace no se queda con su estadía; el que entra, sí.
    await client.patch("/api/v1/habitaciones/1/liberar")
    await _turno(client)
    assert (await _entrar(anterior, qr))["estado"] == "libre"
    assert (await _entrar(celulares(), qr))["estado"] == "vinculado"


async def test_pasadas_las_12_horas_el_celular_vuelve_a_poder(client, cliente_como, celulares, db):
    qr = (await _qrs(cliente_como))[1]
    turno = await _turno(client)
    celular = celulares()
    await _entrar(celular, qr)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    vinculo = (await db.execute(select(VinculoCliente))).scalars().first()
    vinculo.creado_en = datetime.now(UTC) - timedelta(hours=13)
    await db.commit()
    await client.patch("/api/v1/habitaciones/1/liberar")
    await _turno(client)
    assert (await _entrar(celular, qr))["estado"] == "vinculado"


async def test_un_celular_no_tiene_dos_estadias_a_la_vez(client, cliente_como, celulares):
    qrs = await _qrs(cliente_como)
    await _turno(client, 1)
    await _turno(client, 2)
    celular = celulares()
    assert (await _entrar(celular, qrs[1]))["estado"] == "vinculado"
    assert (await _entrar(celular, qrs[2]))["estado"] == "libre"
    assert (await _entrar(celulares(), qrs[2]))["estado"] == "vinculado"


async def test_no_fui_yo_la_ventanilla_libera_el_qr(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    await _turno(client)
    intruso, cliente = celulares(), celulares()
    token_intruso = (await _entrar(intruso, qr))["token"]
    assert (await _entrar(cliente, qr))["estado"] == "libre"
    resp = await cliente.post(f"/api/v1/cliente/habitacion/{qr}/aviso")
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    pendientes = (await client.get("/api/v1/pedidos-cliente/")).json()
    assert len(pendientes) == 1 and pendientes[0]["tipo"] == "VINCULO" and pendientes[0]["numero"] == 1
    # Un segundo aviso mientras el primero espera no se acumula.
    await cliente.post(f"/api/v1/cliente/habitacion/{qr}/aviso")
    assert len((await client.get("/api/v1/pedidos-cliente/")).json()) == 1
    assert (await client.post(f"/api/v1/pedidos-cliente/{pendientes[0]['id']}/atender")).status_code == 200
    # El intruso quedó afuera y no puede volver a entrar; el cliente, sí.
    assert (await intruso.get(f"/api/v1/cliente/{token_intruso}")).status_code == 404
    assert (await _entrar(intruso, qr))["estado"] == "libre"
    assert (await _entrar(cliente, qr))["estado"] == "vinculado"


async def test_liberado_el_qr_entra_aunque_haya_estado_hace_poco(client, cliente_como, celulares):
    """La pareja que vuelve a la misma habitación en el día: avisa y la ventanilla libera el QR."""
    qr = (await _qrs(cliente_como))[1]
    turno = await _turno(client)
    pareja = celulares()
    await _entrar(pareja, qr)
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=COBRO)
    await client.patch("/api/v1/habitaciones/1/liberar")
    await _turno(client)
    # Todavía no calificó la anterior: el QR la lleva a calificar, no a la estadía nueva.
    assert (await _entrar(pareja, qr))["estado"] == "terminada"
    await pareja.post(f"/api/v1/cliente/habitacion/{qr}/aviso")
    aviso = (await client.get("/api/v1/pedidos-cliente/")).json()[0]["id"]
    await client.post(f"/api/v1/pedidos-cliente/{aviso}/atender")
    assert (await _entrar(pareja, qr))["estado"] == "vinculado"


async def test_el_aviso_no_dice_si_esta_ocupada_ni_se_puede_repetir_sin_fin(client, cliente_como, celulares):
    qrs = await _qrs(cliente_como)
    curioso = celulares()
    resp = await curioso.post(f"/api/v1/cliente/habitacion/{qrs[2]}/aviso")
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert (await client.get("/api/v1/pedidos-cliente/")).json() == []
    await _turno(client, 1)
    ignorados = 0
    for _ in range(qr_habitacion.MAXIMO_AVISOS + 2):
        assert (await curioso.post(f"/api/v1/cliente/habitacion/{qrs[1]}/aviso")).json() == {"ok": True}
        for pedido in (await client.get("/api/v1/pedidos-cliente/")).json():
            assert (await client.post(f"/api/v1/pedidos-cliente/{pedido['id']}/rechazar")).status_code == 200
            ignorados += 1
    assert ignorados == qr_habitacion.MAXIMO_AVISOS


async def test_el_aviso_no_aparece_en_la_estadia_ni_cuenta_como_pedido(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    await _turno(client)
    cliente = celulares()
    token = (await _entrar(cliente, qr))["token"]
    await celulares().post(f"/api/v1/cliente/habitacion/{qr}/aviso")
    assert (await cliente.get(f"/api/v1/cliente/{token}")).json()["pedidos"] == []
    for tipo in ("TOALLAS", "LLAMAR", "SALIDA"):
        assert (await cliente.post(f"/api/v1/cliente/{token}/pedidos", json={"tipo": tipo})).status_code == 201


async def test_la_ventanilla_desvincula_desde_el_ticket(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    turno = await _turno(client)
    celular = celulares()
    token = (await _entrar(celular, qr))["token"]
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/desvincular")
    assert resp.status_code == 200 and resp.json() == {"cortados": 1}
    assert (await celular.get(f"/api/v1/cliente/{token}")).status_code == 404
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/ticket")).json()["vinculados"] == 0
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/desvincular")).json() == {"cortados": 0}


async def test_la_cookie_del_celular_es_httponly_y_solo_de_la_api(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    resp = await celulares().post(f"/api/v1/cliente/habitacion/{qr}/entrar")
    cookie = resp.headers["set-cookie"]
    assert cookie.startswith(f"{settings.COOKIE_CLIENTE}=") and "HttpOnly" in cookie and "Path=/api" in cookie
    assert "samesite=strict" in cookie.lower()


async def test_otro_motel_no_abre_con_el_qr_de_este(client, cliente_como, celulares):
    qr = (await _qrs(cliente_como))[1]
    _, hab, version, _ = qr.split(".")

    class Hab:
        establecimiento_id, id, qr_version = 2, int(hab), int(version)

    ajeno = qr_habitacion.qr_de(Hab)
    assert (await celulares().post(f"/api/v1/cliente/habitacion/{ajeno}/entrar")).status_code == 404


async def test_mot_explica_el_qr_fijo(client, cliente_como):
    async def decir(cliente, texto: str) -> str:
        resp = await cliente.post("/api/v1/asistente/pregunta", json={"texto": texto})
        assert resp.status_code == 200, resp.text
        return resp.json()["intencion"]

    for texto in ("como se usa el qr de la habitacion", "el cliente no puede ver su estadia", "como libero el qr"):
        assert await decir(client, texto) == "ayuda:qr_habitacion", texto
    gerencia = await cliente_como("gerencia")
    assert await decir(gerencia, "donde imprimo los qr de las habitaciones") == "ayuda:qr_habitacion"
    # El ticket sigue siendo su propio tema.
    assert await decir(client, "como le doy el ticket al cliente") == "ayuda:imprimir_ticket"


async def test_los_vinculos_se_depuran_a_los_30_dias(client, cliente_como, celulares, db):
    qr = (await _qrs(cliente_como))[1]
    await _turno(client)
    await _entrar(celulares(), qr)
    vinculo = (await db.execute(select(VinculoCliente))).scalars().first()
    assert vinculo.origen == POR_QR and len(vinculo.huella) == 64
    vinculo.creado_en = datetime.now(UTC) - timedelta(days=31)
    await db.commit()
    assert await qr_habitacion.depurar_vinculos(db) == 1
