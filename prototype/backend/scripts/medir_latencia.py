"""RNF-02: el backend responde la apertura y el cobro de un turno en 800 ms o menos (percentil 95).

Criterio de aceptación del catálogo: 5 peticiones concurrentes de apertura y 5 de cobro, repetidas 20
veces; el percentil 95 de las latencias debe ser de 800 ms o menos. El script corre contra una API en
ejecución con un conserje de demostración, abre su guardia si no tiene una, y al terminar la cierra con
un arqueo correcto (declara el fondo de cambio más lo que cobró). Escribe cada medición en un CSV con fecha y hora.

Uso: python -m scripts.medir_latencia --api http://localhost:8000 --salida latencia.csv
"""

import argparse
import asyncio
import csv
import math
import sys
import time
from datetime import datetime

import httpx

from scripts.recorrido_v2 import ENCABEZADO, leer_env

UMBRAL_MS = 800.0
CONCURRENCIA = 5
REPETICIONES = 20


def percentil(valores: list[float], p: float) -> float:
    """Percentil por rango más cercano (sin interpolar): el valor que deja el p % de las muestras por debajo."""
    ordenados = sorted(valores)
    rango = max(1, math.ceil(p / 100 * len(ordenados)))
    return ordenados[rango - 1]


async def medir(cliente: httpx.AsyncClient, metodo: str, url: str, **kwargs) -> tuple[float, httpx.Response]:
    inicio = time.perf_counter()
    resp = await cliente.request(metodo, url, **kwargs)
    return (time.perf_counter() - inicio) * 1000, resp


async def preparar(cliente: httpx.AsyncClient) -> float | None:
    """Deja libres las habitaciones en limpieza y abre la guardia.

    Devuelve el fondo de cambio de la guardia si la abrió el script, o None si ya estaba abierta.
    """
    for hab in (await cliente.get("/habitaciones/")).json():
        if hab["estado"] == "En Limpieza":
            await cliente.patch(f"/habitaciones/{hab['id']}/liberar")
    sesion = (await cliente.get("/auth/sesion")).json()
    if sesion["guardia"] is None:
        resp = await cliente.post("/guardias/")
        resp.raise_for_status()
        return float(resp.json()["fondo_inicial"])
    if not sesion["guardia"]["es_propia"]:
        sys.exit("La ventanilla tiene una guardia abierta de otro operador.")
    return None


async def principal(api: str, salida: str | None, usuario: str) -> int:
    env = leer_env()
    clave = env.get("DEMO_CLAVE_CONSERJES")
    if not clave:
        sys.exit("Falta DEMO_CLAVE_CONSERJES")
    filas: list[dict] = []
    cobrado = 0.0
    async with httpx.AsyncClient(base_url=f"{api}/api/v1", headers=ENCABEZADO, timeout=30) as cliente:
        login = await cliente.post("/auth/login", json={"usuario": usuario, "clave": clave})
        login.raise_for_status()
        fondo = await preparar(cliente)

        for repeticion in range(1, REPETICIONES + 1):
            libres = [h["id"] for h in (await cliente.get("/habitaciones/")).json() if h["estado"] == "Libre"]
            if len(libres) < CONCURRENCIA:
                sys.exit(f"Se necesitan {CONCURRENCIA} habitaciones libres y hay {len(libres)}.")
            elegidas = libres[:CONCURRENCIA]

            aperturas = await asyncio.gather(
                *(medir(cliente, "POST", "/turnos/", json={"habitacion_id": h}) for h in elegidas)
            )
            turnos = []
            for (ms, resp), habitacion in zip(aperturas, elegidas, strict=True):
                filas.append({"repeticion": repeticion, "operacion": "apertura", "ms": round(ms, 1),
                              "estado_http": resp.status_code})
                if resp.status_code == 201:
                    turnos.append((resp.json(), habitacion))

            cobros = await asyncio.gather(
                *(
                    medir(cliente, "POST", f"/turnos/{t['id']}/cerrar",
                          json={"pagos": [{"medio_pago": "EFECTIVO", "monto": t["total_general"]}]})
                    for t, _ in turnos
                )
            )
            for (ms, resp), (turno, _) in zip(cobros, turnos, strict=True):
                filas.append({"repeticion": repeticion, "operacion": "cobro", "ms": round(ms, 1),
                              "estado_http": resp.status_code})
                if resp.status_code == 200:
                    cobrado += turno["total_general"]
            for _, habitacion in turnos:
                await cliente.patch(f"/habitaciones/{habitacion}/liberar")

        if fondo is not None:
            declarado = round(fondo + cobrado, 2)
            arqueo = (await cliente.post("/guardias/actual/arqueo", json={"efectivo": declarado})).json()
            print(f"Guardia de medición cerrada: arqueo {arqueo.get('categoria')} por {arqueo.get('total_sistema')}")

    fallidas = [f for f in filas if f["estado_http"] not in (200, 201)]
    resultados = {}
    for operacion in ("apertura", "cobro"):
        valores = [f["ms"] for f in filas if f["operacion"] == operacion and f["estado_http"] in (200, 201)]
        resultados[operacion] = percentil(valores, 95) if valores else float("inf")
    p95_total = percentil([f["ms"] for f in filas if f["estado_http"] in (200, 201)], 95)

    marca = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"Medición RNF-02 ({marca}): {len(filas)} peticiones, {len(fallidas)} con error")
    for operacion, valor in resultados.items():
        print(f"  P95 {operacion}: {valor:.1f} ms")
    print(f"  P95 total: {p95_total:.1f} ms (umbral {UMBRAL_MS:.0f} ms)")

    if salida:
        with open(salida, "w", newline="", encoding="utf-8") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=["fecha", "repeticion", "operacion", "ms", "estado_http"])
            escritor.writeheader()
            for fila in filas:
                escritor.writerow({"fecha": marca, **fila})
        print(f"  Mediciones guardadas en {salida}")

    cumple = not fallidas and all(v <= UMBRAL_MS for v in resultados.values())
    print("RNF-02 cumplido." if cumple else "RNF-02 NO cumplido.")
    return 0 if cumple else 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--salida", help="CSV con cada medición")
    parser.add_argument("--usuario", default="conserje1")
    args = parser.parse_args()
    sys.exit(asyncio.run(principal(args.api, args.salida, args.usuario)))


if __name__ == "__main__":
    main()
