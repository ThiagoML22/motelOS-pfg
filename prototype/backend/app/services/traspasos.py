"""Traspaso de guardia: lo que recibe quien entra (migración 016).

Al abrir la guardia, quien entra ve los turnos en curso, los pedidos sin resolver, las habitaciones en limpieza o
mantenimiento, los arreglos abiertos, las novedades y la ropa que le dejaron, y lo confirma. Queda como foto: no cambia
aunque después cambie la ventanilla. No lleva importes ni patentes (RN-RES-03, RNF-03).

Quien cierra ve lo mismo salvo la ropa: el recuento de cierre es a ciegas. Por eso, con una guardia abierta, la ropa
solo la ve la gerencia.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.novedad import Novedad
from app.models.operacion import CIERRE, RUBROS, SIN_RESOLVER, Arreglo, RopaConteo, Traspaso
from app.models.operador import ROL_ADMINISTRADOR, Operador
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services import acceso_cliente, ropa
from app.services.caja import guardia_abierta
from app.services.liquidacion import con_zona

# Las novedades que se muestran al entrar: las de las últimas horas.
HORAS_DE_NOVEDADES = 12


async def _ultima_cerrada(db: AsyncSession) -> Guardia | None:
    consulta = (
        select(Guardia)
        .where(Guardia.estado == "Cerrada")
        .order_by(Guardia.cerrada_en.desc(), Guardia.id.desc())
        .limit(1)
    )
    return (await db.execute(consulta)).scalars().first()


async def foto_de_la_ventanilla(db: AsyncSession, ahora: datetime | None = None) -> dict:
    """Cómo está la ventanilla ahora, sin importes ni patentes."""
    ahora = ahora or datetime.now(UTC)
    habitaciones = list(
        (await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))).scalars()
    )
    numeros = {h.id: h.numero for h in habitaciones}
    filas = (
        await db.execute(
            select(Turno.habitacion_id, Turno.hora_inicio, Tarifa.estadia_base_min)
            .join(Tarifa, Tarifa.id == Turno.tarifa_id)
            .where(Turno.estado == "En Curso")
        )
    ).all()
    turnos = []
    for habitacion_id, inicio, base in filas:
        lleva = round((ahora - con_zona(inicio)).total_seconds() / 60)
        turnos.append(
            {"numero": numeros.get(habitacion_id), "lleva_min": lleva, "base_min": base, "excedido": lleva > base}
        )
    turnos.sort(key=lambda t: t["numero"] or 0)
    arreglos = (
        await db.execute(select(Arreglo).where(Arreglo.estado.in_(SIN_RESOLVER)).order_by(Arreglo.abierto_en))
    ).scalars()
    desde = ahora - timedelta(hours=HORAS_DE_NOVEDADES)
    novedades = (
        await db.execute(select(Novedad).where(Novedad.creado_en >= desde).order_by(Novedad.creado_en.desc()).limit(8))
    ).scalars()
    nombres = dict((await db.execute(select(Operador.id, Operador.nombre_visible))).all())
    pedidos = await acceso_cliente.pendientes_de_la_ventanilla(db)
    return {
        "turnos": turnos,
        "pedidos": [
            {"numero": p["numero"], "descripcion": p["descripcion"], "cantidad": p["cantidad"]} for p in pedidos
        ],
        "limpieza": [h.numero for h in habitaciones if h.estado == "En Limpieza"],
        "mantenimiento": [h.numero for h in habitaciones if h.estado == "Mantenimiento"],
        "arreglos": [
            {
                "numero": numeros.get(a.habitacion_id),
                "rubro": RUBROS[a.rubro],
                "descripcion": a.descripcion,
                "estado": a.estado,
            }
            for a in arreglos
        ],
        "novedades": [
            {
                "texto": n.texto,
                "importante": n.importante,
                "numero": numeros.get(n.habitacion_id),
                "autor": nombres.get(n.operador_id, "—"),
            }
            for n in novedades
        ],
    }


async def para_la_pantalla(db: AsyncSession, operador: Operador) -> dict:
    """Lo que ve quien entra, o quien cierra: a este último no se le muestra la ropa, porque cuenta a ciegas."""
    abierta = await guardia_abierta(db)
    foto = await foto_de_la_ventanilla(db)
    if abierta is not None and operador.rol != ROL_ADMINISTRADOR:
        return {
            **foto,
            "ropa": None,
            "ropa_por_estado": await ropa.cuenta_por_estado(db),
            "ropa_contada": await ropa.hizo_el_recuento(db, abierta.id),
            "exige_recuento": settings.EXIGIR_RECUENTO_ROPA,
            "saliente": None,
        }
    cerrada = await _ultima_cerrada(db)
    saliente = None
    if cerrada is not None:
        nombre = (await db.execute(select(Operador.nombre_visible).where(Operador.id == cerrada.operador_id))).scalar()
        saliente = {
            "operador": nombre,
            "franja": cerrada.franja,
            "cerrada_en": con_zona(cerrada.cerrada_en).isoformat(),
            "sin_conteo": not await ropa.hizo_el_recuento(db, cerrada.id),
        }
    return {
        **foto,
        "ropa": await ropa.para_recibir(db),
        "ropa_por_estado": await ropa.cuenta_por_estado(db),
        "ropa_contada": False,
        "exige_recuento": settings.EXIGIR_RECUENTO_ROPA,
        "saliente": saliente,
    }


async def registrar_recepcion(db: AsyncSession, guardia: Guardia, operador: Operador, recibido: list[dict]) -> None:
    """Quien entra confirma lo que recibe. Va en la misma transacción que abre la guardia."""
    cerrada = await _ultima_cerrada(db)
    # Primero la foto de lo que dejaron: el recuento nuevo todavía no cuenta como «lo que había».
    ropa_dejada = await ropa.para_recibir(db)
    foto = await foto_de_la_ventanilla(db)
    resultado = await ropa.guardar_conteo(db, guardia, operador, ropa.APERTURA, recibido)
    db.add(
        Traspaso(
            guardia_saliente_id=cerrada.id if cerrada else None,
            guardia_id=guardia.id,
            operador_id=operador.id,
            resumen={**foto, "ropa_dejada": ropa_dejada, "ropa_recibida": resultado},
        )
    )
    await db.flush()


async def historial(db: AsyncSession, limite: int = 40) -> list[dict]:
    """Para la gerencia: cada traspaso, con quién dejó y quién recibió."""
    filas = (await db.execute(select(Traspaso).order_by(Traspaso.creado_en.desc()).limit(limite))).scalars().all()
    guardias = {g.id: g for g in (await db.execute(select(Guardia))).scalars()}
    nombres = dict((await db.execute(select(Operador.id, Operador.nombre_visible))).all())
    contadas = set((await db.execute(select(RopaConteo.guardia_id).where(RopaConteo.momento == CIERRE))).scalars())
    resultado = []
    for t in filas:
        guardia = guardias.get(t.guardia_id)
        saliente = guardias.get(t.guardia_saliente_id)
        resultado.append(
            {
                "id": t.id,
                "creado_en": con_zona(t.creado_en).isoformat(),
                "franja": guardia.franja if guardia else None,
                "recibio": nombres.get(t.operador_id, "—"),
                "dejo": nombres.get(saliente.operador_id, "—") if saliente else None,
                "sin_conteo": saliente is not None and saliente.id not in contadas,
                "resumen": t.resumen,
            }
        )
    return resultado
