"""Tarifas especiales por día y franja (migración 014): cuándo rige cada una y qué tarifa toma el turno."""

from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services import acceso_cliente, franjas
from app.services.liquidacion import con_zona
from scripts.cargar_historial import generar_historial

CONFIG = "/api/v1/configuracion"
TODO_EL_TIEMPO = {"dias": 127, "desde": "00:00", "hasta": "00:00"}
PRECIO = {"tarifa_base": 12000, "estadia_base_min": 120, "fraccion_min": 30, "tarifa_fraccion": 3000}
VIERNES_Y_SABADO = franjas.mascara(4, 5)
ZONA = ZoneInfo(settings.ZONA_HORARIA)


def _franja(dias: int, desde: str, hasta: str, id: int = 1, nombre: str = "Noche") -> SimpleNamespace:
    return SimpleNamespace(
        id=id, nombre=nombre, dias=dias, desde=time.fromisoformat(desde), hasta=time.fromisoformat(hasta)
    )


def _minuto(dia: int, hora: int, minuto: int = 0) -> int:
    return dia * franjas.MINUTOS_DIA + hora * 60 + minuto


def _alta(**cambios) -> dict:
    return {"categoria_id": 1, "nombre": "Noche", **TODO_EL_TIEMPO, "tarifa": PRECIO, **cambios}


async def _nueva(gerencia, **cambios) -> dict:
    resp = await gerencia.post(f"{CONFIG}/franjas", json=_alta(**cambios))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _turno(cliente, habitacion_id: int = 1, **extra):
    return await cliente.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, **extra})


def _dia_de_hoy() -> int:
    return datetime.now(UTC).astimezone(ZONA).weekday()


# --- Cuándo rige ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("minuto", "esperado"),
    [
        (_minuto(4, 19, 59), False),  # el viernes todavía no
        (_minuto(4, 20), True),  # empieza
        (_minuto(4, 23, 59), True),
        (_minuto(5, 2), True),  # la madrugada del sábado es la noche del viernes
        (_minuto(5, 5, 59), True),
        (_minuto(5, 6), False),  # termina: el borde final no cuenta
        (_minuto(5, 12), False),
        (_minuto(5, 21), True),  # la noche del sábado
        (_minuto(6, 3), True),  # sigue el domingo de madrugada
        (_minuto(6, 6), False),
        (_minuto(3, 23), False),  # el jueves no
    ],
)
def test_la_noche_del_viernes_sigue_el_sabado_de_madrugada(minuto, esperado):
    assert franjas.rige(_franja(VIERNES_Y_SABADO, "20:00", "06:00"), minuto) is esperado


def test_la_noche_del_domingo_da_la_vuelta_a_la_semana():
    domingo = _franja(franjas.mascara(6), "22:00", "05:00")
    assert franjas.rige(domingo, _minuto(6, 23))
    assert franjas.rige(domingo, _minuto(0, 4, 59))
    assert not franjas.rige(domingo, _minuto(0, 5))
    assert not franjas.rige(domingo, _minuto(0, 23))


def test_desde_igual_a_hasta_es_el_dia_completo():
    domingo = _franja(franjas.mascara(6), "00:00", "00:00")
    assert franjas.rige(domingo, _minuto(6, 0)) and franjas.rige(domingo, _minuto(6, 23, 59))
    assert not franjas.rige(domingo, _minuto(5, 23, 59)) and not franjas.rige(domingo, _minuto(0, 0))


def test_hasta_la_medianoche_no_entra_al_dia_siguiente():
    viernes = _franja(franjas.mascara(4), "20:00", "00:00")
    assert franjas.rige(viernes, _minuto(4, 23, 59))
    assert not franjas.rige(viernes, _minuto(5, 0))


def test_primer_cruce_dice_donde_se_pisan():
    noche = franjas.tramos(VIERNES_Y_SABADO, time(20), time(6))
    assert franjas.primer_cruce(noche, franjas.tramos(franjas.mascara(5), time(1), time(3))) == _minuto(5, 1)
    # Una termina justo cuando empieza la otra: no se pisan.
    assert franjas.primer_cruce(noche, franjas.tramos(franjas.mascara(5), time(6), time(20))) is None
    # Del domingo al lunes.
    domingo = franjas.tramos(franjas.mascara(6), time(22), time(5))
    assert franjas.primer_cruce(domingo, franjas.tramos(franjas.mascara(0), time(4), time(8))) == _minuto(0, 4)


@pytest.mark.parametrize(
    ("dias", "texto"),
    [
        (127, "todos los días"),
        (franjas.mascara(0, 1, 2, 3), "de lunes a jueves"),
        (VIERNES_Y_SABADO, "viernes y sábado"),
        (franjas.mascara(0, 2, 4), "lunes, miércoles y viernes"),
        (franjas.mascara(6), "domingo"),
    ],
)
def test_los_dias_se_leen_como_se_dicen(dias, texto):
    assert franjas.dias_texto(dias) == texto


def test_la_regla_se_lee_como_se_dice():
    assert franjas.regla_texto(VIERNES_Y_SABADO, time(20), time(6)) == "viernes y sábado de 20:00 a 06:00"
    assert franjas.regla_texto(franjas.mascara(6), time(0), time(0)) == "domingo, todo el día"


def _tarifario() -> franjas.Tarifario:
    noche = _franja(VIERNES_Y_SABADO, "20:00", "06:00", 1, "Noche")
    pegada = _franja(franjas.mascara(5), "06:00", "20:00", 2, "Sábado de día")
    return franjas.Tarifario(
        generales={1: SimpleNamespace(tarifa_base=8000)},
        franjas={1: [noche, pegada]},
        de_franja={1: SimpleNamespace(tarifa_base=12000), 2: SimpleNamespace(tarifa_base=10000)},
    )


def _momento(dia: int, hora: int) -> datetime:
    # El 2 de noviembre de 2026 es lunes.
    return datetime(2026, 11, 2 + dia, hora, tzinfo=ZONA)


def test_el_tarifario_dice_que_rige_y_cuando_cambia():
    tarifario = _tarifario()
    jueves = tarifario.en(1, _momento(3, 12))
    assert jueves.franja is None and float(jueves.tarifa.tarifa_base) == 8000
    assert jueves.cambia_en == _momento(4, 20) and jueves.siguiente_franja.nombre == "Noche"

    sabado_madrugada = tarifario.en(1, _momento(5, 3))
    assert sabado_madrugada.franja.nombre == "Noche"
    # Dos franjas pegadas: el cambio es a la otra, no a la general.
    assert sabado_madrugada.cambia_en == _momento(5, 6) and sabado_madrugada.siguiente_franja.nombre == "Sábado de día"

    domingo_madrugada = tarifario.en(1, _momento(6, 3))
    assert domingo_madrugada.cambia_en == _momento(6, 6)
    assert domingo_madrugada.siguiente_franja is None and float(domingo_madrugada.siguiente.tarifa_base) == 8000


def test_sin_franjas_no_hay_cambio_y_una_franja_de_toda_la_semana_tampoco():
    tarifario = franjas.Tarifario({1: SimpleNamespace(tarifa_base=8000)}, {}, {})
    assert tarifario.en(1, _momento(0, 12)).cambia_en is None
    siempre = _franja(127, "00:00", "00:00")
    tarifario = franjas.Tarifario({}, {1: [siempre]}, {1: SimpleNamespace(tarifa_base=9000)})
    vigente = tarifario.en(1, _momento(3, 12))
    assert vigente.franja is siempre and vigente.cambia_en is None


def test_una_categoria_sin_tarifa_no_tiene_nada_que_regir():
    assert franjas.Tarifario({}, {}, {}).en(1, _momento(0, 12)) is None


# --- El turno ---------------------------------------------------------------------------------------------------------


async def test_el_turno_toma_la_tarifa_de_la_franja_y_la_conserva(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia)
    turno = (await _turno(client)).json()
    assert turno["tarifa_base"] == 12000 and turno["estadia_base_min"] == 120

    # Cambia el precio y después se da de baja: el turno abierto sigue con lo suyo (RN-DER-06).
    cambio = await gerencia.patch(f"{CONFIG}/franjas/{franja['id']}", json={"tarifa": {**PRECIO, "tarifa_base": 20000}})
    assert cambio.status_code == 200, cambio.text
    assert (await gerencia.delete(f"{CONFIG}/franjas/{franja['id']}")).status_code == 204

    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["tarifa_base"] == 12000 and resumen["total_general"] == 12000
    assert resumen["tarifa"]["franja"] == "Noche" and resumen["tarifa"]["tarifa_fraccion"] == 3000

    cierre = await client.post(
        f"/api/v1/turnos/{turno['id']}/cerrar", json={"pagos": [{"medio_pago": "EFECTIVO", "monto": 12000}]}
    )
    assert cierre.status_code == 200, cierre.text
    # El turno siguiente ya vuelve a la general.
    otro = await _turno(client, 2)
    assert otro.json()["tarifa_base"] == 8000


async def test_fuera_de_la_franja_rige_la_general(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    otro_dia = franjas.mascara((_dia_de_hoy() + 3) % 7)
    await _nueva(gerencia, dias=otro_dia, desde="10:00", hasta="11:00")
    assert (await _turno(client)).json()["tarifa_base"] == 8000


async def test_la_franja_de_otra_categoria_no_cuenta(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(
        f"{CONFIG}/categorias",
        json={"nombre": "VIP", "color": "#7c3aed", "orden": 2, "tarifa": {**PRECIO, "tarifa_base": 16000}},
    )
    await _nueva(gerencia, categoria_id=alta.json()["id"], tarifa={**PRECIO, "tarifa_base": 30000})
    assert (await _turno(client)).json()["tarifa_base"] == 8000


async def test_si_la_tarifa_cambio_mientras_se_atendia_no_abre(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    vista = (await client.get("/api/v1/categorias/")).json()[0]["tarifa_ahora"]["id"]
    await _nueva(gerencia)

    resp = await _turno(client, tarifa_id=vista)
    assert resp.status_code == 409
    assert "$" in resp.json()["detail"] and "Noche" in resp.json()["detail"]

    actual = (await client.get("/api/v1/categorias/")).json()[0]["tarifa_ahora"]["id"]
    assert (await _turno(client, tarifa_id=actual)).status_code == 201


async def test_cliente_ve_el_nombre_de_su_tarifa(client, cliente_como, anonimo):
    await _nueva(await cliente_como("gerencia"), nombre="Fin de semana")
    turno = (await _turno(client)).json()
    token = (await client.get(f"/api/v1/turnos/{turno['id']}/ticket")).json()["direccion"].split("cliente=")[1]
    assert acceso_cliente.leer_token(token) is not None
    datos = (await anonimo.get(f"/api/v1/cliente/{token}")).json()
    assert datos["franja"] == "Fin de semana" and datos["tarifa_base"] == 12000


# --- El asistente ------------------------------------------------------------------------------------------------


def test_entiende_de_que_momento_se_habla():
    ahora = datetime(2026, 11, 4, 15, 0, tzinfo=ZONA)  # miércoles
    casos = {
        "cuanto sale el sabado a la noche": (5, 22, "el sábado a las 22:00"),
        "precio del viernes a las 23": (4, 23, "el viernes a las 23:00"),
        "cuanto sale a las 20:30": (2, 20, "hoy a las 20:30"),
        "cuanto sale manana a la tarde": (3, 17, "mañana a las 17:00"),
        "tarifa del domingo a la manana": (6, 10, "el domingo a las 10:00"),
        "cuanto sale esta noche": (2, 22, "hoy a las 22:00"),
        "cuanto sale a las 8": (3, 8, "mañana a las 08:00"),  # ya pasó: es la próxima
    }
    for texto, (dia, hora, dicho) in casos.items():
        momento, etiqueta = franjas.momento_mencionado(texto, ahora)
        assert (momento.weekday(), momento.hour, etiqueta) == (dia, hora, dicho), texto
    # Un día solo no alcanza: tiene varias tarifas.
    assert franjas.momento_mencionado("cuanto sale el sabado", ahora) is None
    assert franjas.momento_mencionado("cuanto sale", ahora) is None


async def _preguntar(cliente, texto: str) -> dict:
    resp = await cliente.post("/api/v1/asistente/pregunta", json={"texto": texto})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_el_asistente_dice_la_tarifa_que_rige_ahora_y_cuando_cambia(client, cliente_como):
    await _nueva(await cliente_como("gerencia"), dias=franjas.mascara(_dia_de_hoy()))
    datos = await _preguntar(client, "¿cuánto sale la simple?")
    assert "Simple (Noche): $12.000" in datos["respuesta"]
    assert "pasa a $8.000 (tarifa general)" in datos["respuesta"]


async def test_el_asistente_responde_por_otro_dia_y_hora(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _nueva(gerencia, dias=VIERNES_Y_SABADO, desde="20:00", hasta="06:00")
    noche = await _preguntar(client, "¿cuánto sale la simple el sábado a la noche?")
    assert "Simple (Noche): $12.000" in noche["respuesta"] and "a las 22:00" in noche["detalle"]
    madrugada = await _preguntar(client, "¿y el precio de la simple el sábado a las 2?")
    assert "Simple (Noche)" in madrugada["respuesta"]
    martes = await _preguntar(client, "¿cuánto sale la simple el martes a la tarde?")
    assert "Simple: $8.000" in martes["respuesta"]


async def test_el_asistente_lista_las_especiales(client, cliente_como):
    sin_nada = await _preguntar(client, "¿qué tarifas especiales hay?")
    assert "rige la tarifa general toda la semana" in sin_nada["respuesta"]
    await _nueva(await cliente_como("gerencia"), dias=VIERNES_Y_SABADO, desde="20:00", hasta="06:00")
    datos = await _preguntar(client, "¿qué tarifas especiales hay?")
    assert "Noche, viernes y sábado de 20:00 a 06:00, $12.000 por 2 h" in datos["respuesta"]


async def test_abrir_por_el_asistente_avisa_y_fija_la_tarifa(client, cliente_como):
    await _nueva(await cliente_como("gerencia"))
    datos = await _preguntar(client, "abrí la 1 en auto")
    assert datos["intencion"] == "accion:abrir_turno"
    assert "Simple · Noche: $12.000" in datos["detalle"]
    tarifa_id = datos["confirmacion"]["tarifa_id"]
    resp = await _turno(client, tarifa_id=tarifa_id)
    assert resp.status_code == 201 and resp.json()["tarifa_base"] == 12000


@pytest.mark.parametrize(
    ("pregunta", "intencion"),
    [
        ("¿qué es una tarifa especial?", "definicion:tarifa_especial"),
        ("¿por qué sale más caro de noche?", "definicion:tarifa_especial"),
        ("¿Cómo creo una tarifa especial?", "ayuda:config_franjas"),
    ],
)
async def test_el_asistente_explica_las_tarifas_especiales(cliente_como, pregunta, intencion):
    datos = await _preguntar(await cliente_como("gerencia"), pregunta)
    assert datos["intencion"] == intencion, datos


# --- La inteligencia ---------------------------------------------------------------------------------------------


async def _tablero(gerencia) -> dict:
    resp = await gerencia.get("/api/v1/inteligencia/tablero")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_el_historial_cobra_lo_que_regia_y_la_inteligencia_lo_cuenta(db, cliente_como):
    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia, dias=VIERNES_Y_SABADO, desde="20:00", hasta="06:00")
    await generar_historial(db, dias=28, semilla=3)

    turnos = list((await db.execute(select(Turno))).scalars())
    regla = _franja(VIERNES_Y_SABADO, "20:00", "06:00")
    en_la_franja = [
        t for t in turnos if franjas.rige(regla, franjas.minuto_de_semana(con_zona(t.hora_inicio).astimezone(ZONA)))
    ]
    assert en_la_franja and len(en_la_franja) < len(turnos)
    tarifa_noche = franja["tarifa"]["id"]
    assert {t.tarifa_id for t in en_la_franja} == {tarifa_noche}
    assert all(float(t.tarifa_base) == 12000 for t in en_la_franja)
    assert all(t.tarifa_id != tarifa_noche and float(t.tarifa_base) == 8000 for t in turnos if t not in en_la_franja)

    sugerencia = (await _tablero(gerencia))["sugerencias"][0]
    assert sugerencia["rendimiento"][0]["franja"] == "Noche"
    assert sugerencia["rendimiento"][0]["turnos"] > 0 and sugerencia["rendimiento"][0]["ingresos"] > 0


async def test_el_pico_lleno_sugiere_una_tarifa_especial_y_despues_subirla(db, cliente_como):
    gerencia = await cliente_como("gerencia")
    await generar_historial(db, dias=42, semilla=3, intensidad=4.0)
    sugerencia = (await _tablero(gerencia))["sugerencias"][0]
    assert sugerencia["accion"] == "subir" and sugerencia["titulo"] == "Cobrar 10% más las noches de fin de semana"
    nueva = sugerencia["franja_nueva"]
    assert nueva["regla"] == "viernes y sábado de 20:00 a 06:00" and sugerencia["franja_id"] is None
    assert sugerencia["propuesta"]["tarifa_base"] > sugerencia["actual"]["tarifa_base"]
    assert sugerencia["impacto_mensual"] > 0

    # Aplicada tal cual la manda la pantalla, el pico ya tiene la suya: ahora la sugerencia es sobre ella.
    alta = await gerencia.post(
        f"{CONFIG}/franjas",
        json={
            "categoria_id": sugerencia["categoria_id"],
            "nombre": nueva["nombre"],
            "dias": nueva["dias"],
            "desde": nueva["desde"],
            "hasta": nueva["hasta"],
            "tarifa": sugerencia["propuesta"],
        },
    )
    assert alta.status_code == 201, alta.text
    otra = (await _tablero(gerencia))["sugerencias"][0]
    assert otra["franja_id"] == alta.json()["id"] and otra["franja_nueva"] is None
    assert otra["titulo"] == "Subir «Noche de fin de semana» un 10%"
    assert otra["actual"]["tarifa_base"] == sugerencia["propuesta"]["tarifa_base"]


# --- La ventanilla y la gerencia ----------------------------------------------------------------------------------


async def test_la_ventanilla_ve_la_general_lo_que_rige_y_las_especiales(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    sin_franjas = (await client.get("/api/v1/categorias/")).json()[0]
    assert sin_franjas["tarifa_ahora"]["id"] == sin_franjas["tarifa"]["id"] and sin_franjas["franjas"] == []
    assert sin_franjas["tarifa_ahora"]["cambia_en"] is None

    hoy = _dia_de_hoy()
    await _nueva(gerencia, dias=franjas.mascara(hoy), desde="00:00", hasta="00:00")
    categoria = (await client.get("/api/v1/categorias/")).json()[0]
    assert categoria["tarifa"]["tarifa_base"] == 8000
    ahora = categoria["tarifa_ahora"]
    assert ahora["tarifa_base"] == 12000 and ahora["franja"] == "Noche"
    assert ahora["cambia_a"] is None and ahora["cambia_a_precio"] == 8000
    assert datetime.fromisoformat(ahora["cambia_en"]) - datetime.now(UTC) <= timedelta(days=1)
    assert categoria["franjas"][0]["tarifa"]["tarifa_base"] == 12000
    assert categoria["franjas"][0]["regla"].endswith("todo el día")


async def test_cambiar_la_general_no_toca_las_especiales(client, cliente_como):
    gerencia = await cliente_como("gerencia")
    await _nueva(gerencia)
    resp = await gerencia.post(f"{CONFIG}/tarifas", json={**PRECIO, "categoria_id": 1, "tarifa_base": 9000})
    assert resp.status_code == 201, resp.text
    categoria = (await client.get("/api/v1/categorias/")).json()[0]
    assert categoria["tarifa"]["tarifa_base"] == 9000 and categoria["tarifa_ahora"]["tarifa_base"] == 12000


async def test_no_se_pisan_y_el_mensaje_dice_con_cual(cliente_como):
    gerencia = await cliente_como("gerencia")
    await _nueva(gerencia, dias=VIERNES_Y_SABADO, desde="20:00", hasta="06:00")
    resp = await gerencia.post(
        f"{CONFIG}/franjas", json=_alta(nombre="Madrugada", dias=franjas.mascara(5), desde="01:00", hasta="03:00")
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Se superpone con «Noche» el sábado a las 01:00."
    # Pegada a la otra sí entra.
    await _nueva(gerencia, nombre="Sábado de día", dias=franjas.mascara(5), desde="06:00", hasta="20:00")


async def test_mover_una_franja_tampoco_puede_pisar_a_otra(cliente_como):
    gerencia = await cliente_como("gerencia")
    await _nueva(gerencia, dias=franjas.mascara(0), desde="10:00", hasta="12:00")
    tarde = await _nueva(gerencia, nombre="Tarde", dias=franjas.mascara(0), desde="12:00", hasta="14:00")
    resp = await gerencia.patch(f"{CONFIG}/franjas/{tarde['id']}", json={"desde": "11:00"})
    assert resp.status_code == 409 and "Noche" in resp.json()["detail"]
    # Sin cambiar el horario, no se compara consigo misma.
    assert (await gerencia.patch(f"{CONFIG}/franjas/{tarde['id']}", json={"nombre": "Siesta"})).status_code == 200


async def test_el_nombre_no_se_repite_en_la_categoria(cliente_como):
    gerencia = await cliente_como("gerencia")
    await _nueva(gerencia, dias=franjas.mascara(0))
    resp = await gerencia.post(f"{CONFIG}/franjas", json=_alta(nombre="NOCHE", dias=franjas.mascara(1)))
    assert resp.status_code == 409 and "Ya hay" in resp.json()["detail"]


@pytest.mark.parametrize(
    "cambio",
    [
        {"dias": 0},
        {"dias": 128},
        {"nombre": " "},
        {"nombre": "x" * 41},
        {"desde": "25:00"},
        {"tarifa": {**PRECIO, "tarifa_base": 0}},
        {"tarifa": {**PRECIO, "tope": 5000}},
    ],
)
async def test_datos_invalidos_se_rechazan(cliente_como, cambio):
    gerencia = await cliente_como("gerencia")
    assert (await gerencia.post(f"{CONFIG}/franjas", json=_alta(**cambio))).status_code == 422


async def test_los_segundos_no_cuentan(cliente_como):
    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia, dias=1, desde="20:00:30", hasta="21:00:59")
    assert franja["desde"] == "20:00:00" and franja["hasta"] == "21:00:00"


async def test_una_categoria_dada_de_baja_no_recibe_franjas(cliente_como):
    gerencia = await cliente_como("gerencia")
    alta = await gerencia.post(
        f"{CONFIG}/categorias", json={"nombre": "Vieja", "color": "#7c3aed", "orden": 2, "tarifa": PRECIO}
    )
    await gerencia.patch(f"{CONFIG}/categorias/{alta.json()['id']}", json={"activa": False})
    assert (await gerencia.post(f"{CONFIG}/franjas", json=_alta(categoria_id=alta.json()["id"]))).status_code == 409


async def test_cambiar_el_precio_reemplaza_la_tarifa_y_no_la_edita(cliente_como, db):
    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia)
    original = franja["tarifa"]["id"]
    nueva = (
        await gerencia.patch(f"{CONFIG}/franjas/{franja['id']}", json={"tarifa": {**PRECIO, "tarifa_base": 15000}})
    ).json()
    assert nueva["tarifa"]["id"] != original and nueva["tarifa"]["tarifa_base"] == 15000
    fila = (await db.execute(select(Tarifa).where(Tarifa.id == original))).scalar_one()
    assert not fila.vigente and float(fila.tarifa_base) == 12000


async def test_la_baja_no_borra_y_se_puede_volver_a_crear(cliente_como):
    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia)
    assert (await gerencia.delete(f"{CONFIG}/franjas/{franja['id']}")).status_code == 204
    assert (await gerencia.delete(f"{CONFIG}/franjas/{franja['id']}")).status_code == 404
    assert (await gerencia.patch(f"{CONFIG}/franjas/{franja['id']}", json={"nombre": "Otra"})).status_code == 404
    await _nueva(gerencia)
    historial = (await gerencia.get(f"{CONFIG}/tarifas", params={"categoria_id": 1})).json()
    # La general primero; después la especial vigente y la dada de baja, con su nombre.
    assert historial[0]["franja"] is None and historial[0]["vigente"]
    assert [t["franja"] for t in historial[1:]] == ["Noche", "Noche"]
    assert [t["vigente"] for t in historial[1:]] == [True, False]


async def test_queda_en_el_registro_de_actividad(cliente_como):
    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia, dias=VIERNES_Y_SABADO, desde="20:00", hasta="06:00")
    await gerencia.patch(f"{CONFIG}/franjas/{franja['id']}", json={"desde": "21:00", "tarifa": PRECIO})
    await gerencia.delete(f"{CONFIG}/franjas/{franja['id']}")
    entradas = {
        e["accion"]: e for e in (await gerencia.get(f"{CONFIG}/actividad", params={"categoria": "TARIFA"})).json()
    }
    assert {"FRANJA_ALTA", "FRANJA_CAMBIO", "FRANJA_PRECIO", "FRANJA_BAJA"} <= set(entradas)
    assert "viernes y sábado de 20:00 a 06:00" in entradas["FRANJA_ALTA"]["descripcion"]
    assert entradas["FRANJA_CAMBIO"]["valor_nuevo"] == "viernes y sábado de 21:00 a 06:00"


@pytest.mark.parametrize(
    ("metodo", "camino", "cuerpo"),
    [
        ("post", f"{CONFIG}/franjas", _alta()),
        ("patch", f"{CONFIG}/franjas/1", {"nombre": "Otra"}),
        ("delete", f"{CONFIG}/franjas/1", None),
    ],
)
async def test_solo_la_gerencia_las_gestiona(client, metodo, camino, cuerpo):
    pedido = {"json": cuerpo} if cuerpo else {}
    assert (await client.request(metodo.upper(), camino, **pedido)).status_code == 403


async def test_otro_establecimiento_no_las_ve_ni_las_toca(cliente_como, session_factory):
    from app.tests.conftest import CLAVE_OTRO_MOTEL, ESTABLECIMIENTO_OTRO, nuevo_cliente

    gerencia = await cliente_como("gerencia")
    franja = await _nueva(gerencia)
    async with nuevo_cliente() as ajena:
        await ajena.post(
            "/api/v1/auth/login",
            json={"usuario": "gerencia", "clave": CLAVE_OTRO_MOTEL, "establecimiento": ESTABLECIMIENTO_OTRO},
        )
        categorias = (await ajena.get(f"{CONFIG}/categorias")).json()
        assert categorias and all(c["franjas"] == [] for c in categorias)
        assert (await ajena.patch(f"{CONFIG}/franjas/{franja['id']}", json={"nombre": "Mía"})).status_code == 404
        assert (await ajena.delete(f"{CONFIG}/franjas/{franja['id']}")).status_code == 404


async def test_el_asistente_dice_cuando_cambia_la_tarifa(client, cliente_como):
    sin_nada = await _preguntar(client, "¿cuándo cambia la tarifa?")
    assert sin_nada["intencion"] == "tarifas" and "No hay cambios" in sin_nada["respuesta"]
    await _nueva(await cliente_como("gerencia"), dias=franjas.mascara(_dia_de_hoy()))
    datos = await _preguntar(client, "¿cuándo cambia la tarifa?")
    assert "pasa a $8.000 (tarifa general)" in datos["respuesta"]