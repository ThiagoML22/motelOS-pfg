"""RNF-08: la patente se separa del turno inmutable y se elimina dentro del plazo posterior al cierre."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import inspect, select

from app.models.estadia_activa import EstadiaActiva
from app.models.turno import Turno
from app.services.estadia import depurar_patentes


async def _abrir(client: AsyncClient, habitacion_id: int, **extra) -> dict:
    resp = await client.post("/api/v1/turnos/", json={"habitacion_id": habitacion_id, **extra})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _cerrar(client: AsyncClient, turno_id: str) -> None:
    resumen = (await client.get(f"/api/v1/turnos/{turno_id}/resumen")).json()
    pagos = {"pagos": [{"medio_pago": "EFECTIVO", "monto": resumen["saldo_pendiente"]}]}
    resp = await client.post(f"/api/v1/turnos/{turno_id}/cerrar", json=pagos)
    assert resp.status_code == 200, resp.text


async def _patentes(db) -> list[str]:
    db.expire_all()
    return [e.identificador_vehicular for e in (await db.execute(select(EstadiaActiva))).scalars().all()]


async def test_el_turno_no_guarda_la_patente(session_factory):
    async with session_factory() as db:
        columnas = await db.run_sync(lambda s: [c["name"] for c in inspect(s.connection()).get_columns("turnos")])
    assert "identificador_vehicular" not in columnas


async def test_la_patente_vive_en_la_estadia_activa_y_se_muestra_con_el_turno_en_curso(client: AsyncClient, db):
    turno = await _abrir(client, 1, identificador_vehicular="AE987CD")

    assert turno["identificador_vehicular"] == "AE987CD"
    assert await _patentes(db) == ["AE987CD"]
    resumen = (await client.get(f"/api/v1/turnos/{turno['id']}/resumen")).json()
    assert resumen["identificador_vehicular"] == "AE987CD"
    habitaciones = (await client.get("/api/v1/habitaciones/")).json()
    activo = next(h["turno_activo"] for h in habitaciones if h["numero"] == 1)
    assert activo["identificador_vehicular"] == "AE987CD"


async def test_un_turno_sin_patente_no_crea_estadia_activa(client: AsyncClient, db):
    await _abrir(client, 1, tipo_cliente="Peaton")
    assert await _patentes(db) == []


async def test_la_patente_se_conserva_dentro_del_plazo_y_se_elimina_al_vencer(client: AsyncClient, db):
    turno = await _abrir(client, 1, identificador_vehicular="AE987CD")
    await _cerrar(client, turno["id"])
    cierre = (await db.execute(select(Turno.hora_fin))).scalar_one()
    cierre = cierre.replace(tzinfo=UTC) if cierre.tzinfo is None else cierre

    assert await depurar_patentes(db, horas=24, ahora=cierre + timedelta(hours=23)) == 0
    assert await _patentes(db) == ["AE987CD"]

    assert await depurar_patentes(db, horas=24, ahora=cierre + timedelta(hours=25)) == 1
    assert await _patentes(db) == []


async def test_la_depuracion_no_toca_turnos_en_curso(client: AsyncClient, db):
    await _abrir(client, 1, identificador_vehicular="AE987CD")

    eliminadas = await depurar_patentes(db, horas=24, ahora=datetime.now(UTC) + timedelta(days=30))

    assert eliminadas == 0
    assert await _patentes(db) == ["AE987CD"]


async def test_la_depuracion_conserva_el_registro_financiero_del_turno(client: AsyncClient, db):
    turno = await _abrir(client, 1, identificador_vehicular="AE987CD")
    await _cerrar(client, turno["id"])
    antes = (await db.execute(select(Turno.total_general, Turno.estado, Turno.hora_fin))).one()

    await depurar_patentes(db, horas=24, ahora=datetime.now(UTC) + timedelta(days=2))

    db.expire_all()
    despues = (await db.execute(select(Turno.total_general, Turno.estado, Turno.hora_fin))).one()
    assert despues == antes
    assert await _patentes(db) == []


async def test_verificacion_rnf_08_no_quedan_patentes_de_turnos_cerrados_vencidos(client: AsyncClient, db):
    """Criterio de aceptaciÃ³n de RNF-08: ninguna patente de un turno cerrado hace mÃ¡s de N horas."""
    turno = await _abrir(client, 1, identificador_vehicular="AE987CD")
    await _cerrar(client, turno["id"])
    ahora = datetime.now(UTC) + timedelta(hours=30)

    await depurar_patentes(db, horas=24, ahora=ahora)

    limite = ahora - timedelta(hours=24)
    vencidas = (
        await db.execute(
            select(EstadiaActiva)
            .join(Turno, Turno.id == EstadiaActiva.turno_id)
            .where(Turno.estado != "En Curso", Turno.hora_fin <= limite)
        )
    ).scalars().all()
    assert vencidas == []
