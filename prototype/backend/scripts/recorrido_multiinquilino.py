"""Recorrido de punta a punta del multiinquilino, el registro de actividad y el PDF del arqueo (demo Sprint 4).

Corre contra una API en ejecución (Docker), que se conecta como motel_app: lo que se comprueba acá pasa por Row Level
Security de verdad. Necesita los datos de demostración (docker compose run --rm admin): motelcc, luna y plataforma.

Uso: python -m scripts.recorrido_multiinquilino --api http://localhost:8004
     (claves: DEMO_CLAVE_GERENCIA, DEMO_CLAVE_CONSERJES y DEMO_CLAVE_PLATAFORMA, o el archivo .env de prototype/)
"""

import argparse
import secrets

import httpx

from scripts.recorrido_v2 import ENCABEZADO, leer_env, paso


def entrar(api: str, establecimiento: str, usuario: str, clave: str) -> httpx.Client:
    cliente = httpx.Client(base_url=f"{api}/api/v1", headers=ENCABEZADO, timeout=10)
    resp = cliente.post("/auth/login", json={"establecimiento": establecimiento, "usuario": usuario, "clave": clave})
    paso(f"{usuario}@{establecimiento} inicia sesión", resp.status_code == 200, resp.text)
    return cliente


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    api = parser.parse_args().api
    env = leer_env()
    gerencia, conserjes, plataforma = (
        env["DEMO_CLAVE_GERENCIA"], env["DEMO_CLAVE_CONSERJES"], env["DEMO_CLAVE_PLATAFORMA"],
    )

    # 1. Aislamiento: mismos usuarios, datos distintos.
    cc = entrar(api, "motelcc", "conserje1", conserjes)
    luna = entrar(api, "luna", "conserje1", conserjes)
    numeros_cc = {h["numero"] for h in cc.get("/habitaciones/").json()}
    numeros_luna = {h["numero"] for h in luna.get("/habitaciones/").json()}
    paso("Cada motel ve solo sus habitaciones", numeros_cc.isdisjoint(numeros_luna) and 101 in numeros_luna,
         (numeros_cc, numeros_luna))
    codigos_luna = {a["codigo"] for a in luna.get("/articulos/").json()}
    paso("Motel Luna ve solo sus artículos", "MIN-001" not in codigos_luna and "BEB-001" in codigos_luna, codigos_luna)

    # 2. El conserje de Luna carga un artículo y repone stock: la gerencia de Luna lo ve por revisar.
    luna.post("/guardias/")
    codigo = f"DEM-{secrets.token_hex(2).upper()}"
    alta = luna.post("/articulos/", json={"codigo": codigo, "descripcion": "Chocolate demo", "precio_unitario": 1300,
                                           "stock_actual": 6, "categoria": "Snacks"})
    paso("El conserje da de alta un artículo", alta.status_code == 201, alta.text)
    repo = luna.post(f"/articulos/{alta.json()['id']}/reposicion", json={"cantidad": 4})
    paso("El conserje repone stock (6 + 4 = 10)", repo.status_code == 200 and repo.json()["stock_actual"] == 10,
         repo.text)
    gerencia_luna = entrar(api, "luna", "gerencia", gerencia)
    pendientes = gerencia_luna.get("/configuracion/actividad", params={"pendientes": True}).json()
    acciones = [e["accion"] for e in pendientes if codigo in e["descripcion"]]
    paso("La gerencia de Luna ve el alta y la reposición por revisar",
         sorted(acciones) == ["ARTICULO_ALTA", "ARTICULO_REPOSICION"], pendientes)
    gerencia_cc = entrar(api, "motelcc", "gerencia", gerencia)
    ajenas = [e for e in gerencia_cc.get("/configuracion/actividad").json() if codigo in e["descripcion"]]
    paso("La gerencia de Motel C.C. no ve la actividad de Luna", not ajenas, ajenas)
    revision = gerencia_luna.post("/configuracion/actividad/revision", json={})
    paso("La gerencia marca todo como visto", revision.status_code == 200 and revision.json()["pendientes"] == 0,
         revision.text)

    # 3. RF-10: arqueo y comprobante en PDF.
    arqueo = luna.post("/guardias/actual/arqueo", json={"efectivo": 20000})
    paso("El conserje de Luna confirma su arqueo (fondo de $20.000)", arqueo.status_code == 201, arqueo.text)
    pdf = luna.get(f"/guardias/arqueos/{arqueo.json()['id']}/comprobante.pdf")
    paso("El conserje descarga el comprobante en PDF", pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
         and b"Motel Luna" in pdf.content, pdf.status_code)
    ajeno = gerencia_cc.get(f"/arqueos/{arqueo.json()['id']}/comprobante.pdf")
    paso("La gerencia de otro motel no obtiene ese comprobante (404)", ajeno.status_code == 404, ajeno.status_code)

    # 4. Plataforma: resumen, alta de un motel nuevo y suspensión.
    plat = entrar(api, "plataforma", "plataforma", plataforma)
    paso("La plataforma no opera la ventanilla (403)", plat.get("/habitaciones/").status_code == 403)
    resumen = {e["codigo"]: e for e in plat.get("/plataforma/establecimientos").json()}
    paso("La plataforma ve el resumen de los dos moteles", {"motelcc", "luna"} <= set(resumen), list(resumen))
    nuevo_codigo = f"sol-{secrets.token_hex(2)}"
    clave_nueva = f"clave-{secrets.token_hex(6)}"
    alta = plat.post("/plataforma/establecimientos", json={
        "codigo": nuevo_codigo, "nombre": "Motel Sol", "habitaciones": 4, "tarifa_base": 7000, "tarifa_fraccion": 2000,
        "fondo_cambio": 15000, "gerente_usuario": "gerencia", "gerente_nombre": "Gerencia Sol",
        "gerente_clave": clave_nueva,
    })
    paso("La plataforma da de alta Motel Sol (la base crea su gerencia inicial)", alta.status_code == 201, alta.text)
    sol = entrar(api, nuevo_codigo, "gerencia", clave_nueva)
    paso("La gerencia de Sol ve sus 4 habitaciones", len(sol.get("/habitaciones/").json()) == 4)
    suspension = plat.patch(f"/plataforma/establecimientos/{alta.json()['id']}", json={"activo": False})
    paso("La plataforma suspende Motel Sol", suspension.status_code == 200, suspension.text)
    paso("La sesión de Sol se corta en el acto (401)", sol.get("/habitaciones/").status_code == 401)
    paso("Motel C.C. sigue operando", cc.get("/habitaciones/").status_code == 200)
    print("Recorrido del multiinquilino completo.")


if __name__ == "__main__":
    main()
