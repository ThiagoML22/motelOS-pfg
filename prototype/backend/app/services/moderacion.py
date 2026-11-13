"""Filtro de palabras para lo poco que se escribe a mano (migración 018).

Lo usan la reseña del cliente (hasta seis palabras) y el detalle de «Se fue un cliente → Otro». No deja pasar
palabras groseras, insultos ni datos de contacto (teléfonos, correos, direcciones web): la reseña la lee la gerencia
y no es lugar para eso. Antes de comparar, el texto se lleva a una forma común: minúsculas, sin tildes, con los
números que imitan letras cambiados por la letra (4 → a, 3 → e, 0 → o...), sin signos dentro de la palabra (p.u.t.o)
y con las letras estiradas recortadas (boluuudo). Las palabras cortas se comparan enteras («culo» bloquea «culo», no
«película»); las raíces largas se buscan dentro de la palabra («pelotud» bloquea «re pelotudo» y «pelotudez»).
"""

import re
import unicodedata

MOTIVO_GROSERO = "Sin palabras groseras ni insultos: probá decirlo de otra manera."
MOTIVO_CONTACTO = "Sin teléfonos, correos ni direcciones web."

# Palabras que se bloquean enteras (con plural o femenino a mano: son cortas y aparecen dentro de palabras comunes).
_ENTERAS = """
    puto puta putos putas putita putito gil giles gila orto ortos culo culos ojete forro forros forra forras hdp hdpm
    lpm lptm lpqtp ctm ptm verga vergas pija pijas pete petes petera chota chotas choto trolo trola trolos trava travas
    tarado tarada tarados bobo boba bobos nabo naba nabos zorra zorras perra perras cagon cagona cagones cagada cagadas
    mierda merda porra foda fodase viado shit shitty dick cunt wtf stfu mrd ql culiao chupala chupalo chupame coger
    cogi cogimos cogen cojer coji paja pajas concha conchas marica maricon maricones sidoso sidosa chorro chorros
    chorra chorras basura basuras rata ratas
"""
# Raíces que se buscan dentro de cada palabra: largas y sin otro sentido.
_RAICES = """
    pelotud bolud mierd pajer conchud imbecil idiot estupid pendej cabron carajo culiad culead hijodeput hijadeput
    hijaput hijueput malparid mogolic mongolic sorete garch caralh asshol motherf bitch fuck ladron porquer estaf
    gonorrea
"""

_LETRAS_IMITADAS = str.maketrans(
    {"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t"}
)
# Sin «.me» ni «.ly»: «bien.me gustó» es un punto sin espacio, no una dirección.
_URL = re.compile(r"https?://|www\.|\b[\w-]+\.(com|net|org|ar|py|br|io)\b", re.IGNORECASE)
_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.\w+|(^|\s)@\w+")
# Siete cifras o más, aunque vengan separadas por espacios, puntos o guiones: un teléfono.
_TELEFONO = re.compile(r"\d(?:[\s.\-]*\d){6,}")


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _colapsar(palabra: str, hasta: int = 1) -> str:
    """Recorta las letras repetidas: con hasta=1, «boluuudo» → «boludo»; con hasta=2, «perrrra» → «perra»."""
    return re.sub(rf"(.)\1{{{hasta},}}", lambda m: m.group(1) * hasta, palabra)


def _formas(palabra: str) -> set[str]:
    return {palabra, _colapsar(palabra, 1), _colapsar(palabra, 2)}


def _palabras(texto: str) -> list[str]:
    """Las palabras del texto en la forma común. Las letras sueltas seguidas se juntan: «p u t o» → «puto»."""
    crudas = _sin_tildes(texto.lower().translate(_LETRAS_IMITADAS)).split()
    limpias = [re.sub(r"[^a-z]", "", p) for p in crudas]
    resultado: list[str] = []
    sueltas = ""
    for palabra in limpias:
        if len(palabra) == 1:
            sueltas += palabra
            continue
        if len(sueltas) > 1:
            resultado.append(sueltas)
        sueltas = ""
        if palabra:
            resultado.append(palabra)
    if len(sueltas) > 1:
        resultado.append(sueltas)
    return resultado


ENTERAS = frozenset(_ENTERAS.split())
RAICES = tuple(_RAICES.split())


def es_grosero(texto: str) -> bool:
    for palabra in _palabras(texto):
        for forma in _formas(palabra):
            if forma in ENTERAS or any(raiz in forma for raiz in RAICES):
                return True
    return False


def tiene_contacto(texto: str) -> bool:
    return bool(_URL.search(texto) or _CORREO.search(texto) or _TELEFONO.search(texto))


def limpiar(texto: str) -> str:
    """Un solo espacio entre palabras y nada en los bordes."""
    return " ".join(texto.split())


def contar_palabras(texto: str) -> int:
    return len(limpiar(texto).split()) if texto.strip() else 0


def revisar(texto: str) -> str | None:
    """Por qué no se puede publicar el texto, o None si está bien."""
    if tiene_contacto(texto):
        return MOTIVO_CONTACTO
    if es_grosero(texto):
        return MOTIVO_GROSERO
    return None


__all__ = ["MOTIVO_CONTACTO", "MOTIVO_GROSERO", "contar_palabras", "es_grosero", "limpiar", "revisar", "tiene_contacto"]
