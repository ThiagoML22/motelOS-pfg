"""Alta de operadores por el script de administración (la API no puede crearlos)."""

import pytest
from sqlalchemy import select

from app.core.seguridad import verificar_clave
from app.models.operador import Operador
from scripts.crear_operador import alta_operador, restablecer_clave


async def test_alta_guarda_solo_el_hash_de_la_clave(db):
    operador = await alta_operador(db, "Conserje3", "Conserje Tres", "OPERADOR", "una-clave-larga")

    assert operador.usuario == "conserje3"
    assert operador.hash_clave != "una-clave-larga"
    assert operador.hash_clave.startswith("$argon2id$")
    assert verificar_clave(operador.hash_clave, "una-clave-larga")


@pytest.mark.parametrize(
    ("usuario", "rol", "clave"),
    [
        ("ab", "OPERADOR", "una-clave-larga"),  # usuario corto
        ("con espacio", "OPERADOR", "una-clave-larga"),
        ("conserje9", "SUPERUSUARIO", "una-clave-larga"),
        ("conserje9", "OPERADOR", "corta"),
        ("conserje1", "OPERADOR", "una-clave-larga"),  # ya existe
    ],
)
async def test_alta_rechaza_datos_invalidos(db, usuario, rol, clave):
    with pytest.raises(ValueError):
        await alta_operador(db, usuario, "X", rol, clave)


async def test_restablecer_clave_quita_el_bloqueo(db, anonimo):
    operador = (await db.execute(select(Operador).where(Operador.usuario == "conserje2"))).scalar_one()
    operador.intentos_fallidos = 4
    await db.commit()

    await restablecer_clave(db, "conserje2", "clave-restablecida")

    resp = await anonimo.post("/api/v1/auth/login", json={"usuario": "conserje2", "clave": "clave-restablecida"})
    assert resp.status_code == 200
