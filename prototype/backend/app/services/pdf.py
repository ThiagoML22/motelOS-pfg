"""Generador mínimo de PDF (RF-10), sin dependencias externas.

Alcanza para un comprobante: texto en Helvetica (normal y negrita), líneas y rectángulos, en hojas A4. El texto se
codifica en Windows-1252 (WinAnsiEncoding), que cubre las letras del castellano (á, é, ñ, ü) y el signo $.
Se eligió escribirlo en lugar de sumar una biblioteca (reportlab): son unas 100 líneas que se pueden explicar
completas, y no agregan una dependencia más que auditar (pip-audit en el canal).
"""

from dataclasses import dataclass, field

ANCHO_A4 = 595.28
ALTO_A4 = 841.89
_FUENTES = {False: "F1", True: "F2"}  # F1 Helvetica, F2 Helvetica-Bold

# Ancho aproximado de los caracteres de Helvetica en milésimas del cuerpo, para alinear importes a la derecha.
_ANCHO_DIGITO = 556
_ANCHOS = {" ": 278, ".": 278, ",": 278, "-": 333, "$": 556, ":": 278, "(": 333, ")": 333, "/": 278}


def ancho_texto(texto: str, tamano: float, negrita: bool = False) -> float:
    base = sum(_ANCHOS.get(c, _ANCHO_DIGITO if c.isdigit() else (610 if c.isupper() else 520)) for c in texto)
    return base * tamano / 1000 * (1.05 if negrita else 1)


def _escapar(texto: str) -> bytes:
    crudo = texto.encode("cp1252", errors="replace")
    return crudo.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


@dataclass
class Pagina:
    operaciones: list[bytes] = field(default_factory=list)

    def texto(self, x: float, y: float, texto: str, tamano: float = 10, negrita: bool = False) -> None:
        self.operaciones.append(
            b"BT /%s %.1f Tf %.2f %.2f Td (" % (_FUENTES[negrita].encode(), tamano, x, y) + _escapar(texto) + b") Tj ET"
        )

    def texto_derecha(self, x_derecho: float, y: float, texto: str, tamano: float = 10, negrita: bool = False) -> None:
        self.texto(x_derecho - ancho_texto(texto, tamano, negrita), y, texto, tamano, negrita)

    def linea(self, x1: float, y1: float, x2: float, y2: float, grosor: float = 0.6) -> None:
        self.operaciones.append(b"%.2f w %.2f %.2f m %.2f %.2f l S" % (grosor, x1, y1, x2, y2))

    def rectangulo(self, x: float, y: float, ancho: float, alto: float, gris: float | None = None) -> None:
        """Rectángulo con borde; con `gris` (0 negro, 1 blanco) se rellena."""
        if gris is None:
            self.operaciones.append(b"0.6 w %.2f %.2f %.2f %.2f re S" % (x, y, ancho, alto))
        else:
            self.operaciones.append(b"q %.2f g %.2f %.2f %.2f %.2f re f Q" % (gris, x, y, ancho, alto))


class DocumentoPDF:
    def __init__(self, titulo: str):
        self.titulo = titulo
        self.paginas: list[Pagina] = []

    def nueva_pagina(self) -> Pagina:
        pagina = Pagina()
        self.paginas.append(pagina)
        return pagina

    def generar(self) -> bytes:
        objetos: list[bytes] = []

        def agregar(contenido: bytes) -> int:
            objetos.append(contenido)
            return len(objetos)

        catalogo = agregar(b"")  # se completa al final, cuando se conoce el número del árbol de páginas
        paginas_id = agregar(b"")
        f1 = agregar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = agregar(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        hijos = []
        for pagina in self.paginas:
            flujo = b"\n".join(pagina.operaciones)
            contenido = agregar(b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream")
            hijos.append(
                agregar(
                    b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] "
                    b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> /Contents %d 0 R >>"
                    % (paginas_id, ANCHO_A4, ALTO_A4, f1, f2, contenido)
                )
            )
        objetos[catalogo - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % paginas_id
        objetos[paginas_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
            b" ".join(b"%d 0 R" % h for h in hijos),
            len(hijos),
        )
        info = agregar(b"<< /Title (" + _escapar(self.titulo) + b") /Producer (MotelOS) >>")

        salida = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        posiciones = []
        for numero, contenido in enumerate(objetos, start=1):
            posiciones.append(len(salida))
            salida += b"%d 0 obj\n" % numero + contenido + b"\nendobj\n"
        inicio_xref = len(salida)
        salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
        for posicion in posiciones:
            salida += b"%010d 00000 n \n" % posicion
        salida += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objetos) + 1,
            catalogo,
            info,
            inicio_xref,
        )
        return bytes(salida)
