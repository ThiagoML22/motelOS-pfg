"""Recuento de toallas y sábanas: cuánta ropa hay en el motel en cada cambio de guardia (migración 016).

Se cuenta todo: limpias, sucias y puestas en habitaciones. Quien cierra cuenta a ciegas, como en la caja, y quien entra
ve lo que le dejaron y lo confirma o corrige con su propia cuenta. Lo que entra o sale del motel es un movimiento
(lavandería, compra, baja): lo que debería haber es el recuento anterior más esos movimientos, y una diferencia sin
explicar le llega a la gerencia con los nombres de quienes contaron.
"""

from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actividad import OPERACION
from app.models.guardia import Guardia
from app.models.operacion import APERTURA, CIERRE, MOVIMIENTOS_ROPA, PRENDAS, RopaConteo, RopaMovimiento
from app.models.operador import Operador
from app.services.actividad import registrar
from app.services.caja import guardia_del_operador, nombre_de
from app.services.liquidacion import con_zona


def _comprobar_prendas(conteos: list[dict]) -> None:
    if sorted(c["prenda"] for c in conteos) != sorted(PRENDAS):
        raise HTTPException(status_code=422, detail="El recuento lleva una cuenta por cada prenda.")


async def _ultimos(db: AsyncSession) -> dict[str, RopaConteo]:
    """El último recuento de cada prenda."""
    filas = (await db.execute(select(RopaConteo).order_by(RopaConteo.creado_en, RopaConteo.id))).scalars()
    return {c.prenda: c for c in filas}


async def _movido_desde(db: AsyncSession, prenda: str, desde: datetime) -> int:
    """Lo que entró menos lo que salió del motel después de un recuento."""
    filas = (
        await db.execute(
            select(RopaMovimiento).where(RopaMovimiento.prenda == prenda, RopaMovimiento.creado_en > desde)
        )
    ).scalars()
    return sum(MOVIMIENTOS_ROPA[m.tipo][1] * m.cantidad for m in filas)


async def _esperado(db: AsyncSession, anterior: RopaConteo | None) -> int | None:
    if anterior is None:
        return None
    return anterior.total + await _movido_desde(db, anterior.prenda, anterior.creado_en)


async def guardar_conteo(
    db: AsyncSession, guardia: Guardia, operador: Operador, momento: str, conteos: list[dict]
) -> list[dict]:
    """Guarda el recuento y compara con lo que debería haber; una diferencia queda para que la vea la gerencia. No hace
    commit: va en la transacción que abre la guardia o en la del recuento de cierre."""
    _comprobar_prendas(conteos)
    anteriores = await _ultimos(db)
    resultado = []
    for conteo in conteos:
        prenda = conteo["prenda"]
        anterior = anteriores.get(prenda)
        esperado = await _esperado(db, anterior)
        fila = RopaConteo(
            guardia_id=guardia.id,
            operador_id=operador.id,
            momento=momento,
            prenda=prenda,
            limpias=conteo["limpias"],
            sucias=conteo["sucias"],
            en_habitaciones=conteo["en_habitaciones"],
        )
        db.add(fila)
        diferencia = None if esperado is None else fila.total - esperado
        resultado.append(
            {
                "prenda": prenda,
                "etiqueta": PRENDAS[prenda],
                "total": fila.total,
                "esperado": esperado,
                "diferencia": diferencia,
            }
        )
        if diferencia:
            quien = await nombre_de(db, anterior.operador_id)
            contaron = (
                f"en la guardia de {quien}"
                if anterior.operador_id == operador.id
                else f"entre el recuento de {quien} y el de {operador.nombre_visible}"
            )
            await registrar(
                db,
                operador,
                OPERACION,
                "ROPA_DIFERENCIA",
                f"{PRENDAS[prenda]}: {'faltan' if diferencia < 0 else 'sobran'} {abs(diferencia)} {contaron}",
                valor_anterior=str(esperado),
                valor_nuevo=str(fila.total),
            )
    await db.flush()
    return resultado


async def recuento_de_cierre(db: AsyncSession, operador: Operador, conteos: list[dict]) -> list[dict]:
    guardia = await guardia_del_operador(db, operador)
    if await hizo_el_recuento(db, guardia.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El recuento de esta guardia ya está hecho.")
    resultado = await guardar_conteo(db, guardia, operador, CIERRE, conteos)
    await db.commit()
    return resultado


async def hizo_el_recuento(db: AsyncSession, guardia_id: int) -> bool:
    consulta = select(RopaConteo.id).where(RopaConteo.guardia_id == guardia_id, RopaConteo.momento == CIERRE).limit(1)
    return (await db.execute(consulta)).first() is not None


async def registrar_movimiento(db: AsyncSession, operador: Operador, prenda: str, tipo: str, cantidad: int) -> dict:
    guardia = await guardia_del_operador(db, operador)
    db.add(RopaMovimiento(guardia_id=guardia.id, operador_id=operador.id, prenda=prenda, tipo=tipo, cantidad=cantidad))
    nombre = MOVIMIENTOS_ROPA[tipo][0]
    descripcion = f"{PRENDAS[prenda]}: {nombre.lower()}, {cantidad}"
    await registrar(db, operador, OPERACION, "ROPA_MOVIMIENTO", descripcion, cantidad=cantidad)
    await db.commit()
    return {"ok": True}


async def para_recibir(db: AsyncSession) -> list[dict]:
    """Lo que dejó el último recuento, para quien entra. Con lo que salió o entró después ya descontado."""
    ultimos = await _ultimos(db)
    filas = []
    for prenda, etiqueta in PRENDAS.items():
        conteo = ultimos.get(prenda)
        if conteo is None:
            continue
        filas.append(
            {
                "prenda": prenda,
                "etiqueta": etiqueta,
                "limpias": conteo.limpias,
                "sucias": conteo.sucias,
                "en_habitaciones": conteo.en_habitaciones,
                "total": conteo.total,
                "esperado": await _esperado(db, conteo),
                "contado_por": await nombre_de(db, conteo.operador_id),
            }
        )
    return filas


async def historial(db: AsyncSession, limite: int = 60) -> dict:
    """Para la gerencia: cada recuento con lo que debería haber y su diferencia, del más nuevo al más viejo."""
    conteos = list((await db.execute(select(RopaConteo).order_by(RopaConteo.creado_en, RopaConteo.id))).scalars())
    movimientos = list(
        (await db.execute(select(RopaMovimiento).order_by(RopaMovimiento.creado_en, RopaMovimiento.id))).scalars()
    )
    nombres = dict((await db.execute(select(Operador.id, Operador.nombre_visible))).all())
    por_prenda: dict[str, list] = defaultdict(list)
    for conteo in conteos:
        por_prenda[conteo.prenda].append(conteo)

    filas = []
    resumen = []
    for prenda, etiqueta in PRENDAS.items():
        movidos = [m for m in movimientos if m.prenda == prenda]
        anterior = None
        indice = 0
        faltantes = 0
        for conteo in por_prenda[prenda]:
            neto = 0
            while indice < len(movidos) and con_zona(movidos[indice].creado_en) <= con_zona(conteo.creado_en):
                movimiento = movidos[indice]
                neto += MOVIMIENTOS_ROPA[movimiento.tipo][1] * movimiento.cantidad
                indice += 1
            esperado = None if anterior is None else anterior.total + neto
            diferencia = None if esperado is None else conteo.total - esperado
            if diferencia and diferencia < 0:
                faltantes -= diferencia
            filas.append(
                {
                    "id": conteo.id,
                    "prenda": prenda,
                    "etiqueta": etiqueta,
                    "momento": conteo.momento,
                    "creado_en": con_zona(conteo.creado_en).isoformat(),
                    "operador": nombres.get(conteo.operador_id, "—"),
                    "limpias": conteo.limpias,
                    "sucias": conteo.sucias,
                    "en_habitaciones": conteo.en_habitaciones,
                    "total": conteo.total,
                    "esperado": esperado,
                    "diferencia": diferencia,
                    "anterior_por": nombres.get(anterior.operador_id, "—") if anterior else None,
                }
            )
            anterior = conteo
        ultimo = por_prenda[prenda][-1] if por_prenda[prenda] else None
        en_lavanderia = sum(
            m.cantidad * (1 if m.tipo == "LAVANDERIA_SALE" else -1)
            for m in movidos
            if m.tipo in ("LAVANDERIA_SALE", "LAVANDERIA_VUELVE")
        )
        resumen.append(
            {
                "prenda": prenda,
                "etiqueta": etiqueta,
                "total": ultimo.total if ultimo else None,
                "limpias": ultimo.limpias if ultimo else None,
                "sucias": ultimo.sucias if ultimo else None,
                "en_habitaciones": ultimo.en_habitaciones if ultimo else None,
                "en_lavanderia": max(en_lavanderia, 0),
                "faltantes": faltantes,
            }
        )
    filas.sort(key=lambda f: (f["creado_en"], f["id"]), reverse=True)
    recientes = sorted(movimientos, key=lambda m: (con_zona(m.creado_en), m.id), reverse=True)[:30]
    return {
        "resumen": resumen,
        "conteos": filas[:limite],
        "diferencias": [f for f in filas if f["diferencia"]][:30],
        "movimientos": [
            {
                "id": m.id,
                "prenda": PRENDAS[m.prenda],
                "tipo": MOVIMIENTOS_ROPA[m.tipo][0],
                "signo": MOVIMIENTOS_ROPA[m.tipo][1],
                "cantidad": m.cantidad,
                "operador": nombres.get(m.operador_id, "—"),
                "creado_en": con_zona(m.creado_en).isoformat(),
            }
            for m in recientes
        ],
    }


__all__ = [
    "APERTURA",
    "CIERRE",
    "guardar_conteo",
    "hizo_el_recuento",
    "historial",
    "para_recibir",
    "recuento_de_cierre",
    "registrar_movimiento",
]
