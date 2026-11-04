"""Comprobantes verificables (migración 012): cada arqueo lleva una huella encadenada con la del anterior.

La huella es el SHA-256 de los datos del arqueo, de cada cobro de su guardia y de la huella anterior. Quien cambia un
importe directamente en la base rompe esa coincidencia; si además recalcula la huella, se corta la cadena con el arqueo
siguiente; y si rehace la cadena entera, ya no coincide con la huella impresa en los comprobantes firmados, que están en
papel. No necesita claves ni servicios externos: cualquiera puede recalcularla con los mismos datos.

Es evidencia de alteración, no una traba: las reglas de la base siguen siendo las que impiden modificar un arqueo.
"""

import hashlib
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.arqueo import ArqueoCaja
from app.models.guardia import Guardia
from app.models.operador import Operador
from app.models.pago import Pago
from app.models.sello_arqueo import SelloArqueo
from app.services.liquidacion import con_zona

# La huella anterior del primer arqueo de cada establecimiento.
HUELLA_INICIAL = "0" * 64
LARGO_CODIGO = 16
MINIMO_CODIGO = 8


def codigo_de(huella: str) -> str:
    """Los primeros 16 caracteres de la huella, en grupos de 4: lo que se lee en el papel y se tipea para verificar."""
    corto = huella[:LARGO_CODIGO].upper()
    return "-".join(corto[i : i + 4] for i in range(0, LARGO_CODIGO, 4))


def normalizar_codigo(texto: str) -> str:
    return re.sub(r"[^0-9a-f]", "", texto.lower())


def _monto(valor) -> str:
    return str(Decimal(str(valor)).quantize(Decimal("0.01")))


def contenido_de(arqueo: ArqueoCaja, pagos: list[Pago]) -> str:
    """Lo que la huella protege, en un texto canónico: mismos datos, mismo texto, en cualquier base."""
    campos = [
        arqueo.id,
        arqueo.guardia_id,
        arqueo.operador_id,
        arqueo.confirmado_por_id or "",
        *map(
            _monto,
            (
                arqueo.declarado_efectivo,
                arqueo.declarado_posnet,
                arqueo.declarado_mercado_pago,
                arqueo.total_declarado,
                arqueo.sistema_efectivo,
                arqueo.sistema_posnet,
                arqueo.sistema_mercado_pago,
                arqueo.total_sistema,
                arqueo.diferencia,
            ),
        ),
        arqueo.categoria,
        con_zona(arqueo.confirmado_en).astimezone(UTC).isoformat(),
        arqueo.observacion or "",
    ]
    cobros = sorted(f"{p.id}:{p.medio_pago}:{_monto(p.monto)}:{p.comprobante_referencia or ''}" for p in pagos)
    return "|".join(map(str, campos)) + "|" + ";".join(cobros)


def huella_de(anterior: str, secuencia: int, contenido: str) -> str:
    return hashlib.sha256(f"{anterior}|{secuencia}|{contenido}".encode()).hexdigest()


async def _ultimo(db: AsyncSession) -> SelloArqueo | None:
    return (await db.execute(select(SelloArqueo).order_by(SelloArqueo.secuencia.desc()).limit(1))).scalars().first()


async def sellar(db: AsyncSession, arqueo: ArqueoCaja) -> SelloArqueo:
    """Agrega el eslabón del arqueo; lo guarda el commit de quien llama. El arqueo ya tiene que estar en la base."""
    ultimo = await _ultimo(db)
    secuencia, anterior = (ultimo.secuencia + 1, ultimo.huella) if ultimo else (1, HUELLA_INICIAL)
    pagos = list((await db.execute(select(Pago).where(Pago.guardia_id == arqueo.guardia_id))).scalars())
    sello = SelloArqueo(
        arqueo_id=arqueo.id,
        secuencia=secuencia,
        huella_anterior=anterior,
        huella=huella_de(anterior, secuencia, contenido_de(arqueo, pagos)),
    )
    db.add(sello)
    return sello


async def _pagos_por_guardia(db: AsyncSession) -> dict[int, list[Pago]]:
    por_guardia: dict[int, list[Pago]] = defaultdict(list)
    for pago in (await db.execute(select(Pago))).scalars():
        por_guardia[pago.guardia_id].append(pago)
    return por_guardia


async def sellar_pendientes(db: AsyncSession) -> int:
    """Sella en orden los arqueos que todavía no tienen huella (el historial de ejemplo). Devuelve cuántos."""
    sellados = set((await db.execute(select(SelloArqueo.arqueo_id))).scalars())
    pendientes = [
        a
        for a in (await db.execute(select(ArqueoCaja).order_by(ArqueoCaja.confirmado_en, ArqueoCaja.id))).scalars()
        if a.id not in sellados
    ]
    if not pendientes:
        return 0
    pagos = await _pagos_por_guardia(db)
    ultimo = await _ultimo(db)
    secuencia, anterior = (ultimo.secuencia, ultimo.huella) if ultimo else (0, HUELLA_INICIAL)
    for arqueo in pendientes:
        secuencia += 1
        huella = huella_de(anterior, secuencia, contenido_de(arqueo, pagos[arqueo.guardia_id]))
        db.add(SelloArqueo(arqueo_id=arqueo.id, secuencia=secuencia, huella_anterior=anterior, huella=huella))
        anterior = huella
    return len(pendientes)


async def verificar_cadena(db: AsyncSession) -> dict:
    """Recalcula todas las huellas y dice cuáles no coinciden, sin confiar en lo guardado."""
    sellos = list((await db.execute(select(SelloArqueo).order_by(SelloArqueo.secuencia))).scalars())
    arqueos = {a.id: a for a in (await db.execute(select(ArqueoCaja))).scalars()}
    pagos = await _pagos_por_guardia(db)
    nombres = dict((await db.execute(select(Operador.id, Operador.nombre_visible))).all())
    alterados = []
    anterior, esperada = HUELLA_INICIAL, 1
    for sello in sellos:
        arqueo = arqueos.get(sello.arqueo_id)
        if sello.secuencia != esperada or sello.huella_anterior != anterior:
            motivo = "La cadena se corta acá: falta un comprobante o se cambió la huella del anterior."
        elif arqueo is None:
            motivo = "El arqueo de este comprobante ya no está."
        elif huella_de(anterior, sello.secuencia, contenido_de(arqueo, pagos[arqueo.guardia_id])) != sello.huella:
            motivo = "Los datos ya no coinciden con su huella: cambió un importe, un cobro o una fecha."
        else:
            motivo = None
        if motivo:
            alterados.append(
                {
                    "secuencia": sello.secuencia,
                    "arqueo_id": sello.arqueo_id,
                    "codigo": codigo_de(sello.huella),
                    "motivo": motivo,
                    "operador_nombre": nombres.get(arqueo.operador_id, "—") if arqueo else "—",
                    "confirmado_en": con_zona(arqueo.confirmado_en).isoformat() if arqueo else None,
                }
            )
        anterior, esperada = sello.huella, sello.secuencia + 1
    sellados = {s.arqueo_id for s in sellos}
    return {
        "total": len(sellos),
        "integros": len(sellos) - len(alterados),
        "alterados": alterados,
        "sin_sello": sum(1 for a in arqueos if a not in sellados),
        "ultimo_codigo": codigo_de(sellos[-1].huella) if sellos else None,
        "verificado_en": datetime.now(UTC).isoformat(),
    }


async def verificar_codigo(db: AsyncSession, texto: str) -> dict:
    """Busca el comprobante por su código (o por la huella entera) y recalcula su huella."""
    codigo = normalizar_codigo(texto)
    if len(codigo) < MINIMO_CODIGO:
        return {
            "encontrado": False,
            "coincide": False,
            "detalle": "El código tiene 16 caracteres, como A1B2-C3D4-E5F6-7890.",
        }
    sellos = list((await db.execute(select(SelloArqueo).where(SelloArqueo.huella.like(f"{codigo}%")))).scalars())
    if len(sellos) != 1:
        return {
            "encontrado": False,
            "coincide": False,
            "detalle": "Ningún comprobante de este motel tiene ese código: el papel no salió de este sistema o se "
            "tipeó mal.",
        }
    sello = sellos[0]
    arqueo = (await db.execute(select(ArqueoCaja).where(ArqueoCaja.id == sello.arqueo_id))).scalars().first()
    if arqueo is None:
        return {"encontrado": True, "coincide": False, "detalle": "El arqueo de este comprobante ya no está."}
    pagos = list((await db.execute(select(Pago).where(Pago.guardia_id == arqueo.guardia_id))).scalars())
    coincide = huella_de(sello.huella_anterior, sello.secuencia, contenido_de(arqueo, pagos)) == sello.huella
    guardia = (await db.execute(select(Guardia).where(Guardia.id == arqueo.guardia_id))).scalars().first()
    operador = (await db.execute(select(Operador).where(Operador.id == arqueo.operador_id))).scalars().first()
    return {
        "encontrado": True,
        "coincide": coincide,
        "detalle": "Coincide: los datos son los mismos que cuando se firmó."
        if coincide
        else "No coincide: los datos cambiaron después de sellarse.",
        "arqueo_id": arqueo.id,
        "secuencia": sello.secuencia,
        "codigo": codigo_de(sello.huella),
        "operador_nombre": operador.nombre_visible if operador else "—",
        "franja": guardia.franja if guardia else None,
        "confirmado_en": con_zona(arqueo.confirmado_en).isoformat(),
        "total_declarado": float(arqueo.total_declarado),
        "diferencia": float(arqueo.diferencia),
        "categoria": arqueo.categoria,
    }
