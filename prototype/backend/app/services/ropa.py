"""Recuento de toallas y sábanas: cuánta ropa hay en el motel en cada cambio de guardia (migraciones 016 y 017).

Se cuenta toda la ropa del motel. Cada establecimiento elige cómo: separada en limpias, sucias y en uso (puestas en las
habitaciones), o todo junto. Quien cierra cuenta a ciegas, como en la caja, y quien entra ve lo que le dejaron y lo
confirma o corrige con su propia cuenta. Lo que entra o sale del motel es un movimiento (lavandería, compra, baja): lo
que debería haber es el recuento anterior más esos movimientos, y una diferencia sin explicar le llega a la gerencia con
los nombres de quienes contaron. Se compara siempre el total: cambiar la forma de contar no corta el historial.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.inquilino import CLAVE
from app.models.actividad import OPERACION
from app.models.establecimiento import Establecimiento
from app.models.guardia import Guardia
from app.models.operacion import APERTURA, CIERRE, MOVIMIENTOS_ROPA, PRENDAS, RopaConteo, RopaMovimiento
from app.models.operador import Operador
from app.services.actividad import registrar
from app.services.caja import guardia_abierta, guardia_del_operador, nombre_de
from app.services.liquidacion import con_zona

PARTES = ("limpias", "sucias", "en_habitaciones")
# Las diferencias que se resumen por persona: las del último mes.
DIAS_DE_DIFERENCIAS = 30


async def cuenta_por_estado(db: AsyncSession) -> bool:
    """Cómo cuenta este establecimiento: separado en limpias, sucias y en uso (True) o todo junto (False)."""
    establecimiento = await db.get(Establecimiento, db.info.get(CLAVE))
    return True if establecimiento is None else bool(establecimiento.ropa_por_estado)


async def cambiar_forma(db: AsyncSession, operador: Operador, por_estado: bool) -> dict:
    """La gerencia elige cómo se cuenta. Rige desde el próximo recuento: lo ya contado no cambia."""
    establecimiento = await db.get(Establecimiento, db.info.get(CLAVE))
    if establecimiento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Establecimiento no encontrado")
    if bool(establecimiento.ropa_por_estado) != por_estado:
        formas = {True: "por separado (limpias, sucias y en uso)", False: "todo junto"}
        establecimiento.ropa_por_estado = por_estado
        await registrar(
            db,
            operador,
            OPERACION,
            "ROPA_FORMA",
            f"La ropa pasa a contarse {formas[por_estado]}",
            valor_anterior=formas[not por_estado][:80],
            valor_nuevo=formas[por_estado][:80],
        )
        await db.commit()
    return {"por_estado": por_estado}


def _comprobar_prendas(conteos: list[dict]) -> None:
    if sorted(c["prenda"] for c in conteos) != sorted(PRENDAS):
        raise HTTPException(status_code=422, detail="El recuento lleva una cuenta por cada prenda.")


def _en_la_forma(conteo: dict, por_estado: bool) -> dict:
    """El recuento como lo guarda este establecimiento: con sus partes, o solo el total."""
    partes = [conteo.get(parte) for parte in PARTES]
    completas = all(parte is not None for parte in partes)
    if por_estado:
        if not completas:
            raise HTTPException(
                status_code=422, detail="En este motel la ropa se cuenta por separado: limpias, sucias y en uso."
            )
        return {**dict(zip(PARTES, partes, strict=True)), "total": sum(partes)}
    total = conteo.get("total")
    if total is None:
        if not completas:
            raise HTTPException(status_code=422, detail="Falta la cantidad de cada prenda.")
        total = sum(partes)
    return {**dict.fromkeys(PARTES), "total": total}


def _cuantas(diferencia: int) -> str:
    """«faltan 2», «falta 1», «sobran 3»."""
    verbo = ("falta" if diferencia < 0 else "sobra") + ("" if abs(diferencia) == 1 else "n")
    return f"{verbo} {abs(diferencia)}"


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
    por_estado = await cuenta_por_estado(db)
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
            **_en_la_forma(conteo, por_estado),
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
                f"{PRENDAS[prenda]}: {_cuantas(diferencia)} {contaron}",
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


def _movimiento(movimiento: RopaMovimiento, nombres: dict[int, str]) -> dict:
    return {
        "id": movimiento.id,
        "prenda": PRENDAS[movimiento.prenda],
        "tipo": MOVIMIENTOS_ROPA[movimiento.tipo][0],
        "signo": MOVIMIENTOS_ROPA[movimiento.tipo][1],
        "cantidad": movimiento.cantidad,
        "operador": nombres.get(movimiento.operador_id, "—"),
        "creado_en": con_zona(movimiento.creado_en).isoformat(),
    }


async def registrar_movimiento(db: AsyncSession, operador: Operador, prenda: str, tipo: str, cantidad: int) -> dict:
    guardia = await guardia_del_operador(db, operador)
    db.add(RopaMovimiento(guardia_id=guardia.id, operador_id=operador.id, prenda=prenda, tipo=tipo, cantidad=cantidad))
    nombre = MOVIMIENTOS_ROPA[tipo][0]
    descripcion = f"{PRENDAS[prenda]}: {nombre.lower()}, {cantidad}"
    await registrar(db, operador, OPERACION, "ROPA_MOVIMIENTO", descripcion, cantidad=cantidad)
    await db.commit()
    return {"ok": True}


async def movimientos_de_la_guardia(db: AsyncSession, operador: Operador) -> list[dict]:
    """Lo que el conserje ya anotó en su guardia abierta, del más nuevo al más viejo. Son sus propias anotaciones: no
    dicen cuánta ropa hay."""
    guardia = await guardia_abierta(db)
    if guardia is None or guardia.operador_id != operador.id:
        return []
    filas = (
        await db.execute(
            select(RopaMovimiento)
            .where(RopaMovimiento.guardia_id == guardia.id)
            .order_by(RopaMovimiento.creado_en.desc(), RopaMovimiento.id.desc())
        )
    ).scalars()
    return [_movimiento(m, {operador.id: operador.nombre_visible}) for m in filas]


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


def _por_persona(filas: list[dict], desde: datetime) -> dict:
    """Los faltantes del último mes, según dónde aparecieron.

    Entre la apertura y el cierre de la misma persona, faltó durante su guardia. Entre el cierre de una y la apertura de
    otra, faltó en el cambio de guardia: no se sabe de cuál de las dos.
    """
    en_guardia: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    en_cambio: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for fila in filas:
        if not fila["diferencia"] or fila["diferencia"] > 0 or datetime.fromisoformat(fila["creado_en"]) < desde:
            continue
        if fila["anterior_id"] == fila["operador_id"]:
            cuenta = en_guardia[fila["operador"]]
        else:
            cuenta = en_cambio[(fila["anterior_por"], fila["operador"])]
        cuenta[0] -= fila["diferencia"]
        cuenta[1] += 1
    return {
        "dias": DIAS_DE_DIFERENCIAS,
        "en_guardia": sorted(
            ({"operador": nombre, "unidades": u, "recuentos": r} for nombre, (u, r) in en_guardia.items()),
            key=lambda f: -f["unidades"],
        ),
        "en_cambio": sorted(
            (
                {"dejo": dejo, "recibio": recibio, "unidades": u, "recuentos": r}
                for (dejo, recibio), (u, r) in en_cambio.items()
            ),
            key=lambda f: -f["unidades"],
        ),
    }


def _agrupados(filas: list[dict], limite: int) -> list[dict]:
    """Un renglón por recuento (una guardia, al abrir o al cerrar), con sus dos prendas."""
    grupos: dict[tuple[int, str], dict] = {}
    for fila in filas:
        clave = (fila["guardia_id"], fila["momento"])
        grupo = grupos.setdefault(
            clave,
            {
                "clave": f"{fila['guardia_id']}-{fila['momento']}",
                "creado_en": fila["creado_en"],
                "momento": fila["momento"],
                "operador": fila["operador"],
                "prendas": [],
            },
        )
        grupo["prendas"].append(
            {k: fila[k] for k in ("prenda", "etiqueta", *PARTES, "total", "esperado", "diferencia")}
        )
    orden = list(PRENDAS)
    for grupo in grupos.values():
        grupo["prendas"].sort(key=lambda p: orden.index(p["prenda"]))
    return list(grupos.values())[:limite]


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
    desde = datetime.now(UTC) - timedelta(days=DIAS_DE_DIFERENCIAS)

    filas = []
    resumen = []
    for prenda, etiqueta in PRENDAS.items():
        movidos = [m for m in movimientos if m.prenda == prenda]
        anterior = None
        indice = 0
        faltantes = 0
        faltantes_del_mes = 0
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
                if con_zona(conteo.creado_en) >= desde:
                    faltantes_del_mes -= diferencia
            filas.append(
                {
                    "id": conteo.id,
                    "guardia_id": conteo.guardia_id,
                    "prenda": prenda,
                    "etiqueta": etiqueta,
                    "momento": conteo.momento,
                    "creado_en": con_zona(conteo.creado_en).isoformat(),
                    "operador": nombres.get(conteo.operador_id, "—"),
                    "operador_id": conteo.operador_id,
                    "limpias": conteo.limpias,
                    "sucias": conteo.sucias,
                    "en_habitaciones": conteo.en_habitaciones,
                    "total": conteo.total,
                    "esperado": esperado,
                    "diferencia": diferencia,
                    "anterior_por": nombres.get(anterior.operador_id, "—") if anterior else None,
                    "anterior_id": anterior.operador_id if anterior else None,
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
                "contado_en": con_zona(ultimo.creado_en).isoformat() if ultimo else None,
                "contado_por": nombres.get(ultimo.operador_id, "—") if ultimo else None,
                "en_lavanderia": max(en_lavanderia, 0),
                "faltantes": faltantes,
                "faltantes_del_mes": faltantes_del_mes,
            }
        )
    filas.sort(key=lambda f: (f["creado_en"], f["id"]), reverse=True)
    recientes = sorted(movimientos, key=lambda m: (con_zona(m.creado_en), m.id), reverse=True)[:30]
    return {
        "por_estado": await cuenta_por_estado(db),
        "resumen": resumen,
        "conteos": filas[:limite],
        "recuentos": _agrupados(filas, 40),
        "diferencias": [f for f in filas if f["diferencia"]][:30],
        "por_persona": _por_persona(filas, desde),
        "movimientos": [_movimiento(m, nombres) for m in recientes],
    }


__all__ = [
    "APERTURA",
    "CIERRE",
    "cambiar_forma",
    "cuenta_por_estado",
    "guardar_conteo",
    "hizo_el_recuento",
    "historial",
    "movimientos_de_la_guardia",
    "para_recibir",
    "recuento_de_cierre",
    "registrar_movimiento",
]
