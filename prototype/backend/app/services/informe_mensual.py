"""Informe mensual de arqueos en PDF: el resumen del mes y cada guardia con su resultado, para archivo o el contador.

Usa el mismo generador sin dependencias que el comprobante del arqueo (services.pdf). El día de cada fila es el de la
apertura de la guardia, como en el historial de Control de caja.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.establecimiento import Establecimiento
from app.schemas.caja import ArqueoResultado
from app.services import reportes
from app.services.liquidacion import con_zona
from app.services.pdf import ALTO_A4, ANCHO_A4, DocumentoPDF, Pagina

MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
FRANJA = {"06:00": "Mañana", "14:00": "Tarde", "22:00": "Noche"}
MARGEN = 40
FILA = 14
# Columnas: posición x (las de importes, el borde derecho).
COLUMNAS = [
    ("Fecha", 40, False),
    ("Guardia", 105, False),
    ("Conserje", 160, False),
    ("Declarado", 355, True),
    ("Sistema", 420, True),
    ("Diferencia", 485, True),
    ("Resultado", 495, False),
]


def _pesos(valor: float) -> str:
    entero = round(valor)
    texto = f"{abs(entero):,}".replace(",", ".")
    return f"-$ {texto}" if entero < 0 else f"$ {texto}"


def nombre_mes(mes: str) -> str:
    anio, numero = (int(p) for p in mes.split("-"))
    return f"{MESES[numero - 1].capitalize()} {anio}"


def limites(mes: str) -> tuple[date, date]:
    anio, numero = (int(p) for p in mes.split("-"))
    primero = date(anio, numero, 1)
    return primero, date(anio + numero // 12, numero % 12 + 1, 1) - timedelta(days=1)


async def arqueos_del_mes(db: AsyncSession, mes: str, operador_id: int | None) -> tuple[list[ArqueoResultado], object]:
    """Los arqueos de las guardias abiertas en el mes (hora local) y su métrica."""
    zona = ZoneInfo(settings.ZONA_HORARIA)
    desde, hasta = limites(mes)
    candidatos = await reportes.listar_arqueos(
        db, desde - timedelta(days=1), hasta + timedelta(days=1), operador_id, limite=2000
    )
    resultados = [await reportes.resultado_de_arqueo(db, a) for a in candidatos]
    propios = [
        (a, r)
        for a, r in zip(candidatos, resultados, strict=True)
        if desde <= con_zona(r.abierta_en).astimezone(zona).date() <= hasta
    ]
    propios.sort(key=lambda par: con_zona(par[1].abierta_en))
    return [r for _, r in propios], reportes._metrica([a for a, _ in propios])


def _encabezado_tabla(pagina: Pagina, y: float) -> float:
    pagina.rectangulo(MARGEN, y - 4, ANCHO_A4 - 2 * MARGEN, FILA + 2, gris=0.92)
    for titulo, x, derecha in COLUMNAS:
        if derecha:
            pagina.texto_derecha(x, y, titulo, 8.5, negrita=True)
        else:
            pagina.texto(x + 2, y, titulo, 8.5, negrita=True)
    return y - FILA - 4


def informe_pdf(
    mes: str, arqueos: list[ArqueoResultado], metrica, establecimiento: Establecimiento | None, conserje: str | None
) -> bytes:
    zona = ZoneInfo(settings.ZONA_HORARIA)
    documento = DocumentoPDF(f"Arqueos de {nombre_mes(mes)}")
    pagina = documento.nueva_pagina()
    y = ALTO_A4 - 56
    pagina.texto(MARGEN, y, establecimiento.nombre if establecimiento else "MotelOS", 15, negrita=True)
    y -= 20
    pagina.texto(MARGEN, y, f"Informe de arqueos · {nombre_mes(mes)}", 12)
    generado = datetime.now(UTC).astimezone(zona)
    pagina.texto_derecha(ANCHO_A4 - MARGEN, y, f"Generado el {generado:%d/%m/%Y %H:%M}", 8.5)
    y -= 14
    if conserje:
        pagina.texto(MARGEN, y, f"Solo los arqueos de {conserje}", 9)
        y -= 14
    y -= 8

    # Resumen del mes en cinco casillas.
    casillas = [
        ("Arqueos", str(metrica.arqueos)),
        ("Correctos", str(metrica.correctos)),
        ("Faltantes", f"{metrica.faltantes} · {_pesos(metrica.total_faltante)}"),
        ("Sobrantes", f"{metrica.sobrantes} · {_pesos(metrica.total_sobrante)}"),
        ("TDC", f"{metrica.tdc * 100:.1f} %".replace(".", ",")),
    ]
    ancho = (ANCHO_A4 - 2 * MARGEN) / len(casillas)
    for i, (etiqueta, valor) in enumerate(casillas):
        x = MARGEN + i * ancho
        pagina.rectangulo(x, y - 30, ancho - 6, 36)
        pagina.texto(x + 8, y - 6, etiqueta, 8)
        pagina.texto(x + 8, y - 22, valor, 10.5, negrita=True)
    y -= 56

    y = _encabezado_tabla(pagina, y)
    for r in arqueos:
        if y < 60:
            pagina = documento.nueva_pagina()
            y = _encabezado_tabla(pagina, ALTO_A4 - 56)
        apertura = con_zona(r.abierta_en).astimezone(zona)
        celdas = [
            f"{DIAS[apertura.weekday()]} {apertura:%d/%m}",
            FRANJA.get(r.franja, r.franja),
            (r.operador_nombre or "—")[:32],
            _pesos(float(r.total_declarado)),
            _pesos(float(r.total_sistema)),
            _pesos(float(r.diferencia)),
            r.categoria + (" (sup.)" if r.supervisado else ""),
        ]
        for (_, x, derecha), valor in zip(COLUMNAS, celdas, strict=True):
            negrita = derecha and x == 485 and r.diferencia != 0
            if derecha:
                pagina.texto_derecha(x, y, valor, 8.5, negrita=negrita)
            else:
                pagina.texto(x + 2, y, valor, 8.5)
        pagina.linea(MARGEN, y - 4, ANCHO_A4 - MARGEN, y - 4, grosor=0.2)
        y -= FILA
    if not arqueos:
        pagina.texto(MARGEN, y, "Sin arqueos en este mes.", 9)

    total = len(documento.paginas)
    for numero, hoja in enumerate(documento.paginas, start=1):
        hoja.texto(
            MARGEN, 28, "MotelOS · informe generado por el sistema; los arqueos no se modifican (RN-RES-02)", 7.5
        )
        hoja.texto_derecha(ANCHO_A4 - MARGEN, 28, f"Página {numero} de {total}", 7.5)
    return documento.generar()
