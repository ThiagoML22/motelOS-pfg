"""Categorías de habitación con su tarifa (migración 008).

Cada establecimiento define sus categorías (Simple, Especial, VIP...). Una habitación pertenece a una categoría y el
turno que se abre en ella toma la tarifa vigente de esa categoría. Cambiar la tarifa o la categoría de una
habitación rige para los turnos que se abran después: el turno en curso conserva la suya (RN-DER-06).
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actividad import HABITACION
from app.models.categoria import CategoriaHabitacion
from app.models.franja_tarifa import FranjaTarifa
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.schemas.configuracion import (
    CategoriaAlta,
    CategoriaCambio,
    CategoriaResponse,
    FranjaResponse,
    TarifaAhora,
    TarifaResponse,
)
from app.services import franjas as tarifas_especiales
from app.services.actividad import registrar
from app.services.configuracion import nueva_tarifa_de


def franja_respuesta(franja: FranjaTarifa, tarifa: Tarifa | None) -> FranjaResponse:
    return FranjaResponse(
        id=franja.id,
        categoria_id=franja.categoria_id,
        nombre=franja.nombre,
        dias=franja.dias,
        desde=franja.desde,
        hasta=franja.hasta,
        regla=tarifas_especiales.regla_texto(franja.dias, franja.desde, franja.hasta),
        tarifa=TarifaResponse.model_validate(tarifa) if tarifa else None,
    )


def _tarifa_ahora(vigente: tarifas_especiales.Vigente | None) -> TarifaAhora | None:
    if vigente is None:
        return None
    datos = TarifaResponse.model_validate(vigente.tarifa).model_dump()
    return TarifaAhora(
        **{**datos, "franja": vigente.franja.nombre if vigente.franja else None},
        cambia_en=vigente.cambia_en,
        cambia_a=vigente.siguiente_franja.nombre if vigente.siguiente_franja else None,
        cambia_a_precio=float(vigente.siguiente.tarifa_base) if vigente.siguiente else None,
    )


async def listar(db: AsyncSession, solo_activas: bool) -> list[CategoriaResponse]:
    consulta = select(CategoriaHabitacion).order_by(CategoriaHabitacion.orden, CategoriaHabitacion.id)
    if solo_activas:
        consulta = consulta.where(CategoriaHabitacion.activa.is_(True))
    categorias = (await db.execute(consulta)).scalars().all()
    cantidades = dict(
        (
            await db.execute(
                select(Habitacion.categoria_id, func.count())
                .where(Habitacion.activa.is_(True))
                .group_by(Habitacion.categoria_id)
            )
        ).all()
    )
    tarifas = await tarifas_especiales.tarifario(db)
    ahora = datetime.now(UTC)
    return [
        CategoriaResponse(
            id=c.id,
            nombre=c.nombre,
            descripcion=c.descripcion,
            color=c.color,
            orden=c.orden,
            activa=c.activa,
            habitaciones=cantidades.get(c.id, 0),
            tarifa=TarifaResponse.model_validate(tarifas.generales[c.id]) if c.id in tarifas.generales else None,
            tarifa_ahora=_tarifa_ahora(tarifas.en(c.id, ahora)),
            franjas=[franja_respuesta(f, tarifas.de_franja.get(f.id)) for f in tarifas.franjas.get(c.id, [])],
        )
        for c in categorias
    ]


async def _nombre_libre(db: AsyncSession, nombre: str, salvo_id: int | None = None) -> None:
    consulta = select(CategoriaHabitacion).where(func.lower(CategoriaHabitacion.nombre) == nombre.lower())
    existente = (await db.execute(consulta)).scalars().first()
    if existente is not None and existente.id != salvo_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe la categoría {nombre}.")


async def crear(db: AsyncSession, datos: CategoriaAlta, operador: Operador) -> CategoriaHabitacion:
    nombre = datos.nombre.strip()
    await _nombre_libre(db, nombre)
    categoria = CategoriaHabitacion(
        nombre=nombre,
        descripcion=(datos.descripcion or "").strip() or None,
        color=datos.color,
        orden=datos.orden,
        activa=True,
    )
    db.add(categoria)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe la categoría {nombre}.") from None
    db.add(nueva_tarifa_de(categoria, datos.tarifa, operador.id))
    await registrar(db, operador, HABITACION, "CATEGORIA_ALTA", f"Alta de la categoría {nombre}")
    await db.commit()
    await db.refresh(categoria)
    return categoria


async def cambiar(
    db: AsyncSession, categoria_id: int, datos: CategoriaCambio, operador: Operador
) -> CategoriaHabitacion:
    categoria = await db.get(CategoriaHabitacion, categoria_id, with_for_update=True)
    if categoria is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Categoría de habitación no encontrada")
    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"] is not None:
        cambios["nombre"] = cambios["nombre"].strip()
        await _nombre_libre(db, cambios["nombre"], salvo_id=categoria.id)
    if cambios.get("activa") is False and categoria.activa:
        # La base aplica la misma regla (trigger_categoria_baja, migración 008).
        asignadas = (
            await db.execute(
                select(func.count())
                .select_from(Habitacion)
                .where(Habitacion.categoria_id == categoria.id, Habitacion.activa.is_(True))
            )
        ).scalar_one()
        if asignadas:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{categoria.nombre} tiene {asignadas} habitación(es) activa(s): "
                    "reasígnelas antes de darla de baja."
                ),
            )
    for campo, valor in cambios.items():
        if valor is None and campo != "descripcion":
            continue
        anterior = getattr(categoria, campo)
        if anterior == valor:
            continue
        setattr(categoria, campo, valor)
        await registrar(
            db,
            operador,
            HABITACION,
            "CATEGORIA_CAMBIO",
            f"Categoría {categoria.nombre}: cambio de {campo}",
            valor_anterior=None if anterior is None else str(anterior),
            valor_nuevo=None if valor is None else str(valor),
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una categoría con ese nombre."
        ) from None
    await db.refresh(categoria)
    return categoria
