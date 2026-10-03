import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.articulo import Articulo
from app.models.habitacion import Habitacion
from app.models.tarifa import Tarifa

# Por defecto los tests son herméticos (SQLite en memoria). En CI se puede apuntar a un
# Postgres descartable con TEST_DATABASE_URL; el nombre de la base debe contener "test"
# porque cada test recrea el esquema completo.
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

if not TEST_DATABASE_URL.startswith("sqlite") and "test" not in TEST_DATABASE_URL.rsplit("/", 1)[-1]:
    raise RuntimeError("TEST_DATABASE_URL debe apuntar a una base descartable cuyo nombre contenga 'test'.")


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
        )
        await session.commit()

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(session_factory):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session
