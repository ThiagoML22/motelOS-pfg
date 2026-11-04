"""Arreglos de las habitaciones y traslado de un turno a otra habitación (migración 016).

Un arreglo es una falla o un mantenimiento, con quién lo reparó y cuánto costó. Cada habitación tiene su historial. El
costo lo carga quien lo resuelve y es informativo: no mueve la caja; solo la gerencia lo ve.

El traslado mueve el turno entero: conserva su hora, su tarifa, su cuenta y el enlace del cliente (RN-DER-06). Si el
motivo es una falla, la habitación queda en mantenimiento con su arreglo abierto.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actividad import OPERACION
from app.models.evento_habitacion import ARREGLO, TRASLADO
from app.models.habitacion import Habitacion
from app.models.operacion import (
    ABIERTO,
    EN_CURSO,
    FALLA,
    MOTIVOS_TRASLADO,
    RESUELTO,
    RUBROS,
    SIN_RESOLVER,
    TIPOS_ARREGLO,
    Arreglo,
    TrasladoTurno,
)
from app.models.operador import ROL_ADMINISTRADOR, Operador
from app.models.turno import Turno
from app.services import rotacion
from app.services.actividad import pesos, registrar
from app.services.caja import guardia_del_operador
from app.services.liquidacion import con_zona

CENTAVO = Decimal("0.01")


def _fecha(valor: datetime | None) -> str | None:
    return con_zona(valor).isoformat() if valor else None


def como_dict(arreglo: Arreglo, numeros: dict, nombres: dict, con_costo: bool) -> dict:
    """El costo solo viaja para la gerencia."""
    return {
        "id": arreglo.id,
        "habitacion_id": arreglo.habitacion_id,
        "numero": numeros.get(arreglo.habitacion_id),
        "tipo": arreglo.tipo,
        "tipo_nombre": TIPOS_ARREGLO[arreglo.tipo],
        "rubro": arreglo.rubro,
        "rubro_nombre": RUBROS[arreglo.rubro],
        "descripcion": arreglo.descripcion,
        "estado": arreglo.estado,
        "abierto_por": nombres.get(arreglo.abierto_por_id, "—"),
        "abierto_en": _fecha(arreglo.abierto_en),
        "resuelto_por": nombres.get(arreglo.resuelto_por_id),
        "resuelto_en": _fecha(arreglo.resuelto_en),
        "reparado_por": arreglo.reparado_por,
        "trabajo": arreglo.trabajo,
        "costo": float(arreglo.costo) if con_costo and arreglo.costo is not None else None,
    }


async def _referencias(db: AsyncSession) -> tuple[dict, dict]:
    numeros = dict((await db.execute(select(Habitacion.id, Habitacion.numero))).all())
    nombres = dict((await db.execute(select(Operador.id, Operador.nombre_visible))).all())
    return numeros, nombres


async def listar(
    db: AsyncSession, operador: Operador, habitacion_id: int | None, solo_sin_resolver: bool
) -> list[dict]:
    consulta = select(Arreglo).order_by(Arreglo.abierto_en.desc(), Arreglo.id.desc())
    if habitacion_id is not None:
        consulta = consulta.where(Arreglo.habitacion_id == habitacion_id)
    if solo_sin_resolver:
        consulta = consulta.where(Arreglo.estado.in_(SIN_RESOLVER))
    numeros, nombres = await _referencias(db)
    con_costo = operador.rol == ROL_ADMINISTRADOR
    filas = (await db.execute(consulta.limit(200))).scalars()
    return [como_dict(a, numeros, nombres, con_costo) for a in filas]


async def cuantos_sin_resolver(db: AsyncSession) -> dict[int, int]:
    """Por habitación, para marcar la grilla."""
    filas = await db.execute(
        select(Arreglo.habitacion_id, func.count())
        .where(Arreglo.estado.in_(SIN_RESOLVER))
        .group_by(Arreglo.habitacion_id)
    )
    return dict(filas.all())


async def _habitacion(db: AsyncSession, habitacion_id: int, activa: bool = True) -> Habitacion:
    habitacion = (
        (await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id).with_for_update()))
        .scalars()
        .first()
    )
    if habitacion is None or (activa and not habitacion.activa):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitación no encontrada")
    return habitacion


def _nuevo(habitacion: Habitacion, operador: Operador, tipo: str, rubro: str, descripcion: str) -> Arreglo:
    return Arreglo(
        habitacion_id=habitacion.id,
        tipo=tipo,
        rubro=rubro,
        descripcion=descripcion.strip(),
        abierto_por_id=operador.id,
    )


async def reportar(
    db: AsyncSession,
    operador: Operador,
    habitacion_id: int,
    tipo: str,
    rubro: str,
    descripcion: str,
    fuera_de_servicio: bool,
) -> dict:
    habitacion = await _habitacion(db, habitacion_id)
    if fuera_de_servicio and habitacion.estado == rotacion.OCUPADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La habitación está ocupada: primero trasladá el turno para dejarla fuera de servicio.",
        )
    arreglo = _nuevo(habitacion, operador, tipo, rubro, descripcion)
    db.add(arreglo)
    if fuera_de_servicio:
        await rotacion.cambiar_estado(db, habitacion, rotacion.MANTENIMIENTO, operador, ARREGLO)
    await registrar(
        db,
        operador,
        OPERACION,
        "ARREGLO_ALTA",
        f"Habitación {habitacion.numero}: {TIPOS_ARREGLO[tipo].lower()}, {RUBROS[rubro].lower()}. "
        f"{arreglo.descripcion}",
    )
    await db.commit()
    numeros, nombres = await _referencias(db)
    return como_dict(arreglo, numeros, nombres, operador.rol == ROL_ADMINISTRADOR)


async def _arreglo(db: AsyncSession, arreglo_id: int) -> Arreglo:
    arreglo = (
        (await db.execute(select(Arreglo).where(Arreglo.id == arreglo_id).with_for_update())).scalars().first()
    )
    if arreglo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El arreglo no existe.")
    return arreglo


async def empezar(db: AsyncSession, operador: Operador, arreglo_id: int) -> dict:
    arreglo = await _arreglo(db, arreglo_id)
    if arreglo.estado != ABIERTO:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese arreglo ya empezó o está resuelto.")
    arreglo.estado = EN_CURSO
    await db.commit()
    numeros, nombres = await _referencias(db)
    return como_dict(arreglo, numeros, nombres, operador.rol == ROL_ADMINISTRADOR)


async def resolver(
    db: AsyncSession,
    operador: Operador,
    arreglo_id: int,
    reparado_por: str,
    trabajo: str | None,
    costo: float | None,
    habilitar: bool,
) -> dict:
    arreglo = await _arreglo(db, arreglo_id)
    if arreglo.estado == RESUELTO:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese arreglo ya está resuelto.")
    arreglo.estado = RESUELTO
    arreglo.resuelto_por_id = operador.id
    arreglo.resuelto_en = datetime.now(UTC)
    arreglo.reparado_por = reparado_por.strip()
    arreglo.trabajo = (trabajo or "").strip() or None
    arreglo.costo = None if costo is None else Decimal(str(costo)).quantize(CENTAVO)
    await db.flush()
    # Se puede cerrar un arreglo de una habitación dada de baja, pero esa no vuelve a ofrecerse.
    habitacion = await _habitacion(db, arreglo.habitacion_id, activa=False)
    if habilitar and habitacion.activa and habitacion.estado == rotacion.MANTENIMIENTO:
        otros = await db.execute(
            select(func.count())
            .select_from(Arreglo)
            .where(Arreglo.habitacion_id == habitacion.id, Arreglo.estado.in_(SIN_RESOLVER))
        )
        if otros.scalar_one() == 0:
            await rotacion.cambiar_estado(db, habitacion, rotacion.LIBRE, operador, ARREGLO)
    await registrar(
        db,
        operador,
        OPERACION,
        "ARREGLO_RESUELTO",
        f"Habitación {habitacion.numero}: {RUBROS[arreglo.rubro].lower()} resuelto por {arreglo.reparado_por}",
        valor_nuevo=pesos(arreglo.costo) if arreglo.costo is not None else None,
    )
    await db.commit()
    numeros, nombres = await _referencias(db)
    return como_dict(arreglo, numeros, nombres, operador.rol == ROL_ADMINISTRADOR)


async def cargar_costo(db: AsyncSession, operador: Operador, arreglo_id: int, costo: float | None) -> dict:
    """La factura suele llegar después: es lo único que cambia en un arreglo resuelto."""
    arreglo = await _arreglo(db, arreglo_id)
    if arreglo.estado != RESUELTO:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El costo se carga al resolver el arreglo.")
    anterior = arreglo.costo
    arreglo.costo = None if costo is None else Decimal(str(costo)).quantize(CENTAVO)
    await registrar(
        db,
        operador,
        OPERACION,
        "ARREGLO_COSTO",
        f"Costo del arreglo {arreglo.id}",
        valor_anterior=pesos(anterior) if anterior is not None else None,
        valor_nuevo=pesos(arreglo.costo) if arreglo.costo is not None else None,
    )
    await db.commit()
    numeros, nombres = await _referencias(db)
    return como_dict(arreglo, numeros, nombres, True)


async def trasladar(
    db: AsyncSession,
    operador: Operador,
    turno_id: uuid.UUID,
    destino_id: int,
    motivo: str,
    rubro: str | None,
    descripcion: str | None,
) -> dict:
    guardia = await guardia_del_operador(db, operador)
    turno = (await db.execute(select(Turno).where(Turno.id == turno_id).with_for_update())).scalars().first()
    if turno is None or turno.estado != "En Curso":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese turno no está en curso.")
    if turno.habitacion_id == destino_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El turno ya está en esa habitación.")
    if motivo == FALLA and not (rubro and (descripcion or "").strip()):
        raise HTTPException(status_code=422, detail="Contá qué falló para dejar el arreglo abierto.")
    # Siempre en el mismo orden: dos traslados cruzados no se bloquean entre sí.
    primera, segunda = sorted((turno.habitacion_id, destino_id))
    bloqueadas = {primera: await _habitacion(db, primera), segunda: await _habitacion(db, segunda)}
    origen, destino = bloqueadas[turno.habitacion_id], bloqueadas[destino_id]
    if destino.estado != rotacion.LIBRE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"La {destino.numero} no está disponible: {destino.estado}."
        )
    db.add(
        TrasladoTurno(
            turno_id=turno.id,
            desde_habitacion_id=origen.id,
            hacia_habitacion_id=destino.id,
            motivo=motivo,
            operador_id=operador.id,
            guardia_id=guardia.id,
        )
    )
    try:
        await db.flush()
        turno.habitacion_id = destino.id
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"La {destino.numero} ya tiene un turno en curso."
        ) from None
    await rotacion.cambiar_estado(db, destino, rotacion.OCUPADA, operador, TRASLADO, turno.id)
    queda = rotacion.MANTENIMIENTO if motivo == FALLA else rotacion.LIMPIEZA
    await rotacion.cambiar_estado(db, origen, queda, operador, TRASLADO, turno.id)
    if motivo == FALLA:
        db.add(_nuevo(origen, operador, FALLA, rubro, descripcion))
    await registrar(
        db,
        operador,
        OPERACION,
        "TURNO_TRASLADO",
        f"Turno de la {origen.numero} a la {destino.numero}: {MOTIVOS_TRASLADO[motivo].lower()}",
        valor_anterior=str(origen.numero),
        valor_nuevo=str(destino.numero),
    )
    await db.commit()
    return {"ok": True, "desde": origen.numero, "hacia": destino.numero, "origen_queda": queda}


async def tablero(db: AsyncSession, dias: int = 90) -> dict:
    """Para la gerencia: lo que falta resolver y cuánto se gastó, por habitación y por rubro."""
    numeros, nombres = await _referencias(db)
    todos = list((await db.execute(select(Arreglo).order_by(Arreglo.abierto_en.desc(), Arreglo.id.desc()))).scalars())
    sin_resolver = [a for a in todos if a.estado in SIN_RESOLVER]
    desde = datetime.now(UTC) - timedelta(days=dias)
    resueltos = [a for a in todos if a.estado == RESUELTO and con_zona(a.resuelto_en) >= desde]
    por_rubro: dict[str, list] = defaultdict(lambda: [0, Decimal(0)])
    por_habitacion: dict[int, list] = defaultdict(lambda: [0, Decimal(0)])
    for a in resueltos:
        for grupo, clave in ((por_rubro, a.rubro), (por_habitacion, a.habitacion_id)):
            grupo[clave][0] += 1
            grupo[clave][1] += a.costo or Decimal(0)
    return {
        "dias": dias,
        "sin_resolver": [como_dict(a, numeros, nombres, True) for a in sin_resolver],
        "resueltos": [como_dict(a, numeros, nombres, True) for a in resueltos[:50]],
        "costo_total": float(sum((a.costo or Decimal(0) for a in resueltos), Decimal(0))),
        "sin_costo": sum(1 for a in resueltos if a.costo is None),
        "en_mantenimiento": list(
            (await db.execute(select(Habitacion.id).where(Habitacion.estado == rotacion.MANTENIMIENTO))).scalars()
        ),
        "por_rubro": sorted(
            (
                {"rubro": r, "nombre": RUBROS[r], "cantidad": c, "costo": float(m)}
                for r, (c, m) in por_rubro.items()
            ),
            key=lambda f: -f["costo"],
        ),
        "por_habitacion": sorted(
            (
                {"habitacion_id": h, "numero": numeros.get(h), "cantidad": c, "costo": float(m)}
                for h, (c, m) in por_habitacion.items()
            ),
            key=lambda f: (-f["cantidad"], -f["costo"]),
        ),
    }


async def traslados(db: AsyncSession, limite: int = 50) -> list[dict]:
    numeros, nombres = await _referencias(db)
    filas = (
        await db.execute(select(TrasladoTurno).order_by(TrasladoTurno.creado_en.desc()).limit(limite))
    ).scalars()
    return [
        {
            "id": t.id,
            "creado_en": _fecha(t.creado_en),
            "desde": numeros.get(t.desde_habitacion_id),
            "hacia": numeros.get(t.hacia_habitacion_id),
            "motivo": MOTIVOS_TRASLADO[t.motivo],
            "operador": nombres.get(t.operador_id, "—"),
        }
        for t in filas
    ]
