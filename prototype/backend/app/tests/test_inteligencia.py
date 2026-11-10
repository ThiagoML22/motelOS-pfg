"""Historial de demostración e inteligencia local de la gerencia (pronóstico, alertas, sugerencias y asistente)."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.pago import Pago
from app.models.turno import Turno
from app.services import inteligencia as ia
from app.services.asistente import interpretar_periodo, normalizar, responder
from app.services.billing_service import calcular_sobreturno
from app.services.liquidacion import con_zona
from app.tests.conftest import CLAVE_OTRO_MOTEL, ESTABLECIMIENTO_OTRO, nuevo_cliente
from scripts.cargar_historial import generar_historial, inicio_de_franja

TABLERO = "/api/v1/inteligencia/tablero"
PREGUNTA = "/api/v1/inteligencia/pregunta"


@pytest.fixture
async def historial(db):
    return await generar_historial(db, dias=42, semilla=3)


# --- Historial de demostración ----------------------------------------------------------------------------------------


async def test_el_historial_respeta_las_reglas_de_caja(db, historial):
    assert historial["turnos"] > 200 and historial["guardias"] == 42 * 3 and historial["arqueos"] == 42 * 3
    guardias = {g.id: g for g in (await db.execute(select(Guardia))).scalars()}
    assert all(g.estado == "Cerrada" for g in guardias.values())
    turnos = {t.id: t for t in (await db.execute(select(Turno))).scalars()}
    assert all(t.estado == "FINALIZADO" and t.hora_fin > t.hora_inicio for t in turnos.values())
    for pago in (await db.execute(select(Pago))).scalars():
        turno = turnos[pago.turno_id]
        # RN-EXI-03 y RN-DER-04: cobrado completo, en la guardia que atendía a la hora del cobro, por su conserje.
        assert pago.monto == turno.total_general and pago.operador_id == turno.operador_cierre_id
        guardia = guardias[pago.guardia_id]
        assert pago.operador_id == guardia.operador_id
        assert con_zona(guardia.abierta_en) <= con_zona(pago.created_at) <= con_zona(guardia.cerrada_en)
    for arqueo in (await db.execute(select(ArqueoCaja))).scalars():
        # RN-DER-03, igual que el trigger calcular_arqueo.
        assert arqueo.total_sistema == arqueo.sistema_efectivo + arqueo.sistema_posnet + arqueo.sistema_mercado_pago
        assert arqueo.diferencia == arqueo.total_declarado - arqueo.total_sistema
        assert arqueo.categoria == (
            "Correcto" if arqueo.diferencia == 0 else "Faltante" if arqueo.diferencia < 0 else "Sobrante"
        )


async def test_el_historial_liquida_con_la_tarifa_y_no_pisa_habitaciones(db, historial):
    turnos = list((await db.execute(select(Turno).order_by(Turno.habitacion_id, Turno.hora_inicio))).scalars())
    for anterior, siguiente in zip(turnos, turnos[1:], strict=False):
        if anterior.habitacion_id == siguiente.habitacion_id:
            assert con_zona(siguiente.hora_inicio) >= con_zona(anterior.hora_fin)  # RN-EXI-01
    for t in turnos[:50]:
        minutos = con_zona(t.hora_fin) - con_zona(t.hora_inicio)
        assert t.total_sobreturno == calcular_sobreturno(minutos)  # tarifa estándar de las pruebas
        assert t.total_general == t.tarifa_base + t.total_sobreturno + t.total_consumos


def test_inicio_de_franja():
    zona = ZoneInfo(settings.ZONA_HORARIA)
    assert inicio_de_franja(datetime(2026, 11, 3, 5, 30, tzinfo=zona), zona).hour == 22
    assert inicio_de_franja(datetime(2026, 11, 3, 5, 30, tzinfo=zona), zona).day == 2
    assert inicio_de_franja(datetime(2026, 11, 3, 13, 59, tzinfo=zona), zona).hour == 6
    assert inicio_de_franja(datetime(2026, 11, 3, 23, 0, tzinfo=zona), zona).hour == 22


# --- Tablero ----------------------------------------------------------------------------------------------------------


async def test_el_tablero_de_la_gerencia(cliente_como, historial):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.get(TABLERO)
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert len(datos["pronostico"]["horas"]) == 24 and datos["pronostico"]["total"] > 0
    assert len(datos["serie"]) == 30 and sum(d["turnos"] for d in datos["serie"]) > 0
    assert len(datos["demanda"]["valores"]) == 7 and all(len(f) == 24 for f in datos["demanda"]["valores"])
    assert datos["resumen"]["titular"] and len(datos["resumen"]["puntos"]) >= 4
    assert datos["indicadores"]["turnos_7d"] > 0 and datos["indicadores"]["habitaciones"] == 3
    assert {s["accion"] for s in datos["sugerencias"]} <= {"subir", "bajar", "estadia", "mantener"}
    for s in datos["sugerencias"]:
        assert (s["propuesta"] is None) == (s["impacto_mensual"] is None)
    assert {r["urgencia"] for r in datos["reposicion"]} <= {"alta", "media", "baja", "sin_movimiento"}
    assert abs(sum(m["parte"] for m in datos["medios_de_pago"]) - 1) < 0.01
    assert datos["pronostico"]["precision"] is not None


async def test_solo_la_gerencia_ve_la_inteligencia(cliente_como, historial):
    conserje = await cliente_como("conserje1")
    assert (await conserje.get(TABLERO)).status_code == 403
    assert (await conserje.post(PREGUNTA, json={"texto": "¿cuánto facturamos?"})).status_code == 403


async def test_otro_motel_no_ve_el_historial(historial):
    async with nuevo_cliente() as otro:
        login = {"establecimiento": ESTABLECIMIENTO_OTRO, "usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL}
        assert (await otro.post("/api/v1/auth/login", json=login)).status_code == 200
        datos = (await otro.get(TABLERO)).json()
        assert datos["indicadores"]["turnos_7d"] == 0 and datos["pronostico"]["horas"] == []
        assert "Todavía no hay" in datos["resumen"]["titular"]


async def test_rn_res_03_la_guardia_abierta_no_entra_en_el_analisis(cliente_como, historial):
    gerencia = await cliente_como("gerencia")
    antes = (await gerencia.get(TABLERO)).json()["indicadores"]
    respuesta_antes = (await gerencia.post(PREGUNTA, json={"texto": "cuanto facturamos hoy"})).json()

    conserje = await cliente_como("conserje1")
    assert (await conserje.post("/api/v1/guardias/")).status_code == 201
    turno = (await conserje.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    resumen = (await conserje.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    cobro = {"pagos": [{"monto": resumen["saldo_pendiente"], "medio_pago": "EFECTIVO"}]}
    assert (await conserje.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=cobro)).status_code == 200

    despues = (await gerencia.get(TABLERO)).json()["indicadores"]
    assert despues["ingresos_7d"] == antes["ingresos_7d"] and despues["turnos_7d"] == antes["turnos_7d"]
    respuesta = (await gerencia.post(PREGUNTA, json={"texto": "cuanto facturamos hoy"})).json()
    assert "guardia en curso" in respuesta["respuesta"]
    assert respuesta["respuesta"].split(" No incluye")[0] == respuesta_antes["respuesta"].split(" No incluye")[0]


# --- Asistente --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pregunta", "intencion"),
    [
        ("¿Cuánto facturamos la semana pasada?", "ingresos"),
        ("cuantos turnos hubo ayer", "turnos"),
        ("¿Cuántos turnos esperamos mañana?", "pronostico"),
        ("¿Qué artículos hay que reponer?", "stock"),
        ("¿Quién tuvo más faltantes este mes?", "caja"),
        ("¿A qué hora hay más demanda los sábados?", "horas"),
        ("¿Cuál es la habitación menos usada?", "habitaciones"),
        ("cuanto dura una estadia promedio", "estadia"),
        ("que porcentaje de ocupacion tuvimos", "ocupacion"),
        ("como pagan los clientes, efectivo o tarjeta", "medios"),
        ("qué es lo más vendido del minibar", "articulos"),
        ("¿cómo venimos?", "resumen"),
        ("ayuda", "ayuda"),
        ("¿de qué color es el cielo?", "desconocida"),
    ],
)
async def test_el_asistente_entiende_la_pregunta(cliente_como, historial, pregunta, intencion):
    gerencia = await cliente_como("gerencia")
    resp = await gerencia.post(PREGUNTA, json={"texto": pregunta})
    assert resp.status_code == 200, resp.text
    datos = resp.json()
    assert datos["intencion"] == intencion, datos
    assert datos["respuesta"]


async def test_el_asistente_responde_con_los_numeros_del_historial(db, historial):
    ctx = await ia.contexto(db)
    respuesta = responder(ctx, "¿cuántos turnos hubo en los últimos 30 días?")
    hoy = ctx.ahora.date()
    esperados = sum(1 for t in ctx.turnos if hoy - timedelta(days=29) <= t.fin.date() <= hoy)
    assert f"hubo {esperados} turnos" in respuesta["respuesta"]
    vip = responder(ctx, "cuanto facturo la categoria simple")
    assert "Simple" in vip["respuesta"]


def test_interpretar_periodo():
    hoy = date(2026, 11, 3)  # martes
    assert interpretar_periodo("ayer", hoy).desde == date(2026, 11, 2)
    semana = interpretar_periodo("la semana pasada", hoy)
    assert (semana.desde, semana.hasta) == (date(2026, 10, 26), date(2026, 11, 1))
    assert interpretar_periodo("ultimos 15 dias", hoy).dias == 15
    octubre = interpretar_periodo("cuanto facturamos en octubre", hoy)
    assert (octubre.desde, octubre.hasta) == (date(2026, 10, 1), date(2026, 10, 31))
    assert interpretar_periodo("los sabados", hoy).dias_semana == {5}
    assert interpretar_periodo("el sabado", hoy).desde == date(2026, 10, 31)
    assert interpretar_periodo(normalizar("¿Qué pasó el miércoles?"), hoy).desde == date(2026, 10, 28)
    assert not interpretar_periodo("cuanto facturamos", hoy).explicito


# --- Estadística de las alertas ---------------------------------------------------------------------------------------


def test_cola_binomial():
    assert ia.cola_binomial(0, 10, 0.3) == pytest.approx(1)
    assert ia.cola_binomial(10, 10, 0.5) == pytest.approx(0.5**10)
    assert ia.cola_binomial(7, 30, 0.05) < 0.01


def _contexto_con_arqueos(arqueos: list[ia.ArqueoCerrado]) -> ia.Contexto:
    zona = ZoneInfo(settings.ZONA_HORARIA)
    ahora = datetime.now(UTC).astimezone(zona)
    return ia.Contexto(
        zona=zona,
        ahora=ahora,
        corte=ahora,
        hay_guardia_abierta=False,
        turnos=[],
        arqueos=arqueos,
        ventas=[],
        cobros=[],
        habitaciones=[],
        categorias={},
        tarifas={},
        tarifas_por_id={},
        articulos=[],
        nombres={1: "Conserje Uno", 2: "Conserje Dos"},
    )


def test_la_alerta_de_faltantes_distingue_el_azar():
    ahora = datetime.now(UTC).astimezone(ZoneInfo(settings.ZONA_HORARIA))

    def arqueo(dias: int, operador: int, diferencia: float) -> ia.ArqueoCerrado:
        categoria = "Correcto" if diferencia == 0 else "Faltante" if diferencia < 0 else "Sobrante"
        return ia.ArqueoCerrado(ahora - timedelta(days=dias), operador, diferencia, categoria, "14:00")

    parejos = [arqueo(d, 1 + d % 2, -1000 if d % 10 == 0 else 0) for d in range(1, 29)]
    assert not [a for a in ia.alertas(_contexto_con_arqueos(parejos), []) if "faltantes" in a["titulo"]]

    sesgados = [arqueo(d, 1, 0) for d in range(1, 15)] + [arqueo(d, 2, -1500 if d % 3 else 0) for d in range(1, 15)]
    titulos = [a["titulo"] for a in ia.alertas(_contexto_con_arqueos(sesgados), [])]
    assert "Conserje Dos: faltantes por encima de lo normal" in titulos

    grande = [arqueo(d, 1 + d % 2, -1000 if d % 4 == 0 else 0) for d in range(1, 29)] + [arqueo(5, 2, -15000)]
    alertas = ia.alertas(_contexto_con_arqueos(grande), [])
    assert any(a["titulo"].startswith("Faltante de $15.000") and a["severidad"] == "alta" for a in alertas)


def test_formatos():
    assert ia.pesos(1234567.4) == "$1.234.567" and ia.pesos(-500) == "-$500"
    assert ia.porcentaje(0.1234, 1) == "12,3%" and ia.con_signo(-0.08) == "−8%"
    assert ia.minutos_texto(135) == "2 h 15 min" and ia.minutos_texto(45) == "45 min"
