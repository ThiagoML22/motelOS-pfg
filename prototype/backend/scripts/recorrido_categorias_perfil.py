"""Recorrido de punta a punta de las categorías de habitación y del perfil (migración 008) contra la API real.

La API se conecta como motel_app: las claves cambian por las funciones SECURITY DEFINER de la base y las categorías
pasan por Row Level Security. Necesita los datos de demostración (docker compose run --rm admin).

Uso: python -m scripts.recorrido_categorias_perfil --api http://localhost:8004
"""

import argparse
import secrets

import httpx

from scripts.recorrido_multiinquilino import entrar
from scripts.recorrido_v2 import leer_env, paso


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    api = parser.parse_args().api
    env = leer_env()
    gerencia_clave, conserjes = env["DEMO_CLAVE_GERENCIA"], env["DEMO_CLAVE_CONSERJES"]

    # 1. Categoría nueva con su tarifa, asignada a una habitación de Luna.
    gerencia = entrar(api, "luna", "gerencia", gerencia_clave)
    nombre = f"Temática {secrets.token_hex(2)}"
    alta = gerencia.post("/configuracion/categorias", json={
        "nombre": nombre, "color": "#be123c", "orden": 5,
        "tarifa": {"tarifa_base": 12500, "estadia_base_min": 90, "fraccion_min": 15, "tarifa_fraccion": 1500,
                   "tolerancia_min": 5, "tope": 25000},
    })
    paso("La gerencia crea una categoría con su tarifa (90 min por $12.500)", alta.status_code == 201, alta.text)
    categoria = alta.json()
    habitaciones = {h["numero"]: h for h in gerencia.get("/configuracion/habitaciones").json()}
    asignada = gerencia.patch(f"/configuracion/habitaciones/{habitaciones[106]['id']}",
                              json={"categoria_id": categoria["id"]})
    paso("La habitación 106 pasa a la categoría nueva", asignada.status_code == 200, asignada.text)

    # 2. El conserje ve la categoría y el turno toma su tarifa.
    conserje = entrar(api, "luna", "conserje1", conserjes)
    visibles = {c["nombre"]: c for c in conserje.get("/categorias/").json()}
    paso("La ventanilla ve la categoría con su tarifa", visibles.get(nombre, {}).get("tarifa", {}).get("tarifa_base")
         == 12500, list(visibles))
    conserje.post("/guardias/")
    turno = conserje.post("/turnos/", json={"habitacion_id": habitaciones[106]["id"], "tipo_cliente": "Moto"})
    paso("El turno en la 106 toma la tarifa de la categoría ($12.500, 90 min)",
         turno.status_code == 201 and turno.json()["tarifa_base"] == 12500
         and turno.json()["estadia_base_min"] == 90, turno.text)
    resumen = conserje.get(f"/turnos/{turno.json()['id']}/resumen").json()
    paso("El resumen del turno informa su categoría", resumen["tarifa"]["categoria"] == nombre, resumen.get("tarifa"))
    baja = gerencia.patch(f"/configuracion/categorias/{categoria['id']}", json={"activa": False})
    paso("Una categoría con habitaciones no se da de baja (409)", baja.status_code == 409, baja.text)

    # 3. Perfil: nombre visible y clave propia por la función de la base.
    nombre_antes = conserje.get("/perfil/").json()["nombre_visible"]
    cambio = conserje.patch("/perfil/", json={"nombre_visible": "Conserje Luna (noche)"})
    paso("El conserje cambia su nombre visible", cambio.status_code == 200, cambio.text)
    clave_nueva = f"clave-{secrets.token_hex(6)}"
    resp = conserje.post("/perfil/clave", json={"actual": conserjes, "nueva": clave_nueva})
    paso("El conserje cambia su clave (función cambiar_clave_propia)", resp.status_code == 204, resp.text)
    anonimo = httpx.Client(base_url=f"{api}/api/v1", headers={"X-Requested-With": "motelos"}, timeout=10)
    vieja = anonimo.post("/auth/login", json={"establecimiento": "luna", "usuario": "conserje1", "clave": conserjes})
    paso("La clave vieja ya no entra", vieja.status_code == 401, vieja.status_code)

    # 4. La gerencia restablece la clave del conserje (función restablecer_clave_conserje) a la de la demo.
    conserje_id = conserje.get("/perfil/").json()["id"]
    restablecida = gerencia.post(f"/operadores/{conserje_id}/clave", json={"nueva": conserjes})
    paso("La gerencia restablece la clave del conserje", restablecida.status_code == 200, restablecida.text)
    entrar(api, "luna", "conserje1", conserjes)
    propia = gerencia.post(f"/operadores/{gerencia.get('/perfil/').json()['id']}/clave", json={"nueva": "x" * 12})
    paso("La gerencia no se restablece la clave a sí misma (409)", propia.status_code == 409, propia.text)
    conserje.patch("/perfil/", json={"nombre_visible": nombre_antes})
    actividad = [e["accion"] for e in gerencia.get("/configuracion/actividad", params={"categoria": "PERFIL"}).json()]
    paso("El registro tiene el cambio de clave, el de nombre y el restablecimiento",
         {"CLAVE_PROPIA", "PERFIL_NOMBRE", "CLAVE_RESTABLECIDA"} <= set(actividad), actividad)
    print("Recorrido de categorías y perfil completo.")


if __name__ == "__main__":
    main()
