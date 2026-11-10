"""Operación diaria (migración 016): recuento de ropa, traspaso de guardia, arreglos y traslado de turnos."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import settings
from app.models.actividad import RegistroActividad
from app.models.categoria import CategoriaHabitacion
from app.models.evento_habitacion import EventoHabitacion
from app.models.habitacion import Habitacion
from app.models.operacion import Arreglo, RopaConteo, TrasladoTurno, Traspaso
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services import rotacion
from app.tests.conftest import CLAVE_OTRO_MOTEL, ESTABLECIMIENTO_OTRO, nuevo_cliente
from scripts.cargar_historial import agregar_operacion, generar_historial

GUARDIAS = "/api/v1/guardias"
OPERACION = "/api/v1/operacion"
ARQUEO = {"efectivo": 0, "posnet": 0, "mercado_pago": 0}


def _ropa(toallas=(40, 10, 16), sabanas=(30, 6, 16)) -> dict:
    return {
        "conteos": [
            {"prenda": "TOALLAS", "limpias": toallas[0], "sucias": toallas[1], "en_habitaciones": toallas[2]},
            {"prenda": "SABANAS", "limpias": sabanas[0], "sucias": sabanas[1], "en_habitaciones": sabanas[2]},
        ]
    }


@pytest.fixture
def exige_recuento(monkeypatch):
    monkeypatch.setattr(settings, "EXIGIR_RECUENTO_ROPA", True)


@pytest_asyncio.fixture
async def otro_conserje(cliente_como):
    return await cliente_como("conserje2")


@pytest_asyncio.fixture
async def gerencia(cliente_como):
    return await cliente_como("gerencia")


async def _turno(cliente, habitacion_id: int = 1) -> dict:
    resp = await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, "tipo_cliente": "Auto"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _cerrar_con_conteo(cliente, ropa: dict) -> list[dict]:
    resp = await cliente.post(f"{GUARDIAS}/actual/ropa", json=ropa)
    assert resp.status_code == 201, resp.text
    assert (await cliente.post(f"{GUARDIAS}/actual/arqueo", json=ARQUEO)).status_code == 201
    return resp.json()["prendas"]


# --- Recuento de ropa ------------------------------------------------------------------------------------------------


async def test_sin_recuento_no_se_cierra_la_guardia(client, exige_recuento):
    resp = await client.post(f"{GUARDIAS}/actual/arqueo", json=ARQUEO)
    assert resp.status_code == 409 and "toallas" in resp.json()["detail"]
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())).status_code == 201
    assert (await client.post(f"{GUARDIAS}/actual/arqueo", json=ARQUEO)).status_code == 201


async def test_el_recuento_lleva_las_dos_prendas_y_se_hace_una_vez(client):
    solo_una = {"conteos": [_ropa()["conteos"][0]]}
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=solo_una)).status_code == 422
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())).status_code == 201
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())).status_code == 409


async def test_un_numero_negativo_no_entra(client):
    malo = _ropa(toallas=(-1, 0, 0))
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=malo)).status_code == 422


async def test_el_cierre_es_a_ciegas(client):
    """Mientras la guardia está abierta, nadie de la ventanilla ve cuánta ropa dejó el recuento anterior."""
    await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())
    pantalla = (await client.get(f"{GUARDIAS}/traspaso")).json()
    assert pantalla["ropa"] is None and pantalla["ropa_contada"] is True


async def test_quien_entra_ve_lo_que_dejaron_y_lo_confirma(client, otro_conserje, db):
    await _cerrar_con_conteo(client, _ropa())
    pantalla = (await otro_conserje.get(f"{GUARDIAS}/traspaso")).json()
    toallas = next(p for p in pantalla["ropa"] if p["prenda"] == "TOALLAS")
    assert (toallas["limpias"], toallas["sucias"], toallas["en_habitaciones"]) == (40, 10, 16)
    assert toallas["total"] == 66 and pantalla["saliente"]["sin_conteo"] is False

    assert (await otro_conserje.post(f"{GUARDIAS}/", json=_ropa())).status_code == 201
    filas = list((await db.execute(select(RopaConteo).where(RopaConteo.momento == "APERTURA"))).scalars())
    assert len(filas) == 2
    # Coincide: la gerencia no recibe ningún aviso.
    avisos = await db.execute(select(RegistroActividad).where(RegistroActividad.accion == "ROPA_DIFERENCIA"))
    assert list(avisos.scalars()) == []


async def test_una_diferencia_llega_a_la_gerencia_con_los_dos_nombres(client, otro_conserje, db):
    await _cerrar_con_conteo(client, _ropa())
    faltan = _ropa(toallas=(38, 10, 16))
    assert (await otro_conserje.post(f"{GUARDIAS}/", json=faltan)).status_code == 201
    aviso = (
        (await db.execute(select(RegistroActividad).where(RegistroActividad.accion == "ROPA_DIFERENCIA")))
        .scalars()
        .one()
    )
    assert aviso.requiere_revision is True and aviso.categoria == "OPERACION"
    assert "faltan 2" in aviso.descripcion
    assert "Conserje Uno" in aviso.descripcion and "Conserje Dos" in aviso.descripcion


async def test_lo_que_sale_a_lavanderia_no_es_un_faltante(client, otro_conserje, db):
    await _cerrar_con_conteo(client, _ropa())
    assert (await otro_conserje.post(f"{GUARDIAS}/", json=_ropa())).status_code == 201
    movimiento = {"prenda": "SABANAS", "tipo": "LAVANDERIA_SALE", "cantidad": 12}
    assert (await otro_conserje.post(f"{OPERACION}/ropa/movimientos", json=movimiento)).status_code == 201
    prendas = await _cerrar_con_conteo(otro_conserje, _ropa(sabanas=(18, 6, 16)))
    sabanas = next(p for p in prendas if p["prenda"] == "SABANAS")
    assert sabanas["esperado"] == 40 and sabanas["diferencia"] == 0


async def test_la_ropa_de_otra_guardia_no_se_toca_sin_guardia_propia(client, otro_conserje):
    movimiento = {"prenda": "TOALLAS", "tipo": "COMPRA", "cantidad": 10}
    assert (await otro_conserje.post(f"{OPERACION}/ropa/movimientos", json=movimiento)).status_code == 409


async def test_la_gerencia_cierra_y_queda_sin_conteo(client, gerencia, otro_conserje, exige_recuento):
    guardia = (await client.get(f"{GUARDIAS}/actual")).json()
    declaracion = {**ARQUEO, "observacion": "Se fue sin cerrar"}
    resp = await gerencia.post(f"/api/v1/arqueos/guardias/{guardia['id']}/cierre-supervisado", json=declaracion)
    assert resp.status_code == 201, resp.text
    pantalla = (await otro_conserje.get(f"{GUARDIAS}/traspaso")).json()
    assert pantalla["saliente"]["sin_conteo"] is True


async def test_otro_motel_no_ve_la_operacion(client):
    await _reportar(client)
    await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())
    async with nuevo_cliente() as otra:
        await otra.post(
            "/api/v1/auth/login",
            json={"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL},
        )
        tablero = (await otra.get(f"{OPERACION}/tablero")).json()
        assert tablero["arreglos"]["sin_resolver"] == [] and tablero["ropa"]["conteos"] == []
        assert (await otra.get(f"{OPERACION}/arreglos")).json() == []


async def test_el_historial_es_de_la_gerencia(client, gerencia, otro_conserje):
    assert (await client.get(f"{OPERACION}/tablero")).status_code == 403
    await _cerrar_con_conteo(client, _ropa())
    await otro_conserje.post(f"{GUARDIAS}/", json=_ropa(toallas=(39, 10, 16)))
    tablero = (await gerencia.get(f"{OPERACION}/tablero")).json()
    toallas = next(r for r in tablero["ropa"]["resumen"] if r["prenda"] == "TOALLAS")
    assert toallas["total"] == 65 and toallas["faltantes"] == 1
    diferencia = tablero["ropa"]["diferencias"][0]
    assert diferencia["diferencia"] == -1
    assert diferencia["operador"] == "Conserje Dos" and diferencia["anterior_por"] == "Conserje Uno"


# --- Traspaso --------------------------------------------------------------------------------------------------------


async def test_abrir_exige_confirmar_lo_recibido(client, otro_conserje, exige_recuento):
    await _cerrar_con_conteo(client, _ropa())
    assert (await otro_conserje.post(f"{GUARDIAS}/")).status_code == 409
    assert (await otro_conserje.get(f"{GUARDIAS}/actual")).json() is None
    assert (await otro_conserje.post(f"{GUARDIAS}/", json=_ropa())).status_code == 201


async def test_un_recuento_incompleto_no_abre_la_guardia(client, otro_conserje):
    await _cerrar_con_conteo(client, _ropa())
    solo_una = {"conteos": [_ropa()["conteos"][0]]}
    assert (await otro_conserje.post(f"{GUARDIAS}/", json=solo_una)).status_code == 422
    assert (await otro_conserje.get(f"{GUARDIAS}/actual")).json() is None


async def test_el_traspaso_queda_como_foto_y_sin_importes(client, otro_conserje, db):
    turno = await _turno(client)
    await client.post(
        f"{OPERACION}/arreglos",
        json={"habitacion_id": 2, "rubro": "AIRE", "descripcion": "No enfría"},
    )
    await _cerrar_con_conteo(client, _ropa())
    assert (await otro_conserje.post(f"{GUARDIAS}/", json=_ropa())).status_code == 201

    traspaso = (await db.execute(select(Traspaso))).scalars().one()
    resumen = traspaso.resumen
    assert [t["numero"] for t in resumen["turnos"]] == [1]
    assert resumen["arreglos"][0]["descripcion"] == "No enfría"
    assert resumen["ropa_dejada"][0]["total"] == 66
    texto = str(resumen)
    for prohibido in ("total_general", "tarifa_base", "identificador_vehicular", turno["id"]):
        assert prohibido not in texto


# --- Arreglos --------------------------------------------------------------------------------------------------------


async def _reportar(cliente, **extra) -> dict:
    datos = {"habitacion_id": 1, "rubro": "PLOMERIA", "descripcion": "Pierde la canilla", **extra}
    resp = await cliente.post(f"{OPERACION}/arreglos", json=datos)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_cada_habitacion_tiene_su_historial(client):
    await _reportar(client)
    await _reportar(client, habitacion_id=2, rubro="TV", descripcion="No enciende")
    filas = (await client.get(f"{OPERACION}/arreglos", params={"habitacion_id": 2})).json()
    assert [f["rubro_nombre"] for f in filas] == ["TV o Wi-Fi"]


async def test_un_mantenimiento_tambien_es_un_arreglo(client):
    arreglo = await _reportar(client, tipo="MANTENIMIENTO", rubro="AIRE", descripcion="Limpieza de filtros")
    assert arreglo["tipo_nombre"] == "Mantenimiento" and arreglo["estado"] == "Abierto"


async def test_la_grilla_marca_lo_que_falta_resolver(client):
    await _reportar(client)
    habitaciones = (await client.get("/api/v1/habitaciones/")).json()
    assert {h["id"]: h["arreglos_abiertos"] for h in habitaciones}[1] == 1


async def test_fuera_de_servicio_pasa_a_mantenimiento_y_al_resolver_vuelve(client, db):
    arreglo = await _reportar(client, fuera_de_servicio=True)
    habitacion = await db.get(Habitacion, 1)
    await db.refresh(habitacion)
    assert habitacion.estado == "Mantenimiento"

    resp = await client.post(
        f"{OPERACION}/arreglos/{arreglo['id']}/resolver", json={"reparado_por": "Plomería Sosa", "costo": 15000}
    )
    assert resp.status_code == 200, resp.text
    await db.refresh(habitacion)
    assert habitacion.estado == "Libre"
    evento = (
        (await db.execute(select(EventoHabitacion).order_by(EventoHabitacion.id.desc()).limit(1))).scalars().one()
    )
    assert evento.origen == "ARREGLO"


async def test_con_otro_arreglo_abierto_no_se_habilita(client, db):
    uno = await _reportar(client, fuera_de_servicio=True)
    await _reportar(client, rubro="ELECTRICIDAD", descripcion="Luz del baño")
    await client.post(f"{OPERACION}/arreglos/{uno['id']}/resolver", json={"reparado_por": "Sosa"})
    habitacion = await db.get(Habitacion, 1)
    await db.refresh(habitacion)
    assert habitacion.estado == "Mantenimiento"


async def test_ocupada_no_queda_fuera_de_servicio(client):
    await _turno(client)
    datos = {"habitacion_id": 1, "rubro": "AIRE", "descripcion": "No enfría", "fuera_de_servicio": True}
    resp = await client.post(f"{OPERACION}/arreglos", json=datos)
    assert resp.status_code == 409 and "trasladá" in resp.json()["detail"]


async def test_resolver_pide_quien_lo_reparo_y_se_hace_una_vez(client):
    arreglo = await _reportar(client)
    ruta = f"{OPERACION}/arreglos/{arreglo['id']}/resolver"
    assert (await client.post(ruta, json={"reparado_por": "   "})).status_code == 422
    assert (await client.post(ruta, json={"reparado_por": "Sosa"})).status_code == 200
    assert (await client.post(ruta, json={"reparado_por": "Otro"})).status_code == 409


async def test_el_conserje_carga_el_costo_y_no_lo_ve(client, gerencia):
    arreglo = await _reportar(client)
    resuelto = (
        await client.post(
            f"{OPERACION}/arreglos/{arreglo['id']}/resolver", json={"reparado_por": "Sosa", "costo": 15000}
        )
    ).json()
    assert resuelto["costo"] is None
    assert (await client.get(f"{OPERACION}/arreglos")).json()[0]["costo"] is None
    assert (await gerencia.get(f"{OPERACION}/arreglos")).json()[0]["costo"] == 15000


async def test_el_conserje_no_cambia_el_costo_y_la_gerencia_si(client, gerencia):
    arreglo = await _reportar(client)
    ruta = f"{OPERACION}/arreglos/{arreglo['id']}"
    assert (await client.patch(f"{ruta}/costo", json={"costo": 1})).status_code == 403
    # Mientras no se resolvió no hay costo que corregir.
    assert (await gerencia.patch(f"{ruta}/costo", json={"costo": 1})).status_code == 409
    await client.post(f"{ruta}/resolver", json={"reparado_por": "Sosa"})
    assert (await gerencia.patch(f"{ruta}/costo", json={"costo": 22000})).json()["costo"] == 22000


async def test_el_tablero_suma_por_rubro_y_habitacion(client, gerencia):
    for costo in (10000, 5000):
        arreglo = await _reportar(client)
        await client.post(
            f"{OPERACION}/arreglos/{arreglo['id']}/resolver", json={"reparado_por": "Sosa", "costo": costo}
        )
    tablero = (await gerencia.get(f"{OPERACION}/tablero")).json()["arreglos"]
    assert tablero["costo_total"] == 15000 and tablero["por_rubro"][0]["cantidad"] == 2
    assert tablero["por_habitacion"][0]["numero"] == 1


async def test_el_costo_no_mueve_la_caja(client, gerencia):
    arreglo = await _reportar(client)
    await client.post(f"{OPERACION}/arreglos/{arreglo['id']}/resolver", json={"reparado_por": "Sosa", "costo": 9000})
    resultado = (await client.post(f"{GUARDIAS}/actual/arqueo", json=ARQUEO)).json()
    assert resultado["total_sistema"] == 0


# --- Traslado --------------------------------------------------------------------------------------------------------


async def test_el_turno_conserva_todo_al_trasladarse(client, db):
    turno = await _turno(client)
    consumo = await client.post(f"/api/v1/turnos/{turno['id']}/consumos", json={"articulo_id": 1, "cantidad": 1})
    assert consumo.status_code == 201, consumo.text
    ticket = (await client.get(f"/api/v1/turnos/{turno['id']}/ticket")).json()

    resp = await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "CLIENTE"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["origen_queda"] == "En Limpieza"

    actualizado = (await db.execute(select(Turno).where(Turno.id == uuid.UUID(turno["id"])))).scalars().one()
    assert actualizado.habitacion_id == 2
    assert actualizado.hora_inicio.isoformat()[:19] == turno["hora_inicio"][:19]
    assert (await client.get(f"/api/v1/turnos/{turno['id']}/ticket")).json()["direccion"] == ticket["direccion"]
    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["total_consumos"] > 0

    habitaciones = {h["id"]: h for h in (await client.get("/api/v1/habitaciones/")).json()}
    assert habitaciones[1]["estado"] == "En Limpieza" and habitaciones[2]["estado"] == "Ocupada"
    assert habitaciones[2]["turno_activo"]["id"] == turno["id"]


async def test_a_una_habitacion_mas_cara_conserva_la_tarifa(client, db):
    turno = await _turno(client)
    suite = CategoriaHabitacion(nombre="Suite", color="#123456", orden=2)
    db.add(suite)
    await db.flush()
    db.add(Tarifa(nombre="Suite", categoria_id=suite.id, tarifa_base=20000, estadia_base_min=120, tolerancia_min=0,
                  fraccion_min=30, tarifa_fraccion=5000, vigente=True))
    cara = Habitacion(numero=9, estado="Libre", categoria_id=suite.id)
    db.add(cara)
    await db.commit()
    datos = {"habitacion_id": cara.id, "motivo": "CLIENTE"}
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json=datos)).status_code == 200
    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["tarifa_base"] == 8000 and resumen["total_general"] == 8000


async def test_por_una_falla_queda_en_mantenimiento_con_su_arreglo(client, db):
    turno = await _turno(client)
    datos = {"habitacion_id": 2, "motivo": "FALLA", "rubro": "AIRE", "descripcion": "No enfría"}
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json=datos)
    assert resp.status_code == 200, resp.text
    arreglo = (await db.execute(select(Arreglo))).scalars().one()
    assert arreglo.habitacion_id == 1 and arreglo.estado == "Abierto" and arreglo.tipo == "FALLA"
    habitacion = await db.get(Habitacion, 1)
    await db.refresh(habitacion)
    assert habitacion.estado == "Mantenimiento"


async def test_una_falla_pide_saber_que_fallo(client):
    turno = await _turno(client)
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "FALLA"})
    assert resp.status_code == 422


async def test_solo_a_una_habitacion_libre(client):
    turno = await _turno(client)
    await _turno(client, 2)
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "OTRO"})
    assert resp.status_code == 409
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 1, "motivo": "OTRO"})
    assert resp.status_code == 409


async def test_un_turno_cerrado_no_se_traslada(client):
    turno = await _turno(client)
    cobro = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
    assert (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=cobro)).status_code == 200
    resp = await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "OTRO"})
    assert resp.status_code == 409


async def test_sin_guardia_no_se_traslada(client, otro_conserje):
    turno = await _turno(client)
    resp = await otro_conserje.post(
        f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "OTRO"}
    )
    assert resp.status_code == 409


async def test_la_linea_de_tiempo_reparte_el_turno(client, db):
    turno = await _turno(client)
    await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "OTRO"})
    assert len(list((await db.execute(select(TrasladoTurno))).scalars())) == 1
    linea = await rotacion.linea_de_tiempo(db)
    por_habitacion = {f["numero"]: f["tramos"] for f in linea["habitaciones"]}
    assert [t["tipo"] for t in por_habitacion[2]] == ["ocupada"]
    # Es un solo turno, aunque ocupó dos habitaciones.
    assert linea["resumen"]["turnos"] == 1


async def test_un_turno_trasladado_se_cobra_en_su_nueva_habitacion(client):
    turno = await _turno(client)
    await client.post(f"/api/v1/turnos/{turno['id']}/trasladar", json={"habitacion_id": 2, "motivo": "OTRO"})
    cobro = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
    constancia = (await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=cobro)).json()
    assert constancia["habitacion_numero"] == 2
    habitaciones = {h["id"]: h["estado"] for h in (await client.get("/api/v1/habitaciones/")).json()}
    assert habitaciones[2] == "En Limpieza"


# --- Mot -------------------------------------------------------------------------------------------------------------


async def _preguntar(cliente, texto: str) -> dict:
    resp = await cliente.post("/api/v1/asistente/pregunta", json={"texto": texto})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_mot_traslada_con_confirmacion(client):
    await _turno(client)
    datos = await _preguntar(client, "trasladá la 1 a la 2")
    confirmacion = datos["confirmacion"]
    assert confirmacion["tipo"] == "traslado" and confirmacion["habitacion_id"] == 2
    # Nunca lo hace por su cuenta.
    habitaciones = {h["id"]: h["estado"] for h in (await client.get("/api/v1/habitaciones/")).json()}
    assert habitaciones[1] == "Ocupada"


@pytest.mark.parametrize(
    ("orden", "espera"),
    [
        ("trasladá la 2 a la 1", "no tiene un turno"),
        ("trasladá la 1 a la 3", "no está disponible"),
        ("trasladá la 1 a la 40", "No encuentro"),
        ("trasladá la 1 a la 2 porque no anda el aire", "desde la habitación"),
    ],
)
async def test_mot_avisa_lo_que_no_se_puede_trasladar(client, orden, espera):
    await _turno(client)
    datos = await _preguntar(client, orden)
    assert datos["confirmacion"] is None and espera in datos["respuesta"]


async def test_mot_no_le_dice_la_ropa_a_quien_cuenta_a_ciegas(client):
    await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())
    for pregunta in ("¿cuántas toallas hay?", "¿faltan sábanas?", "¿hay ropa?"):
        datos = await _preguntar(client, pregunta)
        assert "66" not in datos["respuesta"] and "a ciegas" in datos["respuesta"], pregunta


async def test_mot_le_cuenta_la_ropa_a_la_gerencia(client, gerencia, otro_conserje):
    await _cerrar_con_conteo(client, _ropa())
    await otro_conserje.post(f"{GUARDIAS}/", json=_ropa(toallas=(38, 10, 16)))
    datos = await _preguntar(gerencia, "¿faltan toallas?")
    assert datos["intencion"] == "ropa" and "64 toallas" in datos["respuesta"] and "faltaron 2" in datos["respuesta"]


async def test_mot_dice_que_arreglos_hay_sin_el_costo(client, gerencia):
    arreglo = await _reportar(client, rubro="AIRE", descripcion="No enfría")
    datos = await _preguntar(client, "¿qué arreglos hay abiertos?")
    assert "No enfría" in datos["respuesta"]
    await client.post(f"{OPERACION}/arreglos/{arreglo['id']}/resolver", json={"reparado_por": "Sosa", "costo": 15000})
    assert "No hay arreglos" in (await _preguntar(client, "¿qué arreglos hay abiertos?"))["respuesta"]
    assert (await _preguntar(client, "¿cuánto gastamos en arreglos?"))["intencion"] == "fuera_de_alcance"
    datos = await _preguntar(gerencia, "¿cuánto gastamos en arreglos?")
    assert datos["intencion"] == "arreglos" and "$15.000" in datos["respuesta"]


@pytest.mark.parametrize(
    ("pregunta", "tema"),
    [
        ("¿cómo traslado un turno?", "Trasladar un turno"),
        ("¿cómo hago el recuento de ropa?", "Contar las toallas"),
        ("¿cómo anoto la ropa de la lavandería?", "ropa que entra"),
        ("¿cómo registro una falla?", "Registrar una falla"),
    ],
)
async def test_mot_explica_como_se_hace(client, pregunta, tema):
    datos = await _preguntar(client, pregunta)
    assert tema in datos["respuesta"] and datos["pasos"], datos


async def test_mot_ya_no_dice_que_no_se_puede_trasladar(client):
    datos = await _preguntar(client, "el cliente quiere cambiarse de habitación, ¿qué hago?")
    assert "Trasladar" in datos["respuesta"] and "no se traslada" not in datos["respuesta"]


async def test_mot_explica_que_es(client):
    assert "recibe quien entra" in (await _preguntar(client, "¿qué es el traspaso?"))["respuesta"]


# --- Inteligencia e historial ----------------------------------------------------------------------------------------


async def test_las_fallas_repetidas_y_la_ropa_llegan_a_inteligencia(db, cliente_como):
    await generar_historial(db, dias=42, semilla=3, intensidad=2.0, habitacion_poco_usada=2)
    cantidades = await agregar_operacion(db, 3, 2)
    await db.commit()
    assert cantidades["traspasos"] > 0 and cantidades["recuentos"] == cantidades["traspasos"] * 4
    assert cantidades["arreglos"] >= 3

    gerencia = await cliente_como("gerencia")
    tablero = (await gerencia.get(f"{OPERACION}/tablero")).json()
    resumen = {r["prenda"]: r for r in tablero["ropa"]["resumen"]}
    assert resumen["TOALLAS"]["total"] > 0
    assert tablero["traspasos"] and tablero["traspasos"][0]["resumen"]["ropa_recibida"]
    # Lo que salió a la lavandería no es un faltante: las sábanas no pierden nada en el ejemplo.
    assert resumen["SABANAS"]["faltantes"] == 0 and resumen["TOALLAS"]["faltantes"] > 0

    alertas = (await gerencia.get("/api/v1/inteligencia/tablero")).json()["alertas"]
    titulos = " · ".join(a["titulo"] for a in alertas)
    assert "toallas" in titulos and "Habitación 2: 3 fallas" in titulos


async def test_la_alerta_de_ropa_no_acusa_por_una_toalla(client, otro_conserje, gerencia):
    await _cerrar_con_conteo(client, _ropa())
    await otro_conserje.post(f"{GUARDIAS}/", json=_ropa(toallas=(39, 10, 16)))
    alertas = (await gerencia.get("/api/v1/inteligencia/tablero")).json()["alertas"]
    assert not [a for a in alertas if "toallas" in a["titulo"]]


# --- Cómo se cuenta la ropa (migración 017) --------------------------------------------------------------------------

JUNTO = {"conteos": [{"prenda": "TOALLAS", "total": 66}, {"prenda": "SABANAS", "total": 52}]}


async def _todo_junto(gerencia) -> None:
    resp = await gerencia.patch(f"{OPERACION}/ropa/forma", json={"por_estado": False})
    assert resp.status_code == 200, resp.text


async def test_por_defecto_se_cuenta_por_estado(client):
    assert (await client.get(f"{GUARDIAS}/traspaso")).json()["ropa_por_estado"] is True
    resp = await client.post(f"{GUARDIAS}/actual/ropa", json=JUNTO)
    assert resp.status_code == 422 and "por separado" in resp.json()["detail"]


async def test_la_gerencia_elige_contar_todo_junto(client, gerencia, db):
    assert (await client.patch(f"{OPERACION}/ropa/forma", json={"por_estado": False})).status_code == 403
    await _todo_junto(gerencia)
    assert (await client.get(f"{GUARDIAS}/traspaso")).json()["ropa_por_estado"] is False

    resp = await client.post(f"{GUARDIAS}/actual/ropa", json=JUNTO)
    assert resp.status_code == 201, resp.text
    filas = list((await db.execute(select(RopaConteo).where(RopaConteo.momento == "CIERRE"))).scalars())
    assert {f.prenda: f.total for f in filas} == {"TOALLAS": 66, "SABANAS": 52}
    assert all(f.limpias is None and f.sucias is None and f.en_habitaciones is None for f in filas)

    cambios = await db.execute(select(RegistroActividad).where(RegistroActividad.accion == "ROPA_FORMA"))
    cambio = cambios.scalars().one()
    assert "todo junto" in cambio.descripcion and cambio.categoria == "OPERACION"


async def test_todo_junto_sigue_siendo_obligatorio_y_a_ciegas(client, gerencia, exige_recuento):
    await _todo_junto(gerencia)
    assert (await client.post(f"{GUARDIAS}/actual/arqueo", json=ARQUEO)).status_code == 409
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json={"conteos": [JUNTO["conteos"][0]]})).status_code == 422
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json={"conteos": [{"prenda": "TOALLAS"}]})).status_code == 422
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=JUNTO)).status_code == 201
    assert (await client.get(f"{GUARDIAS}/traspaso")).json()["ropa"] is None
    assert (await client.post(f"{GUARDIAS}/actual/arqueo", json=ARQUEO)).status_code == 201


async def test_cambiar_la_forma_no_corta_el_control(client, gerencia, otro_conserje, db):
    """Se cerró contando por estado y se abre contando todo junto: se compara el total."""
    await _cerrar_con_conteo(client, _ropa())
    await _todo_junto(gerencia)
    pantalla = (await otro_conserje.get(f"{GUARDIAS}/traspaso")).json()
    toallas = next(p for p in pantalla["ropa"] if p["prenda"] == "TOALLAS")
    assert pantalla["ropa_por_estado"] is False and toallas["total"] == 66 and toallas["limpias"] == 40

    recibe = {"conteos": [{"prenda": "TOALLAS", "total": 64}, {"prenda": "SABANAS", "total": 52}]}
    assert (await otro_conserje.post(f"{GUARDIAS}/", json=recibe)).status_code == 201
    aviso = (
        (await db.execute(select(RegistroActividad).where(RegistroActividad.accion == "ROPA_DIFERENCIA")))
        .scalars()
        .one()
    )
    assert "Toallas: faltan 2" in aviso.descripcion

    tablero = (await gerencia.get(f"{OPERACION}/tablero")).json()["ropa"]
    assert tablero["por_estado"] is False
    toallas = next(r for r in tablero["resumen"] if r["prenda"] == "TOALLAS")
    assert toallas["total"] == 64 and toallas["limpias"] is None and toallas["faltantes_del_mes"] == 2


async def test_todo_junto_acepta_las_partes_y_guarda_el_total(client, gerencia, db):
    await _todo_junto(gerencia)
    assert (await client.post(f"{GUARDIAS}/actual/ropa", json=_ropa())).status_code == 201
    fila = (await db.execute(select(RopaConteo).where(RopaConteo.prenda == "TOALLAS"))).scalars().one()
    assert fila.total == 66 and fila.limpias is None


async def test_el_conserje_ve_lo_que_anoto_en_su_guardia(client, otro_conserje):
    assert (await client.get(f"{OPERACION}/ropa/movimientos")).json() == []
    for tipo, cantidad in (("LAVANDERIA_SALE", 12), ("BAJA", 1)):
        movimiento = {"prenda": "SABANAS", "tipo": tipo, "cantidad": cantidad}
        assert (await client.post(f"{OPERACION}/ropa/movimientos", json=movimiento)).status_code == 201
    propios = (await client.get(f"{OPERACION}/ropa/movimientos")).json()
    assert [(m["tipo"], m["signo"], m["cantidad"]) for m in propios] == [
        ("Baja por rotura", -1, 1),
        ("Salió a la lavandería", -1, 12),
    ]
    # Quien no tiene la guardia no ve los de otro.
    assert (await otro_conserje.get(f"{OPERACION}/ropa/movimientos")).json() == []


async def test_la_gerencia_ve_un_renglon_por_recuento_y_donde_falto(client, gerencia, otro_conserje):
    await _cerrar_con_conteo(client, _ropa())
    await otro_conserje.post(f"{GUARDIAS}/", json=_ropa(toallas=(38, 10, 16)))
    await _cerrar_con_conteo(otro_conserje, _ropa(toallas=(37, 10, 16)))
    ropa = (await gerencia.get(f"{OPERACION}/tablero")).json()["ropa"]

    ultimo = ropa["recuentos"][0]
    assert ultimo["momento"] == "CIERRE" and ultimo["operador"] == "Conserje Dos"
    assert [(p["prenda"], p["total"], p["diferencia"]) for p in ultimo["prendas"]] == [
        ("TOALLAS", 63, -1),
        ("SABANAS", 52, 0),
    ]
    assert len(ropa["recuentos"]) == 3

    personas = ropa["por_persona"]
    assert personas["en_guardia"] == [{"operador": "Conserje Dos", "unidades": 1, "recuentos": 1}]
    assert personas["en_cambio"] == [
        {"dejo": "Conserje Uno", "recibio": "Conserje Dos", "unidades": 2, "recuentos": 1}
    ]


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿cómo elijo cómo se cuenta la ropa?",
        "quiero que las toallas se cuenten todas juntas",
        "¿se pueden contar las sábanas por separado?",
    ],
)
async def test_mot_explica_como_elegir_la_forma(gerencia, client, pregunta):
    datos = await _preguntar(gerencia, pregunta)
    assert "Elegir cómo se cuenta la ropa" in datos["respuesta"] and datos["pasos"], datos
    # Al conserje le explica cómo contar: elegir la forma es de la gerencia.
    conserje = await _preguntar(client, pregunta)
    assert "Elegir cómo se cuenta" not in conserje["respuesta"]


async def test_el_historial_de_ejemplo_respeta_la_forma_del_motel(db, gerencia):
    await generar_historial(db, dias=14, semilla=5, intensidad=1.5)
    await _todo_junto(gerencia)
    cantidades = await agregar_operacion(db, 5)
    await db.commit()
    filas = list((await db.execute(select(RopaConteo))).scalars())
    assert len(filas) == cantidades["recuentos"] > 0
    assert all(f.limpias is None and f.total > 0 for f in filas)
    resumen = (await gerencia.get(f"{OPERACION}/tablero")).json()["ropa"]["resumen"]
    assert all(r["limpias"] is None and r["total"] > 0 for r in resumen)
