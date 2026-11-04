"""Tarifas especiales: una categoría puede cobrar distinto según el día y la hora (migración 014).

Una franja dice cuándo rige («viernes y sábado de 20 a 6») y su precio es una tarifa como cualquier otra, que tampoco
se edita: se reemplaza. Al abrirse, el turno toma la tarifa de la franja en la que cae su llegada, o la general de la
categoría si no cae en ninguna, y la conserva hasta el cobro (RN-DER-06): la liquidación no sabe que existen las
franjas.

Los días de una franja son los de comienzo: la noche del viernes sigue rigiendo el sábado a las 2. Toda la cuenta se
hace sobre los minutos de la semana (lunes 00:00 = 0), igual que franja_en_la_semana() en la base.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.actividad import TARIFA
from app.models.franja_tarifa import FranjaTarifa
from app.models.operador import Operador
from app.models.tarifa import Tarifa
from app.schemas.configuracion import FranjaAlta, FranjaCambio
from app.services.actividad import pesos, registrar
from app.services.configuracion import categoria_activa, nueva_tarifa_de

MINUTOS_DIA = 1440
MINUTOS_SEMANA = 7 * MINUTOS_DIA
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
DIAS_SIN_ACENTO = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
PARTES_DEL_DIA = {"madrugada": 3, "manana": 10, "mediodia": 13, "siesta": 14, "tarde": 17, "noche": 22}
TODOS_LOS_DIAS = 127


def mascara(*dias: int) -> int:
    """La máscara de unos días (lunes = 0)."""
    return sum(1 << d for d in set(dias))


def _minutos(hora: time) -> int:
    return hora.hour * 60 + hora.minute


def tramos(dias: int, desde: time, hasta: time) -> list[tuple[int, int]]:
    """Los tramos [a, b) de minutos de la semana que cubre una franja. Lo que pasa del domingo vuelve al lunes."""
    inicio, fin = _minutos(desde), _minutos(hasta)
    if fin <= inicio:
        fin += MINUTOS_DIA
    resultado: list[tuple[int, int]] = []
    for dia in range(7):
        if dias & (1 << dia):
            a, b = dia * MINUTOS_DIA + inicio, dia * MINUTOS_DIA + fin
            if b <= MINUTOS_SEMANA:
                resultado.append((a, b))
            else:
                resultado += [(a, MINUTOS_SEMANA), (0, b - MINUTOS_SEMANA)]
    return resultado


def local(momento: datetime) -> datetime:
    return momento.astimezone(ZoneInfo(settings.ZONA_HORARIA))


def minuto_de_semana(momento: datetime) -> int:
    """El minuto de la semana de un momento con hora local."""
    return momento.weekday() * MINUTOS_DIA + momento.hour * 60 + momento.minute


def rige(franja: FranjaTarifa, minuto: int) -> bool:
    return any(a <= minuto < b for a, b in tramos(franja.dias, franja.desde, franja.hasta))


def franja_en(franjas: list[FranjaTarifa], minuto: int) -> FranjaTarifa | None:
    return next((f for f in franjas if rige(f, minuto)), None)


def primer_cruce(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> int | None:
    """El primer minuto de la semana en el que dos conjuntos de tramos coinciden."""
    cruces = [max(x[0], y[0]) for x in a for y in b if max(x[0], y[0]) < min(x[1], y[1])]
    return min(cruces) if cruces else None


def hora_texto(hora: time) -> str:
    return f"{hora.hour:02d}:{hora.minute:02d}"


def momento_texto(minuto: int) -> str:
    return f"{DIAS[minuto // MINUTOS_DIA]} a las {(minuto % MINUTOS_DIA) // 60:02d}:{minuto % 60:02d}"


def dias_texto(dias: int) -> str:
    """«todos los días», «de lunes a jueves», «viernes y sábado» o «lunes, miércoles y viernes»."""
    if dias == TODOS_LOS_DIAS:
        return "todos los días"
    elegidos = [d for d in range(7) if dias & (1 << d)]
    if len(elegidos) >= 3 and elegidos[-1] - elegidos[0] == len(elegidos) - 1:
        return f"de {DIAS[elegidos[0]]} a {DIAS[elegidos[-1]]}"
    nombres = [DIAS[d] for d in elegidos]
    return nombres[0] if len(nombres) == 1 else f"{', '.join(nombres[:-1])} y {nombres[-1]}"


def regla_texto(dias: int, desde: time, hasta: time) -> str:
    """«viernes y sábado de 20:00 a 06:00»."""
    if desde == hasta:
        return f"{dias_texto(dias)}, todo el día"
    return f"{dias_texto(dias)} de {hora_texto(desde)} a {hora_texto(hasta)}"


def cuando_texto(momento: datetime, ahora: datetime) -> str:
    """«hoy a las 20:00», «mañana a las 06:00» o «el sábado a las 22:00». Con horas locales."""
    dias = (momento.date() - ahora.date()).days
    dia = "hoy" if dias == 0 else "mañana" if dias == 1 else f"el {DIAS[momento.weekday()]}"
    return f"{dia} a las {momento:%H:%M}"


def momento_mencionado(texto: str, ahora: datetime) -> tuple[datetime, str] | None:
    """El momento del que habla una pregunta ya normalizada («el sabado a la noche», «a las 22», «esta tarde») y cómo
    decirlo. Sin una hora o una parte del día no alcanza: un día solo tiene varias tarifas."""
    hora, minuto = None, 0
    if m := re.search(r"\b(?:a|de) las (\d{1,2})(?::(\d{2}))?\b", texto):
        hora, minuto = int(m[1]) % 24, int(m[2] or 0)
    elif m := re.search(r"\b(?:a la|de la|por la|esta|al|de) (madrugada|manana|mediodia|siesta|tarde|noche)\b", texto):
        hora = PARTES_DEL_DIA[m[1]]
    if hora is None:
        return None
    sin_parte = re.sub(r"\b(?:a la|de la|por la|esta) manana\b", "", texto)
    dia = next((i for i, d in enumerate(DIAS_SIN_ACENTO) if re.search(rf"\b{d}s?\b", texto)), None)
    fecha = ahora
    if dia is not None:
        fecha = ahora + timedelta(days=(dia - ahora.weekday()) % 7)
    elif re.search(r"\bmanana\b", sin_parte):
        fecha = ahora + timedelta(days=1)
    momento = fecha.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if dia is None and momento < ahora and not re.search(r"\b(hoy|esta)\b", texto):
        momento += timedelta(days=1)
    return momento, cuando_texto(momento, ahora)


# --- Qué tarifa rige ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Vigente:
    """La tarifa que rige en un momento y cuándo deja de regir."""

    tarifa: Tarifa
    franja: FranjaTarifa | None = None
    cambia_en: datetime | None = None
    # La que sigue después del cambio (None: la general o nada) y el nombre de su franja.
    siguiente: Tarifa | None = None
    siguiente_franja: FranjaTarifa | None = None


@dataclass
class Tarifario:
    """Las tarifas generales y las franjas activas con su tarifa, leídas una vez y consultadas por momento."""

    generales: dict[int, Tarifa]
    franjas: dict[int, list[FranjaTarifa]]
    de_franja: dict[int, Tarifa]

    def _proximo_cambio(
        self, franjas: list[FranjaTarifa], momento: datetime
    ) -> tuple[datetime, FranjaTarifa | None] | None:
        actual = minuto_de_semana(momento)
        vigente = franja_en(franjas, actual)
        bordes = {
            borde % MINUTOS_SEMANA for f in franjas for tramo in tramos(f.dias, f.desde, f.hasta) for borde in tramo
        }
        for distancia in sorted((b - actual) % MINUTOS_SEMANA or MINUTOS_SEMANA for b in bordes):
            siguiente = franja_en(franjas, (actual + distancia) % MINUTOS_SEMANA)
            if siguiente is not vigente:
                return momento.replace(second=0, microsecond=0) + timedelta(minutes=distancia), siguiente
        return None

    def en(self, categoria_id: int, momento: datetime) -> Vigente | None:
        """Lo que rige para una categoría en un momento. None si no tiene ninguna tarifa."""
        hora = local(momento)
        franjas = [f for f in self.franjas.get(categoria_id, []) if f.id in self.de_franja]
        franja = franja_en(franjas, minuto_de_semana(hora))
        tarifa = self.de_franja[franja.id] if franja else self.generales.get(categoria_id)
        if tarifa is None:
            return None
        cambio = self._proximo_cambio(franjas, hora) if franjas else None
        if cambio is None:
            return Vigente(tarifa, franja)
        cuando, proxima = cambio
        siguiente = self.de_franja[proxima.id] if proxima else self.generales.get(categoria_id)
        return Vigente(tarifa, franja, cuando.astimezone(UTC), siguiente, proxima)


async def tarifario(db: AsyncSession, categoria_id: int | None = None) -> Tarifario:
    consulta = select(FranjaTarifa).where(FranjaTarifa.activa.is_(True)).order_by(FranjaTarifa.desde, FranjaTarifa.id)
    tarifas = select(Tarifa).where(Tarifa.vigente.is_(True))
    if categoria_id is not None:
        consulta = consulta.where(FranjaTarifa.categoria_id == categoria_id)
        tarifas = tarifas.where(Tarifa.categoria_id == categoria_id)
    franjas: dict[int, list[FranjaTarifa]] = defaultdict(list)
    for f in (await db.execute(consulta)).scalars():
        franjas[f.categoria_id].append(f)
    generales: dict[int, Tarifa] = {}
    de_franja: dict[int, Tarifa] = {}
    for t in (await db.execute(tarifas)).scalars():
        if t.franja_id is None:
            generales[t.categoria_id] = t
        else:
            de_franja[t.franja_id] = t
    return Tarifario(generales, dict(franjas), de_franja)


async def tarifa_en(db: AsyncSession, categoria_id: int, momento: datetime) -> Vigente | None:
    return (await tarifario(db, categoria_id)).en(categoria_id, momento)


# --- Alta, cambio y baja --------------------------------------------------------------------------------------------


def _sin_superposicion(
    otras: list[FranjaTarifa], dias: int, desde: time, hasta: time, salvo_id: int | None = None
) -> None:
    """Un minuto de la semana tiene una sola tarifa. La base lo garantiza; acá se explica qué franja molesta."""
    propios = tramos(dias, desde, hasta)
    for otra in otras:
        if otra.id == salvo_id:
            continue
        cruce = primer_cruce(propios, tramos(otra.dias, otra.desde, otra.hasta))
        if cruce is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Se superpone con «{otra.nombre}» el {momento_texto(cruce)}.",
            )


def _nombre_libre(otras: list[FranjaTarifa], nombre: str, salvo_id: int | None = None) -> None:
    if any(o.id != salvo_id and o.nombre.lower() == nombre.lower() for o in otras):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya hay una tarifa especial «{nombre}».")


def _conflicto() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail="Otro cambio de tarifas se registró al mismo tiempo."
    )


async def _activas(db: AsyncSession, categoria_id: int) -> list[FranjaTarifa]:
    return list(
        (
            await db.execute(
                select(FranjaTarifa).where(FranjaTarifa.categoria_id == categoria_id, FranjaTarifa.activa.is_(True))
            )
        ).scalars()
    )


async def crear(db: AsyncSession, datos: FranjaAlta, operador: Operador) -> FranjaTarifa:
    categoria = await categoria_activa(db, datos.categoria_id)
    nombre = datos.nombre.strip()
    otras = await _activas(db, categoria.id)
    _nombre_libre(otras, nombre)
    _sin_superposicion(otras, datos.dias, datos.desde, datos.hasta)
    franja = FranjaTarifa(
        categoria_id=categoria.id,
        nombre=nombre,
        dias=datos.dias,
        desde=datos.desde,
        hasta=datos.hasta,
        creada_por_id=operador.id,
    )
    db.add(franja)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _conflicto() from None
    db.add(nueva_tarifa_de(categoria, datos.tarifa, operador.id, franja.id))
    await registrar(
        db,
        operador,
        TARIFA,
        "FRANJA_ALTA",
        f"Tarifa especial «{nombre}» de {categoria.nombre}: {regla_texto(datos.dias, datos.desde, datos.hasta)}, "
        f"{datos.tarifa.estadia_base_min} min por {pesos(datos.tarifa.tarifa_base)}",
    )
    await db.commit()
    return franja


async def _franja_activa(db: AsyncSession, franja_id: int) -> FranjaTarifa:
    franja = await db.get(FranjaTarifa, franja_id, with_for_update=True)
    if franja is None or not franja.activa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarifa especial no encontrada")
    return franja


async def _tarifa_de(db: AsyncSession, franja_id: int) -> Tarifa | None:
    consulta = select(Tarifa).where(Tarifa.franja_id == franja_id, Tarifa.vigente.is_(True)).with_for_update()
    return (await db.execute(consulta)).scalars().first()


async def cambiar(db: AsyncSession, franja_id: int, datos: FranjaCambio, operador: Operador) -> FranjaTarifa:
    """Cambia cuándo rige o cuánto sale. Rige hacia adelante: los turnos abiertos conservan su tarifa (RN-DER-06)."""
    franja = await _franja_activa(db, franja_id)
    anterior = regla_texto(franja.dias, franja.desde, franja.hasta)
    cambios = datos.model_dump(exclude_unset=True, exclude={"tarifa"})
    nombre = (cambios.pop("nombre", None) or franja.nombre).strip()
    dias = cambios.get("dias") or franja.dias
    desde = cambios["desde"] if cambios.get("desde") is not None else franja.desde
    hasta = cambios["hasta"] if cambios.get("hasta") is not None else franja.hasta
    otras = await _activas(db, franja.categoria_id)
    _nombre_libre(otras, nombre, franja.id)
    _sin_superposicion(otras, dias, desde, hasta, franja.id)
    franja.nombre, franja.dias, franja.desde, franja.hasta = nombre, dias, desde, hasta
    nueva_regla = regla_texto(dias, desde, hasta)
    if nueva_regla != anterior:
        await registrar(
            db,
            operador,
            TARIFA,
            "FRANJA_CAMBIO",
            f"Tarifa especial «{nombre}»: cambio del horario",
            valor_anterior=anterior,
            valor_nuevo=nueva_regla,
        )
    if datos.tarifa is not None:
        categoria = await categoria_activa(db, franja.categoria_id)
        previa = await _tarifa_de(db, franja.id)
        if previa is not None:
            previa.vigente = False
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise _conflicto() from None
        db.add(nueva_tarifa_de(categoria, datos.tarifa, operador.id, franja.id))
        await registrar(
            db,
            operador,
            TARIFA,
            "FRANJA_PRECIO",
            f"Tarifa especial «{nombre}»: cambio del precio",
            valor_anterior=pesos(previa.tarifa_base) if previa else None,
            valor_nuevo=pesos(datos.tarifa.tarifa_base),
        )
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise _conflicto() from None
    return franja


async def dar_de_baja(db: AsyncSession, franja_id: int, operador: Operador) -> None:
    """Deja de regir para los turnos que se abran después. Lo cobrado con ella queda como está."""
    franja = await _franja_activa(db, franja_id)
    tarifa = await _tarifa_de(db, franja.id)
    if tarifa is not None:
        tarifa.vigente = False
    franja.activa = False
    await registrar(
        db,
        operador,
        TARIFA,
        "FRANJA_BAJA",
        f"Baja de la tarifa especial «{franja.nombre}» ({regla_texto(franja.dias, franja.desde, franja.hasta)})",
    )
    await db.commit()
