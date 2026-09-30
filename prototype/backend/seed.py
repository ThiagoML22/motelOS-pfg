import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.habitacion import Habitacion


async def seed_data():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        for i in range(1, 14):
            habitacion = Habitacion(numero=i, estado='Libre')
            session.add(habitacion)
        await session.commit()
    print("Seed finalizado: 13 habitaciones creadas en estado Libre.")

if __name__ == "__main__":
    asyncio.run(seed_data())
