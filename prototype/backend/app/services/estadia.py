import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.estadia_activa import EstadiaActiva
from app.models.turno import Turno

logger = logging.getLogger(__name__)


async def cargar_patentes(db: AsyncSession, turnos: list[Turno]) -> None:
    """Completa la patente de cada turno desde su estadía activa (atributo transitorio, no mapeado)."""
    if not turnos:
        return
    res = await db.execute(select(EstadiaActiva).where(EstadiaActiva.turno_id.in_([t.id for t in turnos])))
    patentes = {e.turno_id: e.identificador_vehicular for e in res.scalars().all()}
    for turno in turnos:
        turno.identificador_vehicular = patentes.get(turno.id)


async def depurar_patentes(
    db: AsyncSession, horas: int | None = None, ahora: datetime | None = None
) -> int:
    """RNF-08: elimina las patentes de los turnos cerrados hace más de `horas` horas.

    Solo toca la tabla de estadías activas; el turno cerrado, sus pagos y sus consumos no se modifican.
    Devuelve la cantidad de patentes eliminadas.
    """
    horas = settings.RETENCION_PATENTE_HORAS if horas is None else horas
    limite = (ahora or datetime.now(UTC)) - timedelta(hours=horas)
    vencidos = select(Turno.id).where(
        Turno.estado != "En Curso",
        func.coalesce(Turno.hora_fin, Turno.hora_inicio) <= limite,
    )
    res = await db.execute(delete(EstadiaActiva).where(EstadiaActiva.turno_id.in_(vencidos)))
    await db.commit()
    return res.rowcount or 0


async def ciclo_depuracion() -> None:
    """Tarea de fondo: depura las patentes vencidas cada DEPURACION_INTERVALO_MIN minutos."""
    while True:
        try:
            async with AsyncSessionLocal() as db:
                eliminadas = await depurar_patentes(db)
            if eliminadas:
                logger.info("RNF-08: %s patente(s) eliminada(s) por vencimiento del plazo de retención", eliminadas)
        except Exception:  # la depuración se reintenta en el ciclo siguiente
            logger.exception("RNF-08: falló la depuración de patentes")
        await asyncio.sleep(settings.DEPURACION_INTERVALO_MIN * 60)
