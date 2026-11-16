"""Equipos autorizados (migración 019): el conserje entra solo desde los equipos que autorizó la gerencia.

Filtrar solo por la dirección IP no alcanza: dentro del motel, el celular conectado al Wi-Fi tiene una IP de la misma
red que la PC de la ventanilla, y desde internet todos los equipos del motel salen con la misma IP pública, que además
cambia. El navegador tampoco da la dirección física (MAC). Por eso cada navegador recibe una marca propia: una cookie
aleatoria que la página no puede leer. La base guarda solo su resumen SHA-256, como con las claves.

- Un conserje que intenta entrar desde un equipo desconocido no entra, y el equipo queda pendiente para que la
  gerencia lo autorice o lo bloquee. El control va antes de revisar la clave: desde afuera no se pueden ni probar
  claves. Igual se revisa por dentro y se le cuenta a la gerencia si era la correcta (era el propio conserje) o no
  (alguien la adivinaba).
- La gerencia entra desde donde quiera.
- Si la gerencia carga las redes del motel, además el conserje tiene que estar en una de ellas.
- Quitarle la autorización a un equipo corta también la sesión abierta en él (deps.operador_actual).

No es seguridad absoluta: quien sepa copiar una cookie puede llevarla a otro equipo. Es un control razonable para la
ventanilla de un motel. La IP y el tipo de equipo son datos del personal (Ley 25.326): los intentos se borran a los 90
días.
"""

import hashlib
import ipaddress
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.inquilino import CLAVE
from app.models.actividad import ESTABLECIMIENTO, PERSONAL
from app.models.equipo import AUTORIZADO, BLOQUEADO, PENDIENTE, POR_EQUIPO, POR_RED, Equipo, IntentoAcceso
from app.models.establecimiento import Establecimiento
from app.models.operador import ROL_OPERADOR, Operador
from app.services.actividad import registrar
from app.services.liquidacion import con_zona

# Los navegadores guardan una cookie hasta 400 días; se renueva en cada inicio de sesión.
DURACION_COOKIE_DIAS = 400
# Un equipo está «en uso» si se usó en los últimos minutos (la ventanilla consulta la API cada pocos segundos).
EN_USO_MIN = 15
# Cada cuánto se anota el uso de un equipo durante la sesión, para no escribir en cada consulta.
REFRESCO_USO_MIN = 5
# Lo que se muestra y lo que se guarda.
DIAS_DE_INTENTOS = 30
RETENCION_DIAS = 90
# Un mismo intento repetido enseguida (el conserje que insiste) cuenta una vez.
REPETIDO_SEG = 60
# Tope de equipos pendientes nuevos por día: quien pruebe sin cookie no llena la tabla.
MAXIMO_PENDIENTES_POR_DIA = 30
MAXIMO_REDES = 10

NO_AUTORIZADO = "Este equipo no está autorizado para la ventanilla. Se avisó a la gerencia."
FUERA_DE_LA_RED = "Desde esta red no se puede entrar a la ventanilla. Se avisó a la gerencia."
SESION_CORTADA = "Este equipo ya no está autorizado para la ventanilla. Avisá a la gerencia."


# --- La marca del equipo ------------------------------------------------------------------------------------------


def huella_de(marca: str) -> str:
    return hashlib.sha256(marca.encode()).hexdigest()


def marca_de(request: Request) -> str | None:
    marca = request.cookies.get(settings.COOKIE_EQUIPO)
    return marca if marca and 20 <= len(marca) <= 100 else None


def nueva_marca() -> str:
    return secrets.token_urlsafe(32)


def poner_cookie(response: Response, marca: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_EQUIPO,
        value=marca,
        max_age=DURACION_COOKIE_DIAS * 86400,
        path="/api",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
    )


def ip_de(request: Request) -> str | None:
    if settings.CONFIAR_X_FORWARDED_FOR:
        reenviada = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if reenviada:
            return reenviada[:45]
    return request.client.host[:45] if request.client else None


_NAVEGADORES = (
    ("Edge", r"edg(e|a|ios)?/"),
    ("Opera", r"opr/|opera"),
    ("Samsung Internet", r"samsungbrowser"),
    ("Firefox", r"firefox|fxios"),
    ("Chrome", r"chrome|crios"),
    ("Safari", r"safari"),
)
_SISTEMAS = (
    ("iPhone", r"iphone"),
    ("iPad", r"ipad"),
    ("Android", r"android"),
    ("Windows", r"windows"),
    ("Mac", r"mac os|macintosh"),
    ("Linux", r"linux|x11"),
)


def describir(agente: str | None) -> str:
    """«Chrome en Android (celular)»: lo que dice el navegador, resumido. No identifica a la persona."""
    texto = (agente or "").lower()
    navegador = next((n for n, patron in _NAVEGADORES if re.search(patron, texto)), "Navegador")
    sistema = next((s for s, patron in _SISTEMAS if re.search(patron, texto)), "equipo desconocido")
    if sistema == "iPhone" or (sistema == "Android" and "mobile" in texto):
        tipo = " (celular)"
    elif sistema in ("iPad", "Android"):
        tipo = " (tableta)"
    else:
        tipo = ""
    return f"{navegador} en {sistema}{tipo}"[:60]


# --- Redes permitidas ---------------------------------------------------------------------------------------------


def leer_redes(texto: str | None) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Las redes de la gerencia, separadas por comas o espacios. Una IP suelta es una red de una sola dirección."""
    redes = []
    for parte in re.split(r"[,\s;]+", (texto or "").strip()):
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            raise HTTPException(
                status_code=422, detail=f"«{parte}» no es una red válida. Ejemplo: 192.168.0.0/24 o 192.168.0.10."
            ) from None
    if len(redes) > MAXIMO_REDES:
        raise HTTPException(status_code=422, detail=f"Se pueden cargar hasta {MAXIMO_REDES} redes.")
    return redes


def en_las_redes(ip: str | None, texto: str | None) -> bool:
    redes = leer_redes(texto)
    if not redes:
        return True
    try:
        direccion = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    if direccion.version == 6 and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    return any(direccion in red for red in redes)


# --- Control ------------------------------------------------------------------------------------------------------


async def _equipo(db: AsyncSession, marca: str | None) -> Equipo | None:
    if not marca:
        return None
    return (await db.execute(select(Equipo).where(Equipo.huella == huella_de(marca)))).scalars().first()


async def motivo_de_rechazo(
    db: AsyncSession, establecimiento: Establecimiento, marca: str | None, ip: str | None
) -> str | None:
    """None si un conserje puede entrar desde acá; si no, POR_EQUIPO o POR_RED."""
    if not establecimiento.control_equipos:
        return None
    equipo = await _equipo(db, marca)
    if equipo is None or equipo.estado != AUTORIZADO:
        return POR_EQUIPO
    if not en_las_redes(ip, establecimiento.redes_permitidas):
        return POR_RED
    return None


def mensaje_de(motivo: str) -> str:
    return FUERA_DE_LA_RED if motivo == POR_RED else NO_AUTORIZADO


async def _pendiente(db: AsyncSession, marca: str, descripcion: str, ip: str | None, operador: Operador | None):
    """El equipo de la marca; si no existe y hay lugar, lo deja pendiente para que la gerencia decida."""
    equipo = await _equipo(db, marca)
    if equipo is not None:
        return equipo
    desde = datetime.now(UTC) - timedelta(days=1)
    nuevos = (
        await db.execute(select(func.count(Equipo.id)).where(Equipo.estado == PENDIENTE, Equipo.creado_en >= desde))
    ).scalar_one()
    if nuevos >= MAXIMO_PENDIENTES_POR_DIA:
        return None
    equipo = Equipo(
        huella=huella_de(marca),
        descripcion=descripcion,
        ultima_ip=ip,
        ultimo_operador_id=operador.id if operador else None,
        ultimo_uso=datetime.now(UTC),
    )
    db.add(equipo)
    await db.flush()
    return equipo


async def registrar_intento(
    db: AsyncSession,
    request: Request,
    marca: str,
    operador: Operador | None,
    clave_correcta: bool,
    motivo: str,
) -> None:
    """Anota el intento (una vez si se repite enseguida) y deja el equipo pendiente si es nuevo."""
    ip, descripcion = ip_de(request), describir(request.headers.get("user-agent"))
    equipo = await _pendiente(db, marca, descripcion, ip, operador) if operador else await _equipo(db, marca)
    if equipo is not None and equipo.estado == PENDIENTE:
        equipo.ultima_ip, equipo.ultimo_uso, equipo.descripcion = ip, datetime.now(UTC), descripcion
        if operador:
            equipo.ultimo_operador_id = operador.id
    mismo = select(IntentoAcceso.id).where(
        IntentoAcceso.creado_en >= datetime.now(UTC) - timedelta(seconds=REPETIDO_SEG)
    )
    mismo = mismo.where(
        IntentoAcceso.operador_id == operador.id if operador else IntentoAcceso.operador_id.is_(None)
    )
    mismo = mismo.where(IntentoAcceso.equipo_id == equipo.id if equipo else IntentoAcceso.ip == ip)
    if (await db.execute(mismo)).first() is None:
        db.add(
            IntentoAcceso(
                equipo_id=equipo.id if equipo else None,
                operador_id=operador.id if operador else None,
                clave_correcta=clave_correcta,
                motivo=motivo,
                ip=ip,
                descripcion=descripcion,
            )
        )
    await db.commit()


async def anotar_uso(db: AsyncSession, request: Request, marca: str, operador: Operador) -> None:
    """Al entrar: el equipo del conserje queda registrado (pendiente si es nuevo, para que la gerencia lo vea antes de
    activar el control); el de la gerencia, solo si ya existe."""
    ip, descripcion = ip_de(request), describir(request.headers.get("user-agent"))
    if operador.rol == ROL_OPERADOR:
        equipo = await _pendiente(db, marca, descripcion, ip, operador)
    else:
        equipo = await _equipo(db, marca)
    if equipo is not None:
        equipo.ultima_ip, equipo.ultimo_uso, equipo.ultimo_operador_id = ip, datetime.now(UTC), operador.id
        equipo.descripcion = descripcion


async def controlar_sesion(db: AsyncSession, request: Request, establecimiento: Establecimiento, operador: Operador):
    """En cada consulta de un conserje: si su equipo dejó de estar autorizado (o salió de la red), la sesión se corta.
    De paso anota el uso, cada algunos minutos."""
    marca = marca_de(request)
    ip = ip_de(request)
    if establecimiento.control_equipos and await motivo_de_rechazo(db, establecimiento, marca, ip):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=SESION_CORTADA)
    equipo = await _equipo(db, marca)
    ahora = datetime.now(UTC)
    if equipo is not None and (
        equipo.ultimo_uso is None or ahora - con_zona(equipo.ultimo_uso) > timedelta(minutes=REFRESCO_USO_MIN)
    ):
        equipo.ultimo_uso, equipo.ultima_ip, equipo.ultimo_operador_id = ahora, ip, operador.id
        await db.commit()


# --- Gerencia -----------------------------------------------------------------------------------------------------


async def _establecimiento(db: AsyncSession) -> Establecimiento:
    establecimiento = await db.get(Establecimiento, db.info.get(CLAVE))
    if establecimiento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Establecimiento no encontrado")
    return establecimiento


def _en_uso(equipo: Equipo, ahora: datetime) -> bool:
    return equipo.ultimo_uso is not None and ahora - con_zona(equipo.ultimo_uso) <= timedelta(minutes=EN_USO_MIN)


async def _nombres(db: AsyncSession) -> dict[int, tuple[str, str]]:
    filas = (await db.execute(select(Operador.id, Operador.nombre_visible, Operador.usuario))).all()
    return {i: (nombre, usuario) for i, nombre, usuario in filas}


def _intento(intento: IntentoAcceso, nombres: dict, equipos: dict[int, Equipo]) -> dict:
    equipo = equipos.get(intento.equipo_id)
    nombre, usuario = nombres.get(intento.operador_id, (None, None))
    return {
        "id": intento.id,
        "creado_en": con_zona(intento.creado_en).isoformat(),
        "operador": nombre,
        "usuario": usuario,
        "clave_correcta": intento.clave_correcta,
        "motivo": intento.motivo,
        "ip": intento.ip,
        "descripcion": intento.descripcion,
        "equipo_id": intento.equipo_id,
        "equipo_estado": equipo.estado if equipo else None,
        "equipo_nombre": equipo.nombre if equipo else None,
    }


async def panel(db: AsyncSession, request: Request) -> dict:
    """Lo que ve la gerencia: los equipos (en uso, autorizados, pendientes y bloqueados) y los intentos del mes."""
    establecimiento = await _establecimiento(db)
    ahora = datetime.now(UTC)
    nombres = await _nombres(db)
    equipos = list((await db.execute(select(Equipo))).scalars())
    orden = {PENDIENTE: 0, AUTORIZADO: 1, BLOQUEADO: 2}
    equipos.sort(key=lambda e: (orden[e.estado], -(con_zona(e.ultimo_uso or e.creado_en).timestamp())))
    desde = ahora - timedelta(days=DIAS_DE_INTENTOS)
    intentos = list(
        (
            await db.execute(
                select(IntentoAcceso)
                .where(IntentoAcceso.creado_en >= desde)
                .order_by(IntentoAcceso.creado_en.desc(), IntentoAcceso.id.desc())
                .limit(100)
            )
        ).scalars()
    )
    este = await _equipo(db, marca_de(request))
    por_id = {e.id: e for e in equipos}
    return {
        "control": bool(establecimiento.control_equipos),
        "redes": establecimiento.redes_permitidas,
        "ip_actual": ip_de(request),
        "este_equipo_id": este.id if este else None,
        "equipos": [
            {
                "id": e.id,
                "nombre": e.nombre,
                "estado": e.estado,
                "descripcion": e.descripcion,
                "ultima_ip": e.ultima_ip,
                "ultimo_uso": con_zona(e.ultimo_uso).isoformat() if e.ultimo_uso else None,
                "ultimo_operador": nombres.get(e.ultimo_operador_id, (None,))[0],
                "en_uso": e.estado == AUTORIZADO and _en_uso(e, ahora),
                "decidido_por": nombres.get(e.decidido_por_id, (None,))[0],
                "decidido_en": con_zona(e.decidido_en).isoformat() if e.decidido_en else None,
                "creado_en": con_zona(e.creado_en).isoformat(),
            }
            for e in equipos
        ],
        "intentos": [_intento(i, nombres, por_id) for i in intentos],
    }


async def intentos_recientes(db: AsyncSession, horas: int = 24) -> list[dict]:
    """Para la campanita de la gerencia: los intentos del último día."""
    desde = datetime.now(UTC) - timedelta(hours=horas)
    intentos = list(
        (
            await db.execute(
                select(IntentoAcceso)
                .where(IntentoAcceso.creado_en >= desde)
                .order_by(IntentoAcceso.creado_en.desc(), IntentoAcceso.id.desc())
                .limit(20)
            )
        ).scalars()
    )
    ids = {i.equipo_id for i in intentos if i.equipo_id}
    equipos = {e.id: e for e in (await db.execute(select(Equipo).where(Equipo.id.in_(ids)))).scalars()} if ids else {}
    nombres = await _nombres(db)
    return [_intento(i, nombres, equipos) for i in intentos]


async def _equipo_por_id(db: AsyncSession, equipo_id: int) -> Equipo:
    # Una consulta (no db.get, que puede responder desde la sesión sin el filtro de establecimiento).
    equipo = (await db.execute(select(Equipo).where(Equipo.id == equipo_id))).scalars().first()
    if equipo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="El equipo no existe.")
    return equipo


def _nombre_limpio(nombre: str) -> str:
    limpio = re.sub(r"\s+", " ", nombre or "").strip()
    if not limpio:
        raise HTTPException(status_code=422, detail="Poné un nombre para reconocer el equipo, como «PC Ventanilla».")
    return limpio[:40]


async def autorizar(db: AsyncSession, gerencia: Operador, equipo_id: int, nombre: str) -> dict:
    equipo = await _equipo_por_id(db, equipo_id)
    equipo.nombre = _nombre_limpio(nombre)
    anterior = equipo.estado
    equipo.estado, equipo.decidido_por_id, equipo.decidido_en = AUTORIZADO, gerencia.id, datetime.now(UTC)
    await registrar(
        db,
        gerencia,
        PERSONAL,
        "EQUIPO_AUTORIZADO",
        f"Equipo autorizado para la ventanilla: {equipo.nombre} ({equipo.descripcion})",
        valor_anterior=anterior,
        valor_nuevo=AUTORIZADO,
    )
    await db.commit()
    return {"ok": True}


async def bloquear(db: AsyncSession, gerencia: Operador, equipo_id: int) -> dict:
    """Rechaza un equipo pendiente o le quita la autorización a uno autorizado: su sesión abierta se corta."""
    equipo = await _equipo_por_id(db, equipo_id)
    if equipo.estado == BLOQUEADO:
        return {"ok": True}
    anterior = equipo.estado
    equipo.estado, equipo.decidido_por_id, equipo.decidido_en = BLOQUEADO, gerencia.id, datetime.now(UTC)
    que = "Se quitó la autorización" if anterior == AUTORIZADO else "Se rechazó"
    await registrar(
        db,
        gerencia,
        PERSONAL,
        "EQUIPO_BLOQUEADO",
        f"{que} al equipo {equipo.nombre or equipo.descripcion}",
        valor_anterior=anterior,
        valor_nuevo=BLOQUEADO,
    )
    await db.commit()
    return {"ok": True}


async def autorizar_este(db: AsyncSession, request: Request, response: Response, gerencia: Operador, nombre: str):
    """La gerencia, sentada frente a la PC de la ventanilla, la autoriza desde su propia sesión."""
    marca = marca_de(request) or nueva_marca()
    poner_cookie(response, marca)
    nombre = _nombre_limpio(nombre)
    equipo = await _equipo(db, marca)
    if equipo is not None:
        return await autorizar(db, gerencia, equipo.id, nombre)
    descripcion = describir(request.headers.get("user-agent"))
    db.add(
        Equipo(
            huella=huella_de(marca),
            nombre=nombre,
            estado=AUTORIZADO,
            descripcion=descripcion,
            ultima_ip=ip_de(request),
            ultimo_operador_id=gerencia.id,
            ultimo_uso=datetime.now(UTC),
            decidido_por_id=gerencia.id,
            decidido_en=datetime.now(UTC),
        )
    )
    await registrar(
        db,
        gerencia,
        PERSONAL,
        "EQUIPO_AUTORIZADO",
        f"Equipo autorizado para la ventanilla: {nombre} ({descripcion})",
        valor_nuevo=AUTORIZADO,
    )
    await db.commit()
    return {"ok": True}


async def cambiar_ajustes(db: AsyncSession, gerencia: Operador, control: bool | None, redes: str | None) -> dict:
    establecimiento = await _establecimiento(db)
    if redes is not None:
        lista = leer_redes(redes)
        nuevas = ", ".join(str(r) for r in lista) or None
        if nuevas != establecimiento.redes_permitidas:
            await registrar(
                db,
                gerencia,
                ESTABLECIMIENTO,
                "EQUIPOS_REDES",
                "Redes desde donde el conserje puede entrar" if nuevas else "Sin restricción de red para el conserje",
                valor_anterior=establecimiento.redes_permitidas,
                valor_nuevo=nuevas,
            )
            establecimiento.redes_permitidas = nuevas
    if control is not None and control != bool(establecimiento.control_equipos):
        if control:
            autorizados = (
                await db.execute(select(func.count(Equipo.id)).where(Equipo.estado == AUTORIZADO))
            ).scalar_one()
            if not autorizados:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Autorizá al menos un equipo antes de activar el control: si no, ningún conserje podría "
                    "entrar.",
                )
        establecimiento.control_equipos = control
        await registrar(
            db,
            gerencia,
            ESTABLECIMIENTO,
            "EQUIPOS_CONTROL",
            "El conserje entra solo desde equipos autorizados"
            if control
            else "El conserje puede entrar desde cualquier equipo",
            valor_anterior="Activo" if not control else "Apagado",
            valor_nuevo="Activo" if control else "Apagado",
        )
    await db.commit()
    return {"control": bool(establecimiento.control_equipos), "redes": establecimiento.redes_permitidas}


async def depurar_intentos(db: AsyncSession, ahora: datetime | None = None) -> int:
    """Borra los intentos de más de 90 días (la base no deja borrar uno más nuevo)."""
    limite = (ahora or datetime.now(UTC)) - timedelta(days=RETENCION_DIAS)
    res = await db.execute(delete(IntentoAcceso).where(IntentoAcceso.creado_en < limite))
    await db.commit()
    return res.rowcount or 0
