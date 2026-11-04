"""Demostración de los comprobantes verificables: altera un arqueo directamente en la base, como lo haría alguien con
acceso a la base, para ver cómo lo detecta la verificación de Control de caja.

Le resta $ 5.000 a lo declarado en efectivo de un arqueo de Motel C.C., saltando las reglas de la base (corre como dueño
de las tablas y con session_replication_role = replica). `deshacer` devuelve lo alterado.

Uso (Docker): docker compose run --rm admin scripts.alterar_arqueo [deshacer]
"""

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.inquilino import CLAVE
from app.models.arqueo import ArqueoCaja
from app.models.establecimiento import Establecimiento
from app.services.sellos import verificar_cadena

CODIGO = "motelcc"
MONTO = Decimal("5000")
# El arqueo que se altera: unos días antes del último, para que no sea el primero que se mira.
ATRAS = 12


def _aplicar(arqueo: ArqueoCaja, cambio: Decimal) -> None:
    arqueo.declarado_efectivo += cambio
    arqueo.total_declarado += cambio
    arqueo.diferencia += cambio


async def alterar(deshacer: bool) -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    sesiones = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sesiones() as db:
            establecimiento = (
                (await db.execute(select(Establecimiento).where(Establecimiento.codigo == CODIGO))).scalars().first()
            )
        async with sesiones(info={CLAVE: establecimiento.id}) as db:
            await db.execute(text("SET LOCAL session_replication_role = replica"))
            if deshacer:
                resultado = await verificar_cadena(db)
                for alterado in resultado["alterados"]:
                    arqueo = await db.get(ArqueoCaja, alterado["arqueo_id"])
                    _aplicar(arqueo, MONTO)
                    print(f"Arqueo N.º {arqueo.id}: se devolvieron $ {MONTO}.")
                if not resultado["alterados"]:
                    print("No hay ningún arqueo alterado.")
            else:
                arqueos = list((await db.execute(select(ArqueoCaja).order_by(ArqueoCaja.confirmado_en))).scalars())
                arqueo = arqueos[-min(ATRAS, len(arqueos))]
                _aplicar(arqueo, -MONTO)
                await db.flush()
                print(f"Arqueo N.º {arqueo.id}: se le restaron $ {MONTO} a lo declarado en efectivo.")
                print("Ahora entrá a Control de caja y tocá «Verificar ahora».")
            await db.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(alterar(len(sys.argv) > 1 and sys.argv[1] == "deshacer"))
