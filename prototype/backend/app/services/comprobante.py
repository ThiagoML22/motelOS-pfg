"""Comprobante del arqueo en PDF (RF-10).

Una hoja A4 con los datos del establecimiento, la guardia, el recuento declarado frente al del sistema por medio de
pago, la diferencia clasificada (RN-DER-03), los cobros imputados a la guardia y los espacios para las firmas. Se
genera a pedido desde el arqueo guardado, que no cambia (RN-RES-02): dos descargas del mismo arqueo dicen lo mismo.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.models.establecimiento import Establecimiento
from app.schemas.caja import ArqueoDetalle
from app.services.actividad import pesos
from app.services.pdf import ALTO_A4, ANCHO_A4, DocumentoPDF, Pagina

MARGEN = 50
DERECHA = ANCHO_A4 - MARGEN
MEDIOS = {"EFECTIVO": "Efectivo", "POSNET": "POSNET", "MERCADO_PAGO": "Mercado Pago"}


def _local(momento: datetime | None) -> str:
    if momento is None:
        return "—"
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(ZoneInfo(settings.ZONA_HORARIA)).strftime("%d/%m/%Y %H:%M")


def _con_signo(monto: float) -> str:
    return ("+ " if monto > 0 else "- " if monto < 0 else "") + pesos(abs(monto))


def comprobante_arqueo(arqueo: ArqueoDetalle, establecimiento: Establecimiento) -> bytes:
    documento = DocumentoPDF(f"Comprobante de arqueo N.º {arqueo.id}")
    hoja = documento.nueva_pagina()
    y = ALTO_A4 - MARGEN

    # Encabezado: el establecimiento y el número de comprobante.
    hoja.texto(MARGEN, y - 4, establecimiento.nombre, 16, negrita=True)
    hoja.texto_derecha(DERECHA, y - 4, f"Arqueo N.º {arqueo.id}", 12, negrita=True)
    y -= 20
    contacto = " · ".join(x for x in (establecimiento.domicilio, establecimiento.telefono) if x)
    if contacto:
        hoja.texto(MARGEN, y, contacto, 9)
    hoja.texto_derecha(DERECHA, y, f"Guardia N.º {arqueo.guardia_id}", 9)
    y -= 14
    hoja.linea(MARGEN, y, DERECHA, y, 1.2)
    y -= 26
    hoja.texto(MARGEN, y, "Comprobante de arqueo de caja", 14, negrita=True)
    y -= 26

    # Datos de la guardia.
    filas = [
        ("Conserje", arqueo.operador_nombre),
        ("Franja", f"Guardia de las {arqueo.franja}"),
        ("Apertura", _local(arqueo.abierta_en)),
        ("Cierre", _local(arqueo.cerrada_en)),
        ("Arqueo confirmado", _local(arqueo.confirmado_en)),
    ]
    if arqueo.supervisado:
        filas.append(("Confirmado por", f"{arqueo.confirmado_por_nombre} (cierre supervisado)"))
    for etiqueta, valor in filas:
        hoja.texto(MARGEN, y, etiqueta, 10, negrita=True)
        hoja.texto(MARGEN + 130, y, valor, 10)
        y -= 16
    if arqueo.supervisado and arqueo.observacion:
        hoja.texto(MARGEN, y, "Observación", 10, negrita=True)
        y = _parrafo(hoja, MARGEN + 130, y, arqueo.observacion, 10, 60) - 4

    # Recuento: declarado frente al sistema, por medio de pago.
    y -= 12
    columnas = (MARGEN + 230, MARGEN + 345, DERECHA - 8)
    hoja.rectangulo(MARGEN, y - 6, DERECHA - MARGEN, 20, gris=0.9)
    hoja.texto(MARGEN + 8, y, "Medio", 10, negrita=True)
    for x, titulo in zip(columnas, ("Declarado", "Sistema", "Diferencia"), strict=True):
        hoja.texto_derecha(x, y, titulo, 10, negrita=True)
    y -= 22
    renglones = [
        ("Efectivo (incluye el fondo)", arqueo.declarado_efectivo, arqueo.sistema_efectivo),
        ("POSNET", arqueo.declarado_posnet, arqueo.sistema_posnet),
        ("Mercado Pago", arqueo.declarado_mercado_pago, arqueo.sistema_mercado_pago),
    ]
    for etiqueta, declarado, sistema in renglones:
        hoja.texto(MARGEN + 8, y, etiqueta, 10)
        hoja.texto_derecha(columnas[0], y, pesos(declarado), 10)
        hoja.texto_derecha(columnas[1], y, pesos(sistema), 10)
        hoja.texto_derecha(columnas[2], y, _con_signo(declarado - sistema), 10)
        y -= 18
    hoja.linea(MARGEN, y + 10, DERECHA, y + 10)
    hoja.texto(MARGEN + 8, y - 2, "Total", 11, negrita=True)
    hoja.texto_derecha(columnas[0], y - 2, pesos(arqueo.total_declarado), 11, negrita=True)
    hoja.texto_derecha(columnas[1], y - 2, pesos(arqueo.total_sistema), 11, negrita=True)
    hoja.texto_derecha(columnas[2], y - 2, _con_signo(arqueo.diferencia), 11, negrita=True)
    y -= 22
    hoja.texto(MARGEN + 8, y, f"Fondo de cambio recibido al abrir la guardia: {pesos(arqueo.fondo_inicial)}", 9)
    y -= 28

    # Resultado (RN-DER-03).
    hoja.rectangulo(MARGEN, y - 10, DERECHA - MARGEN, 30)
    hoja.texto(MARGEN + 10, y, "Resultado", 11, negrita=True)
    resultado = arqueo.categoria if arqueo.diferencia == 0 else f"{arqueo.categoria} de {pesos(abs(arqueo.diferencia))}"
    hoja.texto_derecha(DERECHA - 10, y, resultado, 13, negrita=True)
    y -= 44

    # Cobros imputados a la guardia (RN-DER-04).
    hoja.texto(MARGEN, y, f"Cobros de la guardia ({len(arqueo.pagos)})", 11, negrita=True)
    y -= 18
    if not arqueo.pagos:
        hoja.texto(MARGEN + 8, y, "La guardia no registró cobros.", 9)
        y -= 14
    for pago in arqueo.pagos:
        if y < 170:
            hoja.texto(MARGEN + 8, y, "(continúa en el panel de la gerencia)", 9)
            y -= 14
            break
        hoja.texto(MARGEN + 8, y, _local(pago.registrado_en), 9)
        hoja.texto(MARGEN + 110, y, f"Habitación {pago.habitacion_numero}", 9)
        medio = MEDIOS.get(pago.medio_pago, pago.medio_pago)
        if pago.comprobante_referencia:
            medio += f" · {pago.comprobante_referencia}"
        hoja.texto(MARGEN + 200, y, medio[:40], 9)
        hoja.texto_derecha(DERECHA - 8, y, pesos(pago.monto), 9)
        y -= 13

    # Firmas y pie.
    y_firmas = 120
    for x, quien in ((MARGEN, "Conserje"), (ANCHO_A4 / 2 + 20, "Gerencia")):
        hoja.linea(x, y_firmas, x + 200, y_firmas)
        hoja.texto(x, y_firmas - 14, f"Firma y aclaración · {quien}", 9)
    if establecimiento.leyenda_comprobante:
        _parrafo(hoja, MARGEN, 70, establecimiento.leyenda_comprobante, 8, 110)
    generado = _local(datetime.now(UTC))
    hoja.texto(MARGEN, 40, f"Generado por MotelOS el {generado}. El arqueo confirmado no se modifica.", 7)
    return documento.generar()


def _parrafo(hoja: Pagina, x: float, y: float, texto: str, tamano: float, caracteres: int) -> float:
    """Escribe el texto en renglones de hasta `caracteres` y devuelve la altura del renglón siguiente."""
    renglon = ""
    for palabra in texto.split():
        if renglon and len(renglon) + 1 + len(palabra) > caracteres:
            hoja.texto(x, y, renglon, tamano)
            y -= tamano + 4
            renglon = palabra
        else:
            renglon = f"{renglon} {palabra}".strip()
    if renglon:
        hoja.texto(x, y, renglon, tamano)
        y -= tamano + 4
    return y
