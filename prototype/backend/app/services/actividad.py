"""Registro de actividad para la gerencia (migración 007).

Cada cambio de inventario o de configuración agrega una entrada en la misma transacción que el cambio: si el
cambio se guarda, la entrada también, y si falla, no queda ninguna de las dos. Lo que hace un conserje (alta de
un artículo, reposición de stock) queda «por revisar» hasta que la gerencia lo marca como visto.
"""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actividad import RegistroActividad
from app.models.guardia import Guardia
from app.models.operador import ROL_OPERADOR, Operador


def pesos(monto) -> str:
    """$ 12.345,50 (formato argentino; sin decimales si son cero)."""
    valor = Decimal(str(monto)).quantize(Decimal("0.01"))
    entero, _, decimales = f"{valor:,.2f}".partition(".")
    texto = entero.replace(",", ".")
    return f"$ {texto}" if decimales == "00" else f"$ {texto},{decimales}"


async def registrar(
    db: AsyncSession,
    operador: Operador,
    categoria: str,
    accion: str,
    descripcion: str,
    *,
    articulo_id: int | None = None,
    cantidad: int | None = None,
    valor_anterior: str | None = None,
    valor_nuevo: str | None = None,
) -> RegistroActividad:
    """Agrega la entrada a la sesión; la guarda el commit del cambio que registra."""
    guardia = (
        await db.execute(select(Guardia).where(Guardia.estado == "Abierta", Guardia.operador_id == operador.id))
    ).scalars().first()
    entrada = RegistroActividad(
        operador_id=operador.id,
        guardia_id=guardia.id if guardia else None,
        categoria=categoria,
        accion=accion,
        descripcion=descripcion[:300],
        articulo_id=articulo_id,
        cantidad=cantidad,
        valor_anterior=valor_anterior[:80] if valor_anterior else None,
        valor_nuevo=valor_nuevo[:80] if valor_nuevo else None,
        requiere_revision=operador.rol == ROL_OPERADOR,
    )
    db.add(entrada)
    return entrada


async def listar(
    db: AsyncSession, categoria: str | None, solo_pendientes: bool, limite: int = 300
) -> list[tuple[RegistroActividad, str, str | None]]:
    """Entradas con el nombre de quien hizo el cambio y de quien lo revisó, de la más nueva a la más vieja."""
    consulta = select(RegistroActividad).order_by(RegistroActividad.creado_en.desc(), RegistroActividad.id.desc())
    if categoria:
        consulta = consulta.where(RegistroActividad.categoria == categoria)
    if solo_pendientes:
        consulta = consulta.where(
            RegistroActividad.requiere_revision.is_(True), RegistroActividad.revisado_en.is_(None)
        )
    entradas = list((await db.execute(consulta.limit(limite))).scalars().all())
    ids = {e.operador_id for e in entradas} | {e.revisado_por_id for e in entradas if e.revisado_por_id}
    nombres = dict((await db.execute(select(Operador.id, Operador.nombre_visible).where(Operador.id.in_(ids)))).all())
    return [(e, nombres.get(e.operador_id, "—"), nombres.get(e.revisado_por_id)) for e in entradas]


async def pendientes(db: AsyncSession) -> int:
    consulta = select(func.count()).select_from(RegistroActividad).where(
        RegistroActividad.requiere_revision.is_(True), RegistroActividad.revisado_en.is_(None)
    )
    return (await db.execute(consulta)).scalar_one()


async def marcar_revisadas(db: AsyncSession, gerencia: Operador, ids: list[int] | None) -> int:
    """Marca como vistas las entradas indicadas (o todas las pendientes). Devuelve cuántas marcó."""
    consulta = select(RegistroActividad).where(
        RegistroActividad.requiere_revision.is_(True), RegistroActividad.revisado_en.is_(None)
    )
    if ids is not None:
        if not ids:
            raise HTTPException(status_code=422, detail="No indicó entradas.")
        consulta = consulta.where(RegistroActividad.id.in_(ids))
    entradas = (await db.execute(consulta.with_for_update())).scalars().all()
    ahora = datetime.now(UTC)
    for entrada in entradas:
        entrada.revisado_por_id = gerencia.id
        entrada.revisado_en = ahora
    await db.commit()
    return len(entradas)
