"""Recorrido de punta a punta de la inteligencia local, la apariencia de cada motel y las novedades de guardia
(migración 009) contra la API real, conectada como motel_app (Row Level Security y triggers de la base).

Necesita los datos de demostración (docker compose run --rm admin). Con el historial de ejemplo
(scripts.cargar_historial) además verifica que el pronóstico tenga sus 24 horas.

Uso: python -m scripts.recorrido_inteligencia_novedades --api http://localhost:8004
"""

import argparse

import httpx

from scripts.recorrido_multiinquilino import entrar
from scripts.recorrido_v2 import leer_env, paso


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    api = parser.parse_args().api
    env = leer_env()
    gerencia_clave, conserjes = env["DEMO_CLAVE_GERENCIA"], env["DEMO_CLAVE_CONSERJES"]

    # 1. Marca pública del ingreso: nombre y apariencia, sin sesión.
    anonimo = httpx.Client(base_url=f"{api}/api/v1", headers={"X-Requested-With": "motelos"}, timeout=10)
    marca = anonimo.get("/auth/marca", params={"codigo": "LUNA"})
    paso(
        "El ingreso reconoce el código de Motel Luna con su color",
        marca.status_code == 200 and marca.json()["nombre"] == "Motel Luna" and marca.json()["color_marca"],
        marca.text,
    )
    paso(
        "Un código inexistente no se reconoce (404)",
        anonimo.get("/auth/marca", params={"codigo": "no-existe"}).status_code == 404,
        "",
    )

    # 2. La gerencia cambia el aviso «por vencer» y la sesión lo trae; después lo deja como estaba.
    gerencia = entrar(api, "motelcc", "gerencia", gerencia_clave)
    antes = gerencia.get("/configuracion/establecimiento").json()["aviso_por_vencer_min"]
    cambio = gerencia.patch("/configuracion/establecimiento", json={"aviso_por_vencer_min": 15})
    sesion = gerencia.get("/auth/sesion").json()["establecimiento"]
    paso(
        "El aviso «por vencer» configurado llega en la sesión",
        cambio.status_code == 200 and sesion["aviso_por_vencer_min"] == 15,
        cambio.text,
    )
    gerencia.patch("/configuracion/establecimiento", json={"aviso_por_vencer_min": antes})

    # 3. Novedades: el conserje deja una en su guardia; la ve su gerencia y no la del otro motel.
    conserje = entrar(api, "luna", "conserje1", conserjes)
    conserje.post("/guardias/")  # si ya tiene su guardia abierta, responde 409 y se sigue con esa
    habitaciones = {h["numero"]: h for h in conserje.get("/habitaciones/").json()}
    nota = conserje.post(
        "/novedades/",
        json={
            "texto": "Recorrido: la 101 necesita toallas",
            "importante": True,
            "habitacion_id": habitaciones[101]["id"],
        },
    )
    paso(
        "El conserje deja una novedad importante en su guardia",
        nota.status_code == 201 and nota.json()["franja"] and nota.json()["habitacion_numero"] == 101,
        nota.text,
    )
    gerencia_luna = entrar(api, "luna", "gerencia", gerencia_clave)
    ids_luna = {n["id"] for n in gerencia_luna.get("/novedades/").json()}
    ids_motelcc = {n["id"] for n in gerencia.get("/novedades/").json()}
    paso(
        "La gerencia de Luna la ve y la de Motel C.C. no (RLS)",
        nota.json()["id"] in ids_luna and nota.json()["id"] not in ids_motelcc,
        (ids_luna, ids_motelcc),
    )

    # 4. Inteligencia: solo la gerencia; el tablero y el asistente responden.
    tablero = gerencia.get("/inteligencia/tablero")
    paso("La gerencia obtiene el tablero de inteligencia", tablero.status_code == 200, tablero.text[:200])
    datos = tablero.json()
    if datos["indicadores"]["turnos_7d"]:
        paso("Con historial, el pronóstico cubre 24 horas", len(datos["pronostico"]["horas"]) == 24, "")
    respuesta = gerencia.post("/inteligencia/pregunta", json={"texto": "¿Cuánto facturamos la semana pasada?"})
    paso(
        "El asistente entiende la pregunta de ingresos",
        respuesta.status_code == 200 and respuesta.json()["intencion"] == "ingresos",
        respuesta.text,
    )
    paso("El conserje no accede a la inteligencia (403)", conserje.get("/inteligencia/tablero").status_code == 403, "")
    print("Recorrido de inteligencia, apariencia y novedades completo.")


if __name__ == "__main__":
    main()
