"""Gemelo del motel: repetir las llegadas reales con otra limpieza, otras habitaciones u otro precio."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.habitacion import Habitacion
from app.services import ayuda
from app.services import gemelo as simulador
from app.services import inteligencia as ia
from app.services.gemelo import Escenario, Llegada, aplicar_precio, repetir
from scripts.cargar_historial import generar_historial

GEMELO = "/api/v1/inteligencia/gemelo"
INICIO = datetime(2026, 10, 1, 10, tzinfo=UTC)


def _llegada(
    minutos_desde: float, categoria: int = 1, dura: float = 60, limpia: float = 30, real: bool = True
) -> Llegada:
    return Llegada(INICIO + timedelta(minutes=minutos_desde), categoria, dura, limpia, 1000.0, 100.0, real, 0.5)


def test_una_habitacion_no_atiende_dos_clientes_a_la_vez():
    llegadas = [_llegada(0), _llegada(30)]
    corrida = repetir(llegadas, {1: 1}, INICIO - timedelta(days=1))
    assert (corrida.turnos, corrida.perdidos, corrida.ingresos) == (1, 1, 1100.0)
    assert corrida.perdidos_por_hora[10] == 1


def test_la_limpieza_mas_rapida_deja_entrar_al_que_llega_antes():
    llegadas = [_llegada(0), _llegada(80)]  # la habitación se libera a los 90 minutos, con 30 de limpieza
    assert repetir(llegadas, {1: 1}, INICIO - timedelta(days=1)).perdidos == 1
    assert repetir(llegadas, {1: 1}, INICIO - timedelta(days=1), factor_limpieza=0.5).perdidos == 0


def test_una_habitacion_mas_atiende_al_que_se_iba():
    llegadas = [_llegada(0), _llegada(30)]
    assert repetir(llegadas, {1: 2}, INICIO - timedelta(days=1)).turnos == 2


def test_un_cliente_solo_entra_a_su_categoria_salvo_que_no_tenga():
    inicio = INICIO - timedelta(days=1)
    assert repetir([_llegada(0, categoria=2)], {1: 1, 2: 0}, inicio).perdidos == 1
    sin_categoria = Llegada(INICIO, None, 60, 30, 1000.0, 0.0, False, 0.5)
    assert repetir([sin_categoria], {1: 0, 2: 1}, inicio).turnos == 1


def test_subir_el_precio_paga_mas_y_algunos_no_entran():
    llegadas = [Llegada(INICIO + timedelta(hours=i), 1, 60, 30, 1000.0, 100.0, True, i / 100) for i in range(100)]
    # Todas son horas flojas: con +10% y elasticidad -1,6 se va cerca del 16%.
    subida = aplicar_precio(llegadas, Escenario(precio_pct=10), set())
    assert len(subida) == pytest.approx(84, abs=1)
    assert subida[0].estadia == pytest.approx(1100) and subida[0].consumos == 100.0
    # Bajarlo trae clientes nuevos.
    bajada = aplicar_precio(llegadas, Escenario(precio_pct=-10), set())
    assert len(bajada) == pytest.approx(116, abs=1) and bajada[0].estadia == pytest.approx(900)
    # Solo en las horas pico: en horas flojas nada cambia.
    assert aplicar_precio(llegadas, Escenario(precio_pct=10, precio_cuando="pico"), set()) == llegadas


@pytest.fixture
async def gerencia(db, cliente_como):
    await generar_historial(db, dias=40, semilla=3, intensidad=2.5)
    return await cliente_como("gerencia")


async def _probar(cliente, **parametros) -> dict:
    resp = await cliente.post(GEMELO, json=parametros)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_sin_cambios_no_cambia_nada_y_reproduce_el_pasado(gerencia):
    datos = await _probar(gerencia)
    assert datos["disponible"] and datos["base"] == datos["escenario"]
    assert datos["diferencia"]["turnos"] == 0 and datos["diferencia"]["ingresos"] == 0
    assert "condiciones de hoy" in datos["conclusion"]
    # El modelo reproduce casi todos los turnos que se atendieron de verdad.
    assert datos["calibracion"]["coincidencia"] >= 0.9
    assert datos["base"]["perdidos"] > 0 and 18 <= datos["limpieza_actual"] <= 40


async def test_mas_lugar_atiende_mas_y_pierde_menos(gerencia):
    base = await _probar(gerencia)
    rapida = await _probar(gerencia, limpieza_min=10)
    assert rapida["diferencia"]["turnos"] > 0 and rapida["diferencia"]["perdidos"] < 0
    assert rapida["diferencia"]["ingresos_por_mes"] > 0
    categoria = base["categorias"][0]["categoria_id"]
    mas = await _probar(gerencia, habitaciones={str(categoria): 2})
    assert mas["diferencia"]["perdidos"] <= 0 and mas["categorias"][0]["cambio"] == 2
    sumadas = sum(c["actuales"] + c["cambio"] for c in mas["categorias"])
    assert sumadas == sum(c["actuales"] for c in base["categorias"]) + 2
    assert sum(h["base"] for h in rapida["por_hora"]) == rapida["base"]["perdidos"]
    assert sum(h["escenario"] for h in rapida["por_hora"]) == rapida["escenario"]["perdidos"]


async def test_es_repetible_y_no_toca_nada(gerencia, db):
    antes = [(h.id, h.estado) for h in (await db.execute(select(Habitacion))).scalars()]
    primero = await _probar(gerencia, limpieza_min=20, precio_pct=10, precio_cuando="pico")
    segundo = await _probar(gerencia, limpieza_min=20, precio_pct=10, precio_cuando="pico")
    assert primero == segundo
    assert any("supuesto" in s for s in primero["supuestos"])
    assert antes == [(h.id, h.estado) for h in (await db.execute(select(Habitacion))).scalars()]


async def test_sacar_habitaciones_no_deja_capacidad_negativa(gerencia):
    base = await _probar(gerencia)
    categoria = base["categorias"][0]
    datos = await _probar(gerencia, habitaciones={str(categoria["categoria_id"]): -99})
    assert datos["diferencia"]["turnos"] < 0


async def test_valida_los_parametros_y_solo_la_gerencia(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(GEMELO, json={"precio_pct": 200})).status_code == 422
    assert (await gerencia.post(GEMELO, json={"precio_cuando": "nunca"})).status_code == 422
    assert (await client.post(GEMELO, json={})).status_code == 403


async def test_sin_historia_lo_dice(cliente_como):
    gerencia = await cliente_como("gerencia")
    datos = await _probar(gerencia)
    assert datos["disponible"] is False and datos["categorias"]


async def test_no_mira_la_guardia_en_curso(db, client):
    """RN-RES-03: lo cobrado en la guardia abierta no entra hasta que se arquee."""
    await generar_historial(db, dias=14, semilla=3)
    ctx = await ia.contexto(db)
    antes = len(simulador.llegadas_de(ctx, 30)[0])
    turno = (await client.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})).json()
    cobro = {"pagos": [{"monto": 8000, "medio_pago": "EFECTIVO"}]}
    await client.post(f"/api/v1/turnos/{turno['id']}/cerrar", json=cobro)
    assert len(simulador.llegadas_de(await ia.contexto(db), 30)[0]) == antes


async def _preguntar(cliente, texto: str) -> dict:
    resp = await cliente.post("/api/v1/asistente/pregunta", json={"texto": texto})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿qué pasa si la limpieza tarda 20 minutos?",
        "que pasaria si agrego una vip",
        "¿qué pasa si subo la tarifa 10%?",
        "que pasa si la limpieza tarda 5 minutos menos",
    ],
)
async def test_el_asistente_prueba_escenarios(gerencia, pregunta):
    datos = await _preguntar(gerencia, pregunta)
    assert datos["intencion"] == "gemelo", datos
    assert datos["tabla"]["columnas"][1] == "Hoy" and "reproduce" in datos["detalle"]


async def test_el_asistente_entiende_el_gemelo_y_la_huella(gerencia, client):
    pide = await _preguntar(gerencia, "simulá un cambio")
    assert pide["intencion"] == "gemelo" and pide["sugerencias"]
    assert (await _preguntar(gerencia, "¿qué es el gemelo del motel?"))["intencion"] == "definicion:gemelo"
    assert (await _preguntar(gerencia, "¿qué es la huella de un comprobante?"))["intencion"] == "definicion:huella"
    assert (await _preguntar(gerencia, "como verifico un comprobante"))["intencion"] == "ayuda:verificar_comprobante"
    assert (await _preguntar(gerencia, "como uso el gemelo"))["intencion"] == "ayuda:usar_gemelo"
    # «Qué pasa si…» sobre otra cosa sigue siendo ayuda, no una simulación.
    assert (await _preguntar(gerencia, "que pasa si se corta internet"))["intencion"] == "ayuda:conexion"
    # Al conserje no le da importes.
    assert (await _preguntar(client, "que pasa si agrego una vip"))["intencion"] == "fuera_de_alcance"


def test_las_preguntas_sugeridas_siguen_en_las_pantallas():
    assert "¿Cómo verifico un comprobante?" in ayuda.PANTALLAS["gerencia"].preguntas_gerencia
