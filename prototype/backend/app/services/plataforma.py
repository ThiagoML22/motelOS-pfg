"""Plataforma: alta, suspensión y resumen de los establecimientos (multiinquilino, migración 006).

La plataforma no ve la operación de ningún motel: su sesión tiene el establecimiento 0, que no tiene filas. Para
dar de alta un establecimiento, la transacción cambia al establecimiento nuevo (que todavía está vacío), carga
su configuración inicial y vuelve a 0. El resumen solo trae cantidades y totales.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.inquilino import PLATAFORMA, SIN_FILTRO, fijar_establecimiento
from app.core.seguridad import hashear_clave
from app.models.configuracion import ConfiguracionCaja
from app.models.establecimiento import Establecimiento
from app.models.guardia import Guardia
from app.models.habitacion import Habitacion
from app.models.operador import ROL_ADMINISTRADOR, Operador
from app.models.pago import Pago
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.schemas.configuracion import EstablecimientoAlta, EstablecimientoResumen

CENTAVO = Decimal("0.01")


async def _con_funciones_de_la_base(db: AsyncSession) -> bool:
    """True si la base tiene las funciones de la migración 006. Las pruebas crean el esquema desde los modelos
    (SQLite, o PostgreSQL como dueño de las tablas) y no las tienen: ahí corre el mismo cálculo en Python."""
    if db.get_bind().dialect.name != "postgresql":
        return False
    consulta = text("SELECT to_regprocedure('crear_gerencia_inicial(text,text,text)') IS NOT NULL")
    return bool((await db.execute(consulta)).scalar())


async def alta_establecimiento(db: AsyncSession, datos: EstablecimientoAlta) -> Establecimiento:
    existente = (
        await db.execute(select(Establecimiento).where(Establecimiento.codigo == datos.codigo))
    ).scalars().first()
    if existente is not None or datos.codigo == "plataforma":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"El código {datos.codigo} ya está en uso.")

    establecimiento = Establecimiento(
        codigo=datos.codigo,
        nombre=datos.nombre.strip(),
        domicilio=(datos.domicilio or "").strip() or None,
        telefono=(datos.telefono or "").strip() or None,
    )
    db.add(establecimiento)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"El código {datos.codigo} ya está en uso."
        ) from None

    # Desde acá la transacción trabaja dentro del establecimiento nuevo: lo que se inserta pasa el control de
    # RLS (WITH CHECK) porque pertenece a él.
    await fijar_establecimiento(db, establecimiento.id)
    ahora = datetime.now(UTC)
    db.add_all(
        [Habitacion(numero=n, estado="Libre", activa=True) for n in range(1, datos.habitaciones + 1)]
        + [
            Tarifa(
                nombre=f"Vigente desde {ahora:%Y-%m-%d %H:%M:%S.%f}",
                tarifa_base=Decimal(str(datos.tarifa_base)).quantize(CENTAVO),
                estadia_base_min=datos.estadia_base_min,
                tolerancia_min=0,
                fraccion_min=datos.fraccion_min,
                tarifa_fraccion=Decimal(str(datos.tarifa_fraccion)).quantize(CENTAVO),
                vigente=True,
                vigente_desde=ahora,
            ),
            ConfiguracionCaja(
                establecimiento_id=establecimiento.id,
                fondo_cambio=Decimal(str(datos.fondo_cambio)).quantize(CENTAVO),
                actualizado_en=ahora,
            ),
        ]
    )
    await db.flush()
    clave = hashear_clave(datos.gerente_clave)
    if await _con_funciones_de_la_base(db):
        # motel_app no puede escribir el rol: la gerencia inicial la crea la función de la base, que solo
        # funciona sobre un establecimiento sin usuarios (migración 006).
        await db.execute(
            text("SELECT crear_gerencia_inicial(:usuario, :nombre, :clave)"),
            {"usuario": datos.gerente_usuario, "nombre": datos.gerente_nombre.strip(), "clave": clave},
        )
    else:
        db.add(
            Operador(
                usuario=datos.gerente_usuario,
                nombre_visible=datos.gerente_nombre.strip(),
                hash_clave=clave,
                rol=ROL_ADMINISTRADOR,
            )
        )
        await db.flush()  # antes de volver a la plataforma: el alta toma el establecimiento nuevo
    await fijar_establecimiento(db, PLATAFORMA)
    await db.commit()
    await db.refresh(establecimiento)
    return establecimiento


async def cambiar_estado(db: AsyncSession, establecimiento_id: int, activo: bool) -> Establecimiento:
    """Suspender corta en el acto las sesiones del establecimiento (deps.operador_actual); no borra nada."""
    establecimiento = await db.get(Establecimiento, establecimiento_id, with_for_update=True)
    if establecimiento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Establecimiento no encontrado")
    establecimiento.activo = activo
    await db.commit()
    await db.refresh(establecimiento)
    return establecimiento


async def resumen(db: AsyncSession) -> list[EstablecimientoResumen]:
    establecimientos = (await db.execute(select(Establecimiento).order_by(Establecimiento.id))).scalars().all()
    con_funciones = await _con_funciones_de_la_base(db)
    cantidades = await (_resumen_postgresql(db) if con_funciones else _resumen_sin_rls(db))
    return [
        EstablecimientoResumen.model_validate(e, from_attributes=True).model_copy(update=cantidades.get(e.id, {}))
        for e in establecimientos
    ]


async def _resumen_postgresql(db: AsyncSession) -> dict[int, dict]:
    # La función corre con los permisos del dueño de las tablas y rechaza cualquier sesión que no sea la
    # plataforma (migración 006).
    filas = (await db.execute(text("SELECT * FROM resumen_plataforma()"))).mappings().all()
    return {
        f["establecimiento_id"]: {
            "habitaciones": f["habitaciones"],
            "ocupadas": f["ocupadas"],
            "usuarios": f["usuarios"],
            "turnos_ultimas_24h": f["turnos_ultimas_24h"],
            "cobrado_ultimas_24h": float(f["cobrado_ultimas_24h"]),
            "guardia_abierta": f["guardia_abierta"],
        }
        for f in filas
    }


async def _resumen_sin_rls(db: AsyncSession) -> dict[int, dict]:
    """El mismo cálculo para las pruebas, cuya base no tiene RLS ni las funciones de la migración 006."""
    desde = datetime.now(UTC) - timedelta(hours=24)
    sin_filtro = {SIN_FILTRO: True}

    async def por_establecimiento(columna, *condiciones, agregado=None) -> dict[int, object]:
        consulta = (
            select(columna, agregado if agregado is not None else func.count())
            .where(*condiciones)
            .group_by(columna)
            .execution_options(**sin_filtro)
        )
        return dict((await db.execute(consulta)).all())

    habitaciones = await por_establecimiento(Habitacion.establecimiento_id, Habitacion.activa.is_(True))
    ocupadas = await por_establecimiento(Habitacion.establecimiento_id, Habitacion.estado == "Ocupada")
    usuarios = await por_establecimiento(
        Operador.establecimiento_id, Operador.activo.is_(True), Operador.establecimiento_id.is_not(None)
    )
    turnos = await por_establecimiento(Turno.establecimiento_id, Turno.hora_inicio >= desde)
    cobrado = await por_establecimiento(
        Pago.establecimiento_id, Pago.created_at >= desde, agregado=func.sum(Pago.monto)
    )
    guardias = await por_establecimiento(Guardia.establecimiento_id, Guardia.estado == "Abierta")
    ids = set(habitaciones) | set(usuarios)
    return {
        i: {
            "habitaciones": habitaciones.get(i, 0),
            "ocupadas": ocupadas.get(i, 0),
            "usuarios": usuarios.get(i, 0),
            "turnos_ultimas_24h": turnos.get(i, 0),
            "cobrado_ultimas_24h": float(cobrado.get(i) or 0),
            "guardia_abierta": bool(guardias.get(i)),
        }
        for i in ids
    }
