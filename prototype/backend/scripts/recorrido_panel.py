"""Recorrido de punta a punta del panel de configuración de la gerencia (RF-11) contra una API en ejecución.

Corre con la aplicación conectada como motel_app sobre el esquema migrado, de modo que prueba los permisos reales
de la migración 005: la gerencia da de alta un conserje, cambia el fondo de cambio, la tarifa y un precio, agrega
una habitación; el conserje nuevo trabaja una guardia con esos valores; después la gerencia da de baja la
habitación y al conserje. Al final restituye la tarifa, el fondo y el precio que había.

Uso: python -m scripts.recorrido_panel --api http://localhost:8000
     (las claves se leen de DEMO_CLAVE_GERENCIA y DEMO_CLAVE_CONSERJES, o del archivo .env de prototype/)
"""

import argparse
import secrets
import sys

from scripts.recorrido_v2 import leer_env, paso, sesion

TARIFA_PRUEBA = {"tarifa_base": 9000, "estadia_base_min": 120, "fraccion_min": 30, "tarifa_fraccion": 2500}
FONDO_PRUEBA = 30000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    env = leer_env()
    clave_conserjes, clave_gerencia = env.get("DEMO_CLAVE_CONSERJES"), env.get("DEMO_CLAVE_GERENCIA")
    if not clave_conserjes or not clave_gerencia:
        sys.exit("Faltan DEMO_CLAVE_CONSERJES y DEMO_CLAVE_GERENCIA")

    c1 = sesion(args.api, "conserje1", clave_conserjes)
    paso("Un conserje no entra al panel de configuración (403)", c1.get("/configuracion/tarifas").status_code == 403)

    gerencia = sesion(args.api, "gerencia", clave_gerencia)
    tarifa_anterior = gerencia.get("/configuracion/tarifas").json()[0]
    fondo_anterior = gerencia.get("/configuracion/caja").json()["fondo_cambio"]
    articulo = gerencia.get("/configuracion/articulos").json()[0]

    usuario, clave = f"panel.{secrets.token_hex(3)}", secrets.token_urlsafe(12)
    alta = gerencia.post("/operadores/", json={"usuario": usuario, "nombre_visible": "Conserje del panel",
                                               "clave": clave})
    paso("La gerencia da de alta un conserje; la base le asigna el rol OPERADOR",
         alta.status_code == 201 and alta.json()["rol"] == "OPERADOR", alta.text)
    conserje_id = alta.json()["id"]

    paso("La gerencia cambia el fondo de cambio",
         gerencia.patch("/configuracion/caja", json={"fondo_cambio": FONDO_PRUEBA}).status_code == 200)
    nueva = gerencia.post("/configuracion/tarifas", json=TARIFA_PRUEBA)
    paso("La gerencia cambia la tarifa a $9.000", nueva.status_code == 201, nueva.text)
    precio = articulo["precio_unitario"] + 100
    cambio = gerencia.patch(f"/configuracion/articulos/{articulo['id']}", json={"precio_unitario": precio})
    paso("La gerencia cambia el precio de un artículo", cambio.status_code == 200, cambio.text)
    numero = max(h["numero"] for h in gerencia.get("/configuracion/habitaciones").json()) + 1
    hab = gerencia.post("/configuracion/habitaciones", json={"numero": numero})
    paso(f"La gerencia agrega la habitación {numero}", hab.status_code == 201, hab.text)
    hab_id = hab.json()["id"]

    nuevo = sesion(args.api, usuario, clave)
    guardia = nuevo.post("/guardias/")
    paso("El conserje nuevo abre su guardia con el fondo nuevo",
         guardia.status_code == 201 and guardia.json()["fondo_inicial"] == FONDO_PRUEBA, guardia.text)
    turno = nuevo.post("/turnos/", json={"habitacion_id": hab_id}).json()
    paso("El turno nuevo copia la tarifa de $9.000", turno.get("tarifa_base") == 9000, turno)
    nuevo.post(f"/turnos/{turno['id']}/consumos", json={"articulo_id": articulo["id"], "cantidad": 1})
    total = 9000 + precio
    cobro = nuevo.post(f"/turnos/{turno['id']}/cerrar", json={"pagos": [{"medio_pago": "EFECTIVO", "monto": total}]})
    importe = f"{total:,.0f}".replace(",", ".")
    paso(f"El cobro incluye el precio nuevo del artículo (${importe})", cobro.status_code == 200, cobro.text)
    nuevo.patch(f"/habitaciones/{hab_id}/liberar")
    arqueo = nuevo.post("/guardias/actual/arqueo", json={"efectivo": FONDO_PRUEBA + total}).json()
    paso("Arqueo correcto con el fondo y la tarifa nuevos", arqueo.get("categoria") == "Correcto", arqueo)

    baja_hab = gerencia.patch(f"/configuracion/habitaciones/{hab_id}", json={"activa": False})
    en_grilla = any(h["id"] == hab_id for h in c1.get("/habitaciones/").json())
    paso("La habitación dada de baja sale de la grilla", baja_hab.status_code == 200 and not en_grilla, baja_hab.text)
    baja = gerencia.patch(f"/operadores/{conserje_id}", json={"activo": False})
    paso("La gerencia da de baja al conserje", baja.status_code == 200, baja.text)
    paso("El conserje dado de baja pierde la sesión (401)", nuevo.get("/auth/sesion").status_code == 401)
    propia = next(o for o in gerencia.get("/operadores/").json() if o["usuario"] == "gerencia")
    paso("La gerencia no se da de baja desde el panel (409)",
         gerencia.patch(f"/operadores/{propia['id']}", json={"activo": False}).status_code == 409)

    # Se restituyen los valores que había antes del recorrido (la tarifa vuelve como una tarifa nueva).
    restituida = {k: tarifa_anterior[k] for k in TARIFA_PRUEBA}
    gerencia.post("/configuracion/tarifas", json=restituida)
    gerencia.patch("/configuracion/caja", json={"fondo_cambio": fondo_anterior})
    gerencia.patch(f"/configuracion/articulos/{articulo['id']}", json={"precio_unitario": articulo["precio_unitario"]})
    vigente = gerencia.get("/configuracion/tarifas").json()[0]
    paso("Tarifa, fondo y precio restituidos", vigente["tarifa_base"] == tarifa_anterior["tarifa_base"]
         and gerencia.get("/configuracion/caja").json()["fondo_cambio"] == fondo_anterior)
    print("Recorrido del panel de configuración completo.")


if __name__ == "__main__":
    main()
