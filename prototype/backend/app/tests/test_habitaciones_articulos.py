from httpx import AsyncClient


async def test_listar_habitaciones_ordenadas_e_incluye_turno_activo(client: AsyncClient):
    await client.post("/api/v1/turnos/", json={"habitacion_id": 2, "tipo_cliente": "Auto"})

    resp = await client.get("/api/v1/habitaciones/")

    assert resp.status_code == 200
    data = resp.json()
    assert [h["numero"] for h in data] == [1, 2, 3]
    assert set(data[0]) == {"id", "numero", "estado", "turno_activo"}
    assert data[0]["turno_activo"] is None
    assert data[1]["estado"] == "Ocupada"
    assert data[1]["turno_activo"]["estado"] == "En Curso"


async def test_liberar_solo_permite_habitacion_en_limpieza(client: AsyncClient):
    assert (await client.patch("/api/v1/habitaciones/1/liberar")).status_code == 400
    assert (await client.patch("/api/v1/habitaciones/999/liberar")).status_code == 404


async def test_cambiar_estado_manual(client: AsyncClient):
    assert (await client.patch("/api/v1/habitaciones/1/estado", json={"estado": "Mantenimiento"})).status_code == 200
    assert (await client.patch("/api/v1/habitaciones/1/estado", json={"estado": "Libre"})).status_code == 200


async def test_cambiar_estado_rechaza_valor_invalido_y_habitacion_ocupada(client: AsyncClient):
    assert (await client.patch("/api/v1/habitaciones/1/estado", json={"estado": "Ocupada"})).status_code == 400

    await client.post("/api/v1/turnos/", json={"habitacion_id": 2})
    resp = await client.patch("/api/v1/habitaciones/2/estado", json={"estado": "Libre"})
    assert resp.status_code == 400


async def test_cambiar_estado_habitacion_inexistente_devuelve_404(client: AsyncClient):
    assert (await client.patch("/api/v1/habitaciones/999/estado", json={"estado": "Libre"})).status_code == 404


async def test_listar_y_crear_articulos(client: AsyncClient):
    nuevo = {"codigo": "SNA-001", "descripcion": "Papas Fritas", "precio_unitario": 1500, "stock_actual": 5}

    creado = await client.post("/api/v1/articulos/", json=nuevo)
    assert creado.status_code == 201
    assert creado.json()["codigo"] == "SNA-001"

    codigos = [a["codigo"] for a in (await client.get("/api/v1/articulos/")).json()]
    assert set(codigos) == {"MIN-001", "SNA-001"}


async def test_crear_articulo_codigo_duplicado_devuelve_400(client: AsyncClient):
    dup = {"codigo": "MIN-001", "descripcion": "Otra", "precio_unitario": 1, "stock_actual": 1}
    assert (await client.post("/api/v1/articulos/", json=dup)).status_code == 400


async def test_crear_articulo_con_stock_negativo_devuelve_422(client: AsyncClient):
    malo = {"codigo": "X-1", "descripcion": "Malo", "precio_unitario": 1, "stock_actual": -1}
    assert (await client.post("/api/v1/articulos/", json=malo)).status_code == 422
