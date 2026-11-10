from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.SQL_ECHO)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# Registra los eventos que aíslan cada establecimiento (filtro, alta y Row Level Security).
import app.core.inquilino  # noqa: E402, F401


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
