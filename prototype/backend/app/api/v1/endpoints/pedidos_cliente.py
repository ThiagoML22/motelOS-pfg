"""La ventanilla atiende lo que el cliente pidió desde su habitación (migración 013)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import operador_actual
from app.core.database import get_db
from app.models.operador import Operador
from app.models.pedido_cliente import ARTICULO
from app.services import acceso_cliente
from app.services.caja import guardia_del_operador
from app.services.consumos import cargar_consumo

router = APIRouter()


@router.get("/")
async def pendientes(db: AsyncSession = Depends(get_db)) -> list[dict]:
    return await acceso_cliente.pendientes_de_la_ventanilla(db)


@router.post("/{pedido_id}/llevar", status_code=status.HTTP_200_OK)
async def llevar(
    pedido_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    """El cliente lo ve en camino. Se carga a la cuenta recién al entregarlo."""
    pedido = await acceso_cliente.bloquear_sin_resolver(db, pedido_id)
    await guardia_del_operador(db, operador)
    acceso_cliente.llevar(pedido, operador.id)
    await db.commit()
    return {"ok": True}


@router.post("/{pedido_id}/atender", status_code=status.HTTP_200_OK)
async def atender(
    pedido_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    """Atender un artículo lo carga como consumo, con el control de stock y de guardia de siempre."""
    pedido = await acceso_cliente.bloquear_sin_resolver(db, pedido_id)
    if pedido.tipo == ARTICULO:
        await cargar_consumo(db, pedido.turno_id, pedido.articulo_id, pedido.cantidad, operador)
    else:
        await guardia_del_operador(db, operador)
    acceso_cliente.resolver(pedido, operador.id, atendido=True)
    await db.commit()
    return {"ok": True}


@router.post("/{pedido_id}/rechazar", status_code=status.HTTP_200_OK)
async def rechazar(
    pedido_id: int, db: AsyncSession = Depends(get_db), operador: Operador = Depends(operador_actual)
) -> dict:
    pedido = await acceso_cliente.bloquear_sin_resolver(db, pedido_id)
    await guardia_del_operador(db, operador)
    acceso_cliente.resolver(pedido, operador.id, atendido=False)
    await db.commit()
    return {"ok": True}
