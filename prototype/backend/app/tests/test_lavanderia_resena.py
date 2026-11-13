"""Migración 018: lavandería propia o de afuera, motivo «Otro» al registrar un cliente que se fue y reseña corta del
cliente, con el filtro de palabras de app/services/moderacion.py."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.actividad import RegistroActividad
from app.models.calificacion import Calificacion
from app.models.cliente_perdido import ClientePerdido
from app.services import moderacion

OPERACION = "/api/v1/operacion"
PERDIDOS = "/api/v1/clientes-perdidos/"


@pytest_asyncio.fixture
async def gerencia(cliente_como):
    return await cliente_como("gerencia")


async def _enlace(cliente) -> str:
    resp = await cliente.post("/api/v1/turnos/", json={"habitacion_id": 1, "tipo_cliente": "Auto"})
    assert resp.status_code == 201, resp.text
    ticket = await cliente.get(f"/api/v1/turnos/{resp.json()['id']}/ticket")
    return "/api/v1/cliente/" + ticket.json()["direccion"].split("cliente=")[1]


# --- El filtro de palabras -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Muy limpio y cómodo",
        "Excelente atención, volveremos",
        "La película no andaba",
        "Me da vergüenza el baño",
        "El pedido llegó retrasado",
        "Un asco el baño",
        "La canilla chorrea",
        "Habitación 4 impecable",
        "Todo bien.me gustó",
    ],
)
def test_el_filtro_deja_pasar_lo_comun(texto):
    assert moderacion.revisar(texto) is None


@pytest.mark.parametrize(
    "texto",
    [
        "son unos pelotudos",
        "P.U.T.O el que lee",
        "boluuuudo",
        "h d p",
        "andate a la m1erd4",
        "el conserje es un gil",
        "IDIOTAS",
        "una estafa",
    ],
)
def test_el_filtro_frena_groserias_e_insultos(texto):
    assert moderacion.revisar(texto) == moderacion.MOTIVO_GROSERO


@pytest.mark.parametrize("texto", ["llamame 3764 123456", "visitá www.algo.com", "a x@y.com", "seguinos @motel"])
def test_el_filtro_frena_datos_de_contacto(texto):
    assert moderacion.revisar(texto) == moderacion.MOTIVO_CONTACTO


def test_contar_palabras():
    assert moderacion.contar_palabras("  muy   bien  ") == 2
    assert moderacion.contar_palabras("") == 0


# --- Se fue un cliente: «Otro» -------------------------------------------------------------------------------------


async def test_otro_lleva_lo_que_escribio_el_conserje(client, db):
    resp = await client.post(PERDIDOS, json={"motivo": "OTRO", "detalle": "  Venía   con mascota "})
    assert resp.status_code == 201, resp.text
    # En otro motivo el detalle no se guarda.
    assert (await client.post(PERDIDOS, json={"motivo": "PRECIO", "detalle": "caro"})).status_code == 201
    filas = list((await db.execute(select(ClientePerdido).order_by(ClientePerdido.id))).scalars())
    assert [(f.motivo, f.detalle) for f in filas] == [("OTRO", "Venía con mascota"), ("PRECIO", None)]


@pytest.mark.parametrize("detalle", [None, "   ", "se fue un boludo", "llamar al 3764 555 1234"])
async def test_otro_sin_detalle_o_con_groserias_no_entra(client, detalle):
    resp = await client.post(PERDIDOS, json={"motivo": "OTRO", "detalle": detalle})
    assert resp.status_code == 422


async def test_la_gerencia_ve_los_otros_motivos_agrupados(client, gerencia):
    for detalle in ("Venía con mascota", "venía con  mascota", "Quería cochera techada"):
        await client.post(PERDIDOS, json={"motivo": "OTRO", "detalle": detalle})
    # El análisis mira las guardias ya cerradas.
    arqueo = {"efectivo": 0, "posnet": 0, "mercado_pago": 0}
    assert (await client.post("/api/v1/guardias/actual/arqueo", json=arqueo)).status_code == 201
    perdidos =(await gerencia.get("/api/v1/inteligencia/tablero")).json()["clientes_perdidos"]
    assert perdidos["otros"][0]["cantidad"] == 2 and perdidos["otros"][1]["detalle"] == "Quería cochera techada"
    assert next(m for m in perdidos["motivos"] if m["motivo"] == "OTRO")["etiqueta"] == "Otro motivo"


# --- La reseña del cliente -----------------------------------------------------------------------------------------


async def test_con_cuatro_estrellas_se_marca_que_fallo_y_se_deja_una_resena(client, anonimo, db):
    enlace = await _enlace(client)
    cuerpo = {"puntaje": 4, "problemas": 2, "resena": "  Muy lindo,  algo de ruido "}
    resp = await anonimo.post(f"{enlace}/calificacion", json=cuerpo)
    assert resp.status_code == 201, resp.text
    fila = (await db.execute(select(Calificacion))).scalars().one()
    assert (fila.puntaje, fila.problemas, fila.resena) == (4, 2, "Muy lindo, algo de ruido")


async def test_una_resena_en_blanco_no_se_guarda(client, anonimo, db):
    enlace = await _enlace(client)
    assert (await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 5, "resena": "   "})).status_code == 201
    assert (await db.execute(select(Calificacion.resena))).scalar_one() is None


@pytest.mark.parametrize(
    ("resena", "mensaje"),
    [
        ("uno dos tres cuatro cinco seis siete", "6 palabras"),
        ("conserje pelotudo", "groseras"),
        ("escribime a algo@correo.com", "correos"),
    ],
)
async def test_la_resena_es_corta_y_sin_groserias(client, anonimo, db, resena, mensaje):
    enlace = await _enlace(client)
    resp = await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 2, "resena": resena})
    assert resp.status_code == 422 and mensaje in resp.json()["detail"]
    # No quedó nada a medias: puede volver a calificar.
    assert (await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 2})).status_code == 201


async def test_la_gerencia_lee_las_resenas_sin_hora_ni_habitacion(client, anonimo, gerencia):
    enlace = await _enlace(client)
    await anonimo.post(f"{enlace}/calificacion", json={"puntaje": 5, "resena": "Excelente, volveremos"})
    opiniones = (await gerencia.get("/api/v1/inteligencia/tablero")).json()["opiniones"]
    assert opiniones["resenas"] == [{"puntaje": 5, "texto": "Excelente, volveremos"}]


# --- Lavandería propia o de afuera ---------------------------------------------------------------------------------


async def test_con_lavanderia_propia_solo_se_anotan_compras_y_bajas(client):
    assert (await client.get(f"{OPERACION}/ropa/ajustes")).json() == {"por_estado": True, "lavanderia_propia": True}
    sale = {"prenda": "SABANAS", "tipo": "LAVANDERIA_SALE", "cantidad": 10}
    resp = await client.post(f"{OPERACION}/ropa/movimientos", json=sale)
    assert resp.status_code == 422 and "se lava acá" in resp.json()["detail"]
    compra = {"prenda": "TOALLAS", "tipo": "COMPRA", "cantidad": 12}
    assert (await client.post(f"{OPERACION}/ropa/movimientos", json=compra)).status_code == 201


async def test_la_gerencia_elige_una_lavanderia_de_afuera(client, gerencia, db):
    assert (await client.patch(f"{OPERACION}/ropa/lavanderia", json={"propia": False})).status_code == 403
    resp = await gerencia.patch(f"{OPERACION}/ropa/lavanderia", json={"propia": False})
    assert resp.status_code == 200 and resp.json() == {"lavanderia_propia": False}
    assert (await client.get(f"{OPERACION}/ropa/ajustes")).json()["lavanderia_propia"] is False

    sale = {"prenda": "SABANAS", "tipo": "LAVANDERIA_SALE", "cantidad": 10}
    assert (await client.post(f"{OPERACION}/ropa/movimientos", json=sale)).status_code == 201
    ropa = (await gerencia.get(f"{OPERACION}/tablero")).json()["ropa"]
    assert ropa["lavanderia_propia"] is False
    assert next(r for r in ropa["resumen"] if r["prenda"] == "SABANAS")["en_lavanderia"] == 10

    cambio = (
        (await db.execute(select(RegistroActividad).where(RegistroActividad.accion == "ROPA_LAVANDERIA")))
        .scalars()
        .one()
    )
    assert "lavandería de afuera" in cambio.descripcion and cambio.categoria == "OPERACION"
    # Volver a elegir lo mismo no anota otro cambio.
    await gerencia.patch(f"{OPERACION}/ropa/lavanderia", json={"propia": False})
    cambios = await db.execute(select(RegistroActividad).where(RegistroActividad.accion == "ROPA_LAVANDERIA"))
    assert len(list(cambios.scalars())) == 1
