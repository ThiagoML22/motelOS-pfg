"""Mot entiende cuando se le habla normal y razona sobre los datos.

Corre los dos bancos de frases (app/tests/banco_mot.py) contra el asistente real, con un historial de ejemplo: el
original y uno de frases nuevas que no se usaron para ajustar las reglas. Además prueba por separado cada pieza de la
comprensión (services/comprension.py) y de los razonamientos (comparar, proyectar, mejor día, «¿por qué?», «¿es
mucho?», consejos).
"""

from datetime import date

import pytest
import pytest_asyncio

from app.services import comprension, conocimiento
from app.services.asistente import interpretar_periodo, normalizar, previo_de
from app.services.ayuda import ENTRADAS
from app.tests import banco_mot
from scripts.cargar_historial import agregar_opiniones, generar_historial

PREGUNTA = "/api/v1/asistente/pregunta"
# Lo que tiene que entender de cada banco, como mínimo (con el historial de prueba, no el de la demo).
MINIMO = 0.95


def _bien(intencion: str, esperado) -> bool:
    opciones = esperado if isinstance(esperado, tuple) else (esperado,)
    return any(intencion == o or (o.endswith(":") and intencion.startswith(o)) for o in opciones)


@pytest_asyncio.fixture
async def con_historial(db):
    await generar_historial(db, dias=42, semilla=5, intensidad=2.0)
    await agregar_opiniones(db, 5)
    await db.commit()


async def _medir(client, cliente_como, frases, conversaciones) -> tuple[float, list[str]]:
    clientes = {banco_mot.C: client, banco_mot.G: await cliente_como("gerencia")}
    bien, fallas = 0, []
    for rol, frase, esperado in frases:
        datos = (await clientes[rol].post(PREGUNTA, json={"texto": frase})).json()
        if _bien(datos["intencion"], esperado):
            bien += 1
        else:
            fallas.append(f"{frase!r}: esperaba {esperado}, dio {datos['intencion']}")
    total = len(frases)
    for rol, pasos in conversaciones:
        anterior = None
        for frase, esperado in pasos:
            cuerpo = {"texto": frase}
            if anterior:
                cuerpo |= {"anterior": anterior[0], "anterior_intencion": anterior[1]}
            datos = (await clientes[rol].post(PREGUNTA, json=cuerpo)).json()
            total += 1
            if _bien(datos["intencion"], esperado):
                bien += 1
            else:
                fallas.append(f"(conversación) {frase!r}: esperaba {esperado}, dio {datos['intencion']}")
            anterior = (datos.get("pregunta_resuelta") or frase, datos["intencion"])
    return bien / total, fallas


async def test_entiende_el_banco_de_frases(client, cliente_como, con_historial):
    parte, fallas = await _medir(client, cliente_como, banco_mot.FRASES, banco_mot.CONVERSACIONES)
    assert parte >= MINIMO, "\n".join(fallas)


async def test_entiende_frases_que_no_se_usaron_para_ajustarlo(client, cliente_como, con_historial):
    parte, fallas = await _medir(client, cliente_como, banco_mot.FRASES_NUEVAS, banco_mot.CONVERSACIONES_NUEVAS)
    assert parte >= MINIMO, "\n".join(fallas)


# --- Comprensión --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dicho", "entendido"),
    [
        ("che mot decime cuanto debe la siete porfa", "cuanto debe la 7"),
        ("queria saber si hay alguna libre", "hay alguna libre"),
        ("cuanta guita entro", "cuanta plata entro"),
        ("holaaaa", "hola"),
        ("q tal la recaudacion x semana", "que tal la recaudacion por semana"),
        ("hay coca", "hay gaseosa cola"),
        ("gracias capo", "gracias capo"),
        ("sos un genio", "sos un genio"),
    ],
)
def test_preparar_lo_dicho_como_se_habla(dicho, entendido):
    assert comprension.preparar(normalizar(dicho)) == entendido


def test_un_saludo_delante_no_tapa_la_pregunta():
    assert comprension.quitar_saludo("hola mot cuanto facturamos") == ("cuanto facturamos", True)
    assert comprension.quitar_saludo("que tal estuvo la recaudacion") == ("que tal estuvo la recaudacion", False)


def test_dos_preguntas_juntas_se_separan():
    assert comprension.dividir("cuanto facturamos ayer y cuantos turnos hubo") == [
        "cuanto facturamos ayer",
        "cuantos turnos hubo",
    ]
    assert comprension.dividir("toallas y sabanas") == ["toallas y sabanas"]


def test_el_clasificador_reconoce_formas_nuevas_y_duda_con_lo_raro():
    assert comprension.clasificar("cuanta plata hicimos")[0][1] == "ingresos"
    assert comprension.clasificar("zzz qwerty")[:1] == [] or comprension.clasificar("zzz qwerty")[0][0] < 0.3


def test_el_corrector_no_cambia_verbos_bien_escritos():
    assert conocimiento.corregir("cuantas aguas se vendieron", ENTRADAS) == "cuantas aguas se vendieron"
    assert conocimiento.corregir("cuanto factruamos", ENTRADAS) == "cuanto facturamos"
    assert conocimiento.corregir("como venimos", ENTRADAS) == "como venimos"


@pytest.mark.parametrize(
    ("texto", "desde", "hasta"),
    [
        ("anoche", date(2026, 11, 12), date(2026, 11, 12)),
        ("hace dos semanas", date(2026, 10, 26), date(2026, 11, 1)),
        ("desde el lunes", date(2026, 11, 9), date(2026, 11, 13)),
        ("el 3 de noviembre", date(2026, 11, 3), date(2026, 11, 3)),
        ("del 1/11 al 10/11", date(2026, 11, 1), date(2026, 11, 10)),
        ("compara octubre", date(2026, 10, 1), date(2026, 10, 31)),
        ("la semana del 2/11", date(2026, 11, 2), date(2026, 11, 8)),
    ],
)
def test_periodos_dichos_de_muchas_formas(texto, desde, hasta):
    periodo = interpretar_periodo(normalizar(texto), date(2026, 11, 13))
    assert (periodo.desde, periodo.hasta) == (desde, hasta)


def test_el_periodo_anterior_es_del_mismo_tipo():
    hoy = date(2026, 11, 13)
    semana = interpretar_periodo("la semana pasada", hoy)
    assert (previo_de(semana, hoy).desde, previo_de(semana, hoy).hasta) == (date(2026, 10, 26), date(2026, 11, 1))
    octubre = interpretar_periodo("en octubre", hoy)
    assert previo_de(octubre, hoy).desde == date(2026, 9, 1)


# --- Razonar ------------------------------------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gerencia(cliente_como, con_historial):
    return await cliente_como("gerencia")


async def _preguntar(cliente, texto: str, anterior: dict | None = None) -> dict:
    cuerpo = {"texto": texto}
    if anterior:
        cuerpo |= {
            "anterior": anterior.get("pregunta_resuelta") or anterior["respuesta"],
            "anterior_intencion": anterior["intencion"],
        }
    return (await cliente.post(PREGUNTA, json=cuerpo)).json()


async def test_compara_dos_periodos_y_dice_de_donde_sale_la_diferencia(gerencia):
    datos = await _preguntar(gerencia, "compará la semana pasada con la anterior")
    assert datos["intencion"] == "comparar"
    assert "viene sobre todo" in datos["respuesta"] or "Prácticamente lo mismo" in datos["respuesta"]
    assert [f[0] for f in datos["tabla"]["filas"]][:3] == ["Ingresos", "Turnos", "Ticket promedio"]
    assert datos["entendido"].startswith("Comparación ·")


async def test_sigue_la_conversacion_y_explica_por_que(gerencia):
    primera = await _preguntar(gerencia, "cuánto facturamos la semana pasada")
    anterior = await _preguntar(gerencia, "y la anterior?", primera)
    assert anterior["intencion"] == "ingresos" and "semana del" in anterior["respuesta"]
    por_que = await _preguntar(gerencia, "por qué?", anterior)
    assert por_que["intencion"] == "explicacion" and "pesa más" in por_que["respuesta"]
    es_mucho = await _preguntar(gerencia, "es mucho?", primera)
    assert es_mucho["intencion"] == "valoracion" and "lo típico" in es_mucho["respuesta"]


async def test_proyecta_el_mes_y_encuentra_el_mejor_dia(gerencia):
    proyeccion = await _preguntar(gerencia, "cuánto vamos a facturar este mes")
    assert proyeccion["intencion"] == "proyeccion" and "cerraría" in proyeccion["respuesta"]
    mejor = await _preguntar(gerencia, "cuál fue el mejor día del mes")
    assert mejor["intencion"] == "dias" and "el mejor día fue" in mejor["respuesta"]
    assert len(mejor["tabla"]["filas"]) == 5


async def test_aconseja_con_las_alertas_y_las_tarifas(gerencia):
    datos = await _preguntar(gerencia, "qué me recomendás")
    assert datos["intencion"] == "consejos"
    assert datos["respuesta"].startswith(("Te recomiendo", "Por ahora no veo"))


async def test_dos_preguntas_juntas_tienen_dos_respuestas(gerencia):
    datos = await _preguntar(gerencia, "cuánto facturamos la semana pasada y cuántos turnos hubo")
    partes = datos["respuesta"].split("\n\n")
    assert len(partes) == 2 and "se cobraron" in partes[0] and "turnos" in partes[1]
    # La segunda se entiende sobre la primera: también la semana pasada.
    assert datos["entendido"].count("del ") >= 2


async def test_un_periodo_sin_arquear_se_explica_en_lugar_de_dar_cero(gerencia, client):
    datos = await _preguntar(gerencia, "cuánto facturamos hoy")
    assert "Todavía no hay" in datos["respuesta"] or "se cobraron" in datos["respuesta"]
    assert "0 turnos" not in datos["respuesta"]


async def test_si_duda_pregunta(gerencia):
    datos = await _preguntar(gerencia, "y lo de los numeros esos del otro dia")
    assert datos["intencion"] in ("aclaracion", "desconocida") or datos["intencion"] in comprension.PREGUNTA_DE


async def test_al_conserje_no_le_razona_con_plata(client, con_historial):
    for frase in ("qué me recomendás", "cuánto vamos a facturar este mes", "compará octubre con septiembre"):
        assert (await _preguntar(client, frase))["intencion"] == "fuera_de_alcance"


async def test_ordenes_dichas_como_se_habla(client, con_historial):
    ya_limpia = await _preguntar(client, "che la 2 ya está limpia")
    assert ya_limpia["intencion"].startswith("accion:")
    se_fue = await _preguntar(client, "se fue un cliente porque buscaba jacuzzi")
    assert se_fue["intencion"] == "accion:cliente_perdido"
    assert se_fue["confirmacion"]["motivo"] == "OTRO" and se_fue["confirmacion"]["motivo_detalle"] == "buscaba jacuzzi"
    grosero = await _preguntar(client, "se fue un cliente porque era un boludo")
    assert grosero["intencion"] == "accion:rechazada"
