"""Presentación de los arqueos confirmados (RF-08, RF-09).

Solo trabaja sobre arqueos, que existen únicamente para guardias cerradas: nada de lo que se muestra
expone el total de una guardia abierta (RN-RES-03).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.operador import Operador
from app.schemas.caja import ArqueoResultado


async def resultado_de_arqueo(db: AsyncSession, arqueo: ArqueoCaja) -> ArqueoResultado:
    guardia = await db.get(Guardia, arqueo.guardia_id)
    operador = await db.get(Operador, arqueo.operador_id)
    supervisado = arqueo.confirmado_por_id is not None and arqueo.confirmado_por_id != arqueo.operador_id
    confirma = await db.get(Operador, arqueo.confirmado_por_id) if supervisado else None
    return ArqueoResultado(
        supervisado=supervisado,
        confirmado_por_nombre=confirma.nombre_visible if confirma else None,
        observacion=arqueo.observacion,
        id=arqueo.id,
        guardia_id=arqueo.guardia_id,
        franja=guardia.franja,
        abierta_en=guardia.abierta_en,
        cerrada_en=guardia.cerrada_en,
        operador_id=arqueo.operador_id,
        operador_nombre=operador.nombre_visible if operador else "—",
        declarado_efectivo=arqueo.declarado_efectivo,
        declarado_posnet=arqueo.declarado_posnet,
        declarado_mercado_pago=arqueo.declarado_mercado_pago,
        total_declarado=arqueo.total_declarado,
        sistema_efectivo=arqueo.sistema_efectivo,
        sistema_posnet=arqueo.sistema_posnet,
        sistema_mercado_pago=arqueo.sistema_mercado_pago,
        total_sistema=arqueo.total_sistema,
        fondo_inicial=guardia.fondo_inicial,
        diferencia=arqueo.diferencia,
        categoria=arqueo.categoria,
        confirmado_en=arqueo.confirmado_en,
    )
