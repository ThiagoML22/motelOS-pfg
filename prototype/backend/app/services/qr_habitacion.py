"""QR fijo de la habitación (migración 020): el cliente ve su estadía sin ticket y sin hablar con la ventanilla.

El QR impreso dice solo qué habitación es, con una firma del servidor y una versión que la gerencia cambia si se filtra
(no se puede pasar de la 5 a la 6 tocando el enlace). Quién lo escanea se decide así:

- El primer celular que lo escanea durante una estadía queda vinculado a ella con una cookie aleatoria que la página no
  puede leer (la base guarda solo su resumen SHA-256). Desde ese celular se suman los demás, con un QR que dura minutos.
- Cualquier otro ve solo la carta, igual que con la habitación libre: el QR fijo nunca dice si la habitación está
  ocupada.
- Un celular que estuvo en esta habitación en las últimas 12 horas no puede quedarse con la estadía siguiente (es el
  caso de quien guardó el enlace), ni uno que ya tiene otra estadía en curso.
- Si alguien se adelantó, el cliente avisa a la ventanilla desde la carta («¿Estás en esta habitación y no ves tu
  estadía?»). El conserje libera el QR, que corta los celulares vinculados; desde ahí la regla de las 12 horas no
  aplica a esa estadía, pero el celular desvinculado no puede volver a entrar.

Al terminar la estadía el vínculo deja de abrir nada, salvo la calificación durante la hora siguiente al cobro. No hay
cuenta ni datos personales; los vínculos se depuran a los 30 días.
"""

import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

import segno
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.inquilino import fijar_establecimiento
from app.models.actividad import HABITACION
from app.models.articulo import Articulo
from app.models.calificacion import Calificacion
from app.models.categoria import CategoriaHabitacion
from app.models.establecimiento import Establecimiento
from app.models.habitacion import Habitacion
from app.models.operador import Operador
from app.models.pedido_cliente import ATENDIDO, SIN_RESOLVER, VINCULO, PedidoCliente
from app.models.turno import Turno
from app.models.vinculo_cliente import INVITADO, POR_QR, VinculoCliente
from app.services.acceso_cliente import firmar, puede_calificar
from app.services.actividad import registrar
from app.services.equipos import huella_de
from app.services.liquidacion import con_zona

MAXIMO_CELULARES = 3
# Un celular que estuvo en la habitación hace menos que esto no se queda con la estadía siguiente.
BLOQUEO_HORAS = 12
# Lo que dura el QR para sumar otro celular.
INVITACION_MIN = 10
# La cookie alcanza para la regla de las 12 horas y la calificación; no hace falta que dure más.
DURACION_COOKIE_DIAS = 7
RETENCION_DIAS = 30
# Avisos «no veo mi estadía» por estadía: alcanzan para un reclamo real y frenan a quien quiera molestar.
MAXIMO_AVISOS = 3

NO_VALIDO = "Este código no es válido."
INVITACION_VENCIDA = "El código para sumarte venció. Pedí uno nuevo en el celular que ya está conectado."
LLENA = f"Ya hay {MAXIMO_CELULARES} celulares conectados a esta estadía."

LIBRE = "libre"
VINCULADO = "vinculado"
TERMINADA = "terminada"


# --- Firmas ---------------------------------------------------------------------------------------------------------


def _numeros(partes: list[str]) -> list[int] | None:
    if not all(p.isascii() and p.isdigit() and len(p) <= 12 for p in partes):
        return None
    return [int(p) for p in partes]


def _leer(proposito: bytes, token: str, prefijo: str | None = None) -> list[int] | None:
    partes = token.split(".")
    if prefijo is not None:
        if not partes or partes[0] != prefijo:
            return None
        partes = partes[1:]
    if len(partes) < 2:
        return None
    *datos, firma = partes
    numeros = _numeros(datos)
    if numeros is None or not hmac.compare_digest(firma, firmar(proposito, ".".join(datos))):
        return None
    return numeros


def qr_de(habitacion: Habitacion) -> str:
    texto = f"{habitacion.establecimiento_id}.{habitacion.id}.{habitacion.qr_version}"
    return f"{texto}.{firmar(b'qr-habitacion', texto)}"


def leer_qr(token: str) -> tuple[int, int, int] | None:
    numeros = _leer(b"qr-habitacion", token)
    return (numeros[0], numeros[1], numeros[2]) if numeros and len(numeros) == 3 else None


def token_de_vinculo(vinculo: VinculoCliente) -> str:
    texto = f"{vinculo.establecimiento_id}.{vinculo.id}"
    return f"v.{texto}.{firmar(b'vinculo-cliente', texto)}"


def leer_token_de_vinculo(token: str) -> tuple[int, int] | None:
    numeros = _leer(b"vinculo-cliente", token, prefijo="v")
    return (numeros[0], numeros[1]) if numeros and len(numeros) == 2 else None


def es_de_vinculo(token: str) -> bool:
    return token.startswith("v.")


def _invitacion(vinculo: VinculoCliente, expira: int) -> str:
    texto = f"{vinculo.establecimiento_id}.{vinculo.id}.{expira}"
    return f"{texto}.{firmar(b'sumar-celular', texto)}"


def leer_invitacion(token: str) -> tuple[int, int, int] | None:
    """Establecimiento, vínculo de quien invita y vencimiento (segundos desde 1970), si la firma es válida."""
    numeros = _leer(b"sumar-celular", token)
    return (numeros[0], numeros[1], numeros[2]) if numeros and len(numeros) == 3 else None


def vencida(invitacion: tuple[int, int, int], ahora: float | None = None) -> bool:
    return invitacion[2] < (ahora if ahora is not None else time.time())


def direccion_qr(habitacion: Habitacion) -> str:
    return f"{settings.url_aplicacion}/?habitacion={qr_de(habitacion)}"


def imagen_qr(direccion: str) -> str:
    return segno.make(direccion, error="m", boost_error=False).svg_data_uri(scale=4, border=2)


# --- La marca del celular -------------------------------------------------------------------------------------------


def marca_de(request: Request) -> str | None:
    marca = request.cookies.get(settings.COOKIE_CLIENTE)
    return marca if marca and 20 <= len(marca) <= 100 else None


def nueva_marca() -> str:
    return secrets.token_urlsafe(32)


def poner_cookie(response: Response, marca: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_CLIENTE,
        value=marca,
        max_age=DURACION_COOKIE_DIAS * 86400,
        path="/api",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
    )


# --- Lo que lee el QR -----------------------------------------------------------------------------------------------


async def establecimiento_activo(db: AsyncSession, establecimiento_id: int | None) -> Establecimiento:
    """El establecimiento del enlace, ya fijado para RLS. Un enlace de un motel suspendido no abre nada."""
    establecimiento = await db.get(Establecimiento, establecimiento_id) if establecimiento_id else None
    if establecimiento is None or not establecimiento.activo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_VALIDO)
    await fijar_establecimiento(db, establecimiento.id)
    return establecimiento


async def habitacion_del_qr(db: AsyncSession, token: str) -> tuple[Establecimiento, Habitacion]:
    datos = leer_qr(token)
    establecimiento = await establecimiento_activo(db, datos[0] if datos else None)
    habitacion = (await db.execute(select(Habitacion).where(Habitacion.id == datos[1]))).scalars().first()
    # Un QR regenerado por la gerencia deja de servir: la versión impresa ya no coincide.
    if habitacion is None or not habitacion.activa or habitacion.qr_version != datos[2]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NO_VALIDO)
    return establecimiento, habitacion


async def _en_curso(db: AsyncSession, habitacion_id: int) -> Turno | None:
    consulta = select(Turno).where(Turno.habitacion_id == habitacion_id, Turno.estado == "En Curso")
    return (await db.execute(consulta)).scalars().first()


async def _activos(db: AsyncSession, turno_id) -> int:
    consulta = select(func.count(VinculoCliente.id)).where(
        VinculoCliente.turno_id == turno_id, VinculoCliente.revocado_en.is_(None)
    )
    return (await db.execute(consulta)).scalar_one()


async def _del_celular(db: AsyncSession, huella: str) -> list[tuple[VinculoCliente, Turno]]:
    consulta = (
        select(VinculoCliente, Turno)
        .join(Turno, Turno.id == VinculoCliente.turno_id)
        .where(VinculoCliente.huella == huella)
        .order_by(VinculoCliente.creado_en.desc(), VinculoCliente.id.desc())
        .limit(50)
    )
    return [(v, t) for v, t in (await db.execute(consulta)).all()]


async def _calificada(db: AsyncSession, turno: Turno) -> bool:
    return (await db.execute(select(Calificacion.id).where(Calificacion.turno_id == turno.id))).first() is not None


async def _liberada(db: AsyncSession, turno: Turno) -> bool:
    """La ventanilla ya liberó el QR de esta estadía por un aviso del cliente."""
    consulta = select(PedidoCliente.id).where(
        PedidoCliente.turno_id == turno.id, PedidoCliente.tipo == VINCULO, PedidoCliente.estado == ATENDIDO
    )
    return (await db.execute(consulta)).first() is not None


async def _puede_quedarse(
    db: AsyncSession, turno: Turno, habitacion: Habitacion, del_celular: list[tuple[VinculoCliente, Turno]]
) -> bool:
    if await _activos(db, turno.id):
        return False
    if any(v.revocado_en is None and t.estado == "En Curso" and t.id != turno.id for v, t in del_celular):
        return False
    if await _liberada(db, turno):
        return True
    limite = datetime.now(UTC) - timedelta(hours=BLOQUEO_HORAS)
    return not any(
        t.habitacion_id == habitacion.id and t.id != turno.id and con_zona(v.creado_en) >= limite
        for v, t in del_celular
    )


async def carta(db: AsyncSession, establecimiento: Establecimiento, habitacion: Habitacion) -> dict:
    """Lo que ve quien no está vinculado: lo mismo con la habitación libre u ocupada."""
    categoria = await db.get(CategoriaHabitacion, habitacion.categoria_id)
    articulos = (
        await db.execute(
            select(Articulo)
            .where(Articulo.activo.is_(True), Articulo.stock_actual > 0)
            .order_by(Articulo.categoria, Articulo.descripcion)
        )
    ).scalars()
    respuesta = {
        "estado": LIBRE,
        "motel": establecimiento.nombre,
        "color_marca": establecimiento.color_marca,
        "numero": habitacion.numero,
        "categoria": categoria.nombre if categoria else None,
        "bienvenida": establecimiento.bienvenida,
        "articulos": [
            {"descripcion": a.descripcion, "precio": float(a.precio_unitario), "categoria": a.categoria}
            for a in articulos
        ],
    }
    await db.rollback()
    return respuesta


def _vinculado(vinculo: VinculoCliente) -> dict:
    return {"estado": VINCULADO, "token": token_de_vinculo(vinculo)}


async def entrar(db: AsyncSession, establecimiento: Establecimiento, habitacion: Habitacion, huella: str) -> dict:
    """El celular escaneó el QR fijo: ve su estadía, se queda con ella si nadie la tiene, o ve la carta."""
    # Se bloquea la habitación: dos celulares que escanean a la vez no se quedan los dos con la estadía.
    await db.execute(select(Habitacion.id).where(Habitacion.id == habitacion.id).with_for_update())
    turno = await _en_curso(db, habitacion.id)
    del_celular = await _del_celular(db, huella)
    if turno is not None:
        mio = next((v for v, t in del_celular if t.id == turno.id), None)
        if mio is not None and mio.revocado_en is None:
            respuesta = _vinculado(mio)
            await db.rollback()
            return respuesta
        if mio is None and await _puede_quedarse(db, turno, habitacion, del_celular):
            vinculo = VinculoCliente(turno_id=turno.id, huella=huella, origen=POR_QR)
            db.add(vinculo)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                return await carta(db, establecimiento, habitacion)
            return _vinculado(vinculo)
    # Quien acaba de irse y no calificó todavía puede hacerlo desde el mismo QR.
    ultimo = next(((v, t) for v, t in del_celular if t.habitacion_id == habitacion.id), None)
    if ultimo is not None:
        vinculo, anterior = ultimo
        cerrada = anterior.estado != "En Curso"
        if (
            cerrada
            and vinculo.revocado_en is None
            and puede_calificar(anterior, datetime.now(UTC))
            and not await _calificada(db, anterior)
        ):
            respuesta = {"estado": TERMINADA, "token": token_de_vinculo(vinculo)}
            await db.rollback()
            return respuesta
    return await carta(db, establecimiento, habitacion)


async def avisar(db: AsyncSession, habitacion: Habitacion) -> dict:
    """«Estoy en la habitación y no veo mi estadía». Responde siempre lo mismo: no dice si está ocupada."""
    turno = await _en_curso(db, habitacion.id)
    if turno is not None:
        avisos = list(
            (
                await db.execute(
                    select(PedidoCliente).where(PedidoCliente.turno_id == turno.id, PedidoCliente.tipo == VINCULO)
                )
            ).scalars()
        )
        if len(avisos) < MAXIMO_AVISOS and not any(p.estado in SIN_RESOLVER for p in avisos):
            db.add(PedidoCliente(turno_id=turno.id, tipo=VINCULO))
            await db.commit()
    return {"ok": True}


# --- El celular vinculado -------------------------------------------------------------------------------------------


async def vinculo_vigente(db: AsyncSession, vinculo_id: int, marca: str | None) -> tuple[VinculoCliente, Turno] | None:
    """El vínculo del enlace, si sigue vigente y es de este celular: copiar el enlace a otro celular no sirve."""
    if marca is None:
        return None
    vinculo = (await db.execute(select(VinculoCliente).where(VinculoCliente.id == vinculo_id))).scalars().first()
    if vinculo is None or vinculo.revocado_en is not None or not hmac.compare_digest(vinculo.huella, huella_de(marca)):
        return None
    turno = (await db.execute(select(Turno).where(Turno.id == vinculo.turno_id))).scalars().first()
    return (vinculo, turno) if turno is not None else None


async def invitar(db: AsyncSession, vinculo: VinculoCliente, turno: Turno) -> dict:
    """Un QR que dura unos minutos para sumar otro celular a la estadía."""
    if turno.estado != "En Curso":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta estadía ya terminó.")
    if await _activos(db, turno.id) >= MAXIMO_CELULARES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=LLENA)
    expira = int(time.time()) + INVITACION_MIN * 60
    direccion = f"{settings.url_aplicacion}/?sumar={_invitacion(vinculo, expira)}"
    await db.rollback()
    return {
        "direccion": direccion,
        "qr": imagen_qr(direccion),
        "vence": datetime.fromtimestamp(expira, UTC).isoformat(),
    }


async def sumar(db: AsyncSession, token: str, huella: str) -> dict:
    datos = leer_invitacion(token)
    if datos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=INVITACION_VENCIDA)
    await establecimiento_activo(db, datos[0])
    anfitrion = (await db.execute(select(VinculoCliente).where(VinculoCliente.id == datos[1]))).scalars().first()
    turno = None
    if anfitrion is not None and anfitrion.revocado_en is None:
        turno = (await db.execute(select(Turno).where(Turno.id == anfitrion.turno_id))).scalars().first()
    if turno is None or turno.estado != "En Curso":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=INVITACION_VENCIDA)
    consulta = select(VinculoCliente).where(VinculoCliente.turno_id == turno.id, VinculoCliente.huella == huella)
    mio = (await db.execute(consulta)).scalars().first()
    if mio is not None:
        if mio.revocado_en is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Este celular ya no puede sumarse a esta estadía."
            )
        # Ya se sumó: recargar la página después del vencimiento no lo deja afuera.
        respuesta = _vinculado(mio)
        await db.rollback()
        return respuesta
    if vencida(datos):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=INVITACION_VENCIDA)
    if await _activos(db, turno.id) >= MAXIMO_CELULARES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=LLENA)
    vinculo = VinculoCliente(turno_id=turno.id, huella=huella, origen=INVITADO)
    db.add(vinculo)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=LLENA) from None
    return _vinculado(vinculo)


# --- La ventanilla y la gerencia ------------------------------------------------------------------------------------


async def vinculados(db: AsyncSession, turno_id) -> int:
    return await _activos(db, turno_id)


async def desvincular(db: AsyncSession, turno_id, operador: Operador) -> int:
    """Corta los celulares vinculados a la estadía. El que vuelva a escanear primero se queda con ella."""
    activos = (
        await db.execute(
            select(VinculoCliente).where(VinculoCliente.turno_id == turno_id, VinculoCliente.revocado_en.is_(None))
        )
    ).scalars()
    cortados = 0
    for vinculo in activos:
        vinculo.revocado_en = datetime.now(UTC)
        vinculo.revocado_por_id = operador.id
        cortados += 1
    return cortados


def _qr_de_la_habitacion(habitacion: Habitacion, categorias: dict[int, str]) -> dict:
    direccion = direccion_qr(habitacion)
    return {
        "id": habitacion.id,
        "numero": habitacion.numero,
        "categoria": categorias.get(habitacion.categoria_id),
        "version": habitacion.qr_version,
        "direccion": direccion,
        "qr": imagen_qr(direccion),
    }


async def _categorias(db: AsyncSession) -> dict[int, str]:
    return {c.id: c.nombre for c in (await db.execute(select(CategoriaHabitacion))).scalars()}


async def qrs(db: AsyncSession) -> list[dict]:
    """Los QR para imprimir y pegar, uno por habitación activa."""
    habitaciones = (
        await db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))
    ).scalars()
    categorias = await _categorias(db)
    return [_qr_de_la_habitacion(h, categorias) for h in habitaciones]


async def regenerar(db: AsyncSession, habitacion_id: int, operador: Operador) -> dict:
    """Un QR nuevo para la habitación: el impreso deja de servir. Los celulares ya vinculados siguen igual."""
    habitacion = (
        await db.execute(select(Habitacion).where(Habitacion.id == habitacion_id).with_for_update())
    ).scalars().first()
    if habitacion is None or not habitacion.activa:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Habitación no encontrada")
    habitacion.qr_version += 1
    await registrar(
        db, operador, HABITACION, "HABITACION_QR", f"QR nuevo para la habitación {habitacion.numero}",
        valor_anterior=str(habitacion.qr_version - 1), valor_nuevo=str(habitacion.qr_version),
    )
    await db.commit()
    await db.refresh(habitacion)
    return _qr_de_la_habitacion(habitacion, await _categorias(db))


async def depurar_vinculos(db: AsyncSession, ahora: datetime | None = None) -> int:
    """Borra los vínculos de más de 30 días (la base no deja borrar uno más nuevo)."""
    limite = (ahora or datetime.now(UTC)) - timedelta(days=RETENCION_DIAS)
    res = await db.execute(delete(VinculoCliente).where(VinculoCliente.creado_en < limite))
    await db.commit()
    return res.rowcount or 0
