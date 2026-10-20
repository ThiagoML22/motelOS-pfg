import os

# Las pruebas usan un costo de argon2 bajo para no demorar: se fija antes de importar la aplicación.
os.environ.setdefault("ARGON2_TIME_COST", "1")
os.environ.setdefault("ARGON2_MEMORY_KIB", "1024")
# Las pruebas de caja verifican la aritmética del arqueo sin fondo de cambio; el fondo aprobado ($25.000) se
# prueba aparte en test_caja (test_el_fondo_de_cambio_integra_el_efectivo_del_sistema).
os.environ.setdefault("FONDO_INICIAL_CAJA", "0")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.core.seguridad import hashear_clave  # noqa: E402
from app.main import app  # noqa: E402
from app.models.articulo import Articulo  # noqa: E402
from app.models.habitacion import Habitacion  # noqa: E402
from app.models.operador import ROL_ADMINISTRADOR, ROL_OPERADOR, Operador  # noqa: E402
from app.models.tarifa import Tarifa  # noqa: E402

# Por defecto los tests son herméticos (SQLite en memoria). En CI se puede apuntar a un
# Postgres descartable con TEST_DATABASE_URL; el nombre de la base debe contener "test"
# porque cada test recrea el esquema completo.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

if not TEST_DATABASE_URL.startswith("sqlite") and "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
    raise RuntimeError("TEST_DATABASE_URL debe apuntar a una base descartable cuyo nombre contenga 'test'.")

# Operadores de prueba: usuario -> (nombre visible, rol, clave, activo). Claves solo para estas pruebas.
OPERADORES = {
    "conserje1": ("Conserje Uno", ROL_OPERADOR, "clave-prueba-conserje1", True),
    "conserje2": ("Conserje Dos", ROL_OPERADOR, "clave-prueba-conserje2", True),
    "gerencia": ("Gerencia", ROL_ADMINISTRADOR, "clave-prueba-gerencia", True),
    "baja": ("Conserje dado de baja", ROL_OPERADOR, "clave-prueba-baja", False),
}
ENCABEZADOS_APP = {"X-Requested-With": "motelos"}


@pytest_asyncio.fixture
async def session_factory():
    kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}} if (
        TEST_DATABASE_URL.startswith("sqlite")
    ) else {}
    engine = create_async_engine(TEST_DATABASE_URL, **kwargs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [
                Tarifa(
                    nombre="Estandar",
                    tarifa_base=8000,
                    estadia_base_min=120,
                    tolerancia_min=0,
                    fraccion_min=30,
                    tarifa_fraccion=2500,
                    vigente=True,
                ),
                Habitacion(numero=1, estado="Libre"),
                Habitacion(numero=2, estado="Libre"),
                Habitacion(numero=3, estado="Mantenimiento"),
                Articulo(codigo="MIN-001", descripcion="Agua Mineral 500ml", precio_unitario=800, stock_actual=5),
                Articulo(codigo="MIN-002", descripcion="Papas Fritas", precio_unitario=1500, stock_actual=0),
            ]
            + [
                Operador(usuario=u, nombre_visible=n, rol=r, hash_clave=hashear_clave(c), activo=a)
                for u, (n, r, c, a) in OPERADORES.items()
            ]
        )
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


def nuevo_cliente() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=ENCABEZADOS_APP)


async def iniciar_sesion(ac: AsyncClient, usuario: str) -> None:
    clave = OPERADORES[usuario][2]
    resp = await ac.post("/api/v1/auth/login", json={"usuario": usuario, "clave": clave})
    assert resp.status_code == 200, resp.text


@pytest_asyncio.fixture
async def anonimo(session_factory):
    """Cliente sin sesión (con el encabezado de la aplicación)."""
    async with nuevo_cliente() as ac:
        yield ac


async def abrir_guardia(ac: AsyncClient) -> dict:
    resp = await ac.post("/api/v1/guardias/")
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def client(session_factory):
    """Cliente de conserje1 con su guardia abierta: es el operador con el que corren las pruebas de la v1."""
    async with nuevo_cliente() as ac:
        await iniciar_sesion(ac, "conserje1")
        await abrir_guardia(ac)
        yield ac


@pytest_asyncio.fixture
async def cliente_como(session_factory):
    """Fábrica de clientes con sesión iniciada como el usuario indicado."""
    abiertos: list[AsyncClient] = []

    async def crear(usuario: str) -> AsyncClient:
        ac = nuevo_cliente()
        abiertos.append(ac)
        await iniciar_sesion(ac, usuario)
        return ac

    yield crear
    for ac in abiertos:
        await ac.aclose()


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session
