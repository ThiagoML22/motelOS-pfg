"""Recorrido de punta a punta del prototipo v2 contra una API en ejecución (Docker).

Reproduce el caso del dictamen: un turno que abre la guardia saliente y cobra la entrante (RN-DER-04),
con un arqueo con faltante y otro correcto, y comprueba los rechazos de seguridad. Necesita una base
recién creada con los operadores de demostración (docker compose run --rm admin).

Uso: python -m scripts.recorrido_v2 --api http://localhost:8000
     (las claves se leen de DEMO_CLAVE_GERENCIA y DEMO_CLAVE_CONSERJES, o del archivo .env de src/)
"""

import argparse
import os
import sys
from pathlib import Path

import httpx

ENCABEZADO = {"X-Requested-With": "motelos"}


def leer_env() -> dict[str, str]:
    valores = dict(os.environ)
    archivo = Path(__file__).resolve().parents[2] / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                clave, valor = linea.split("=", 1)
                valores.setdefault(clave.strip(), valor.strip())
    return valores


def paso(descripcion: str, condicion: bool, detalle: object = "") -> None:
    print(f"[{'OK' if condicion else 'FALLA'}] {descripcion}")
    if not condicion:
        print(f"       {detalle}")
        sys.exit(1)


def sesion(api: str, usuario: str, clave: str) -> httpx.Client:
    cliente = httpx.Client(base_url=f"{api}/api/v1", headers=ENCABEZADO, timeout=10)
    resp = cliente.post("/auth/login", json={"usuario": usuario, "clave": clave})
    paso(f"{usuario} inicia sesión", resp.status_code == 200, resp.text)
    return cliente


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    env = leer_env()
    clave_conserjes, clave_gerencia = env.get("DEMO_CLAVE_CONSERJES"), env.get("DEMO_CLAVE_GERENCIA")
    if not clave_conserjes or not clave_gerencia:
        sys.exit("Faltan DEMO_CLAVE_CONSERJES y DEMO_CLAVE_GERENCIA")

    anonimo = httpx.Client(base_url=f"{args.api}/api/v1", headers=ENCABEZADO, timeout=10)
    paso("Sin sesión la API responde 401", anonimo.get("/habitaciones/").status_code == 401)
    malo = anonimo.post("/auth/login", json={"usuario": "conserje1", "clave": "incorrecta"})
    paso("Clave incorrecta: 401 con mensaje genérico", malo.status_code == 401, malo.text)

    c1 = sesion(args.api, "conserje1", clave_conserjes)
    sin_encabezado = httpx.post(f"{args.api}/api/v1/guardias/", cookies=c1.cookies, timeout=10)
    paso("POST sin el encabezado de la aplicación: 403 (CSRF)", sin_encabezado.status_code == 403)
    paso("Sin guardia no se abre un turno (409)", c1.post("/turnos/", json={"habitacion_id": 1}).status_code == 409)

    g14 = c1.post("/guardias/")
    paso("Conserje 1 abre su guardia", g14.status_code == 201, g14.text)
    # Fondo de cambio de la caja ($25.000 según el acta del 19/10/2026): integra el efectivo esperado.
    fondo_14 = g14.json()["fondo_inicial"]

    t1 = c1.post("/turnos/", json={"habitacion_id": 1, "identificador_vehicular": "AE987CD"}).json()
    c1.post(f"/turnos/{t1['id']}/consumos", json={"articulo_id": 1, "cantidad": 2})
    cobro = c1.post(f"/turnos/{t1['id']}/cerrar", json={"pagos": [{"medio_pago": "EFECTIVO", "monto": 9600}]})
    paso("Turno de la habitación 1 cobrado en efectivo ($9.600)", cobro.status_code == 200, cobro.text)
    c1.patch("/habitaciones/1/liberar")

    t2 = c1.post("/turnos/", json={"habitacion_id": 2}).json()
    paso("Turno de la habitación 2 abierto por Conserje 1 (queda en curso)", t2.get("estado") == "En Curso", t2)

    textos = [c1.get(r).text for r in ("/habitaciones/", "/guardias/actual", "/auth/sesion", "/articulos/")]
    paso("RN-RES-03: ninguna respuesta del conserje incluye totales de la guardia",
         all("total_sistema" not in t and "sistema_" not in t for t in textos))
    paso("El conserje no accede al panel de la gerencia (403)", c1.get("/arqueos/").status_code == 403)

    a14 = c1.post("/guardias/actual/arqueo", json={"efectivo": fondo_14 + 9100})
    datos = a14.json()
    paso("Arqueo de Conserje 1: faltante de $500 calculado por la base (con el fondo de cambio)",
         a14.status_code == 201 and datos["total_sistema"] == fondo_14 + 9600 and datos["diferencia"] == -500
         and datos["categoria"] == "Faltante", a14.text)

    c2 = sesion(args.api, "conserje2", clave_conserjes)
    g22 = c2.post("/guardias/")
    paso("Conserje 2 abre la guardia siguiente", g22.status_code == 201, g22.text)
    fondo_22 = g22.json()["fondo_inicial"]
    hab2 = next(h for h in c2.get("/habitaciones/").json() if h["id"] == 2)
    paso("El turno en curso muestra quién lo abrió", hab2["turno_activo"]["abierto_por"] == "Conserje 1", hab2)
    cobro2 = c2.post(f"/turnos/{t2['id']}/cerrar",
                     json={"pagos": [{"medio_pago": "POSNET", "monto": 8000, "comprobante_referencia": "CUP-0001"}]})
    paso("RN-DER-04: Conserje 2 cobra el turno abierto por Conserje 1", cobro2.status_code == 200, cobro2.text)
    a22 = c2.post("/guardias/actual/arqueo", json={"efectivo": fondo_22, "posnet": 8000}).json()
    paso("Arqueo de Conserje 2: el cobro cruzado entra a su caja y da Correcto",
         a22["total_sistema"] == fondo_22 + 8000 and a22["categoria"] == "Correcto", a22)

    gerencia = sesion(args.api, "gerencia", clave_gerencia)
    metricas = gerencia.get("/arqueos/metricas").json()
    paso("Panel de gerencia: 2 arqueos, TDC del 50 %",
         metricas["general"]["arqueos"] == 2 and metricas["general"]["tdc"] == 0.5, metricas)
    print("Recorrido del prototipo v2 completo.")


if __name__ == "__main__":
    main()
