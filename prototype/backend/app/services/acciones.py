"""El asistente que actúa: entiende una orden y la deja lista para confirmar.

Nunca ejecuta nada por su cuenta. De «pasá la 7 a mantenimiento» arma una propuesta; quien atiende la confirma y recién
ahí la interfaz llama a los mismos servicios que usan los botones, con las mismas reglas, la misma guardia y a nombre de
la misma persona. Lo que se puede saber de antemano (la habitación no existe, está ocupada, no hay stock) se responde
acá, sin proponer algo que después va a fallar.

Solo son órdenes las frases que empiezan con el verbo: «¿cómo paso una habitación a mantenimiento?» sigue siendo una
pregunta. El cobro queda afuera a propósito: necesita el medio de pago y el monto, y se hace en la habitación.
"""

import re
from dataclasses import dataclass, field

from app.models.cliente_perdido import ESPERA, PRECIO, SIN_LUGAR
from app.services.asistente import normalizar

CANTIDADES = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}
ORDEN = re.compile(
    r"^(?:(?:por favor|porfa|dale|che|bueno)\s+)*"
    r"(?P<verbo>pasa|pasame|pone|poneme|deja|dejame|manda|libera|liberame|habilita|abri|abrime|ocupa|ocupame"
    r"|carga|cargale|cargame|agrega|agregale|agregame|suma|sumale|sumame|anota|anotame|anotale|registra|escribi"
    r"|cobra|cobrale|cerra|cerrale)\b(?P<resto>.*)$"
)
HABITACION = r"(?:la |el )?(?:habitacion |hab |n |numero )*(?P<numero>\d{1,4})\b"
DESTINOS = (
    ("Mantenimiento", r"mantenimiento|fuera de servicio", "mantenimiento", "en mantenimiento"),
    ("En Limpieza", r"limpieza|a limpiar", "limpieza", "en limpieza"),
    ("Libre", r"\blibres?\b|disponibles?", "disponible", "disponible"),
)
PATENTE = re.compile(r"\b([a-z]{2} ?\d{3} ?[a-z]{2}|[a-z]{3} ?\d{3})\b")


@dataclass
class Propuesta:
    texto: str
    intencion: str
    confirmacion: dict | None = None
    acciones: list[dict] = field(default_factory=list)
    detalle: str | None = None


def _abrir(habitacion_id: int, numero: int) -> list[dict]:
    return [{"etiqueta": f"Abrir la {numero}", "vista": "dashboard", "habitacion_id": habitacion_id}]


def _a_confirmar(tipo: str, titulo: str, hecho: str, detalle: str | None = None, **datos) -> Propuesta:
    return Propuesta(
        "Esto es lo que voy a hacer. ¿Lo confirmás?",
        f"accion:{tipo}",
        confirmacion={"tipo": tipo, "titulo": titulo, "hecho": hecho, **datos},
        detalle=detalle,
    )


def _buscar_habitacion(ventanilla, numero: int):
    return next((h for h in ventanilla.habitaciones if h.numero == numero), None)


def _estado(texto: str, ventanilla) -> Propuesta | None:
    verbo = ORDEN.match(texto).group("verbo")
    m = re.search(HABITACION, ORDEN.match(texto).group("resto"))
    if m is None:
        return None
    destino = next(((d, a, e) for d, patron, a, e in DESTINOS if re.search(patron, texto)), None)
    if destino is None and verbo in ("libera", "liberame", "habilita"):
        destino = ("Libre", "disponible", "disponible")
    if destino is None:
        return None
    numero = int(m.group("numero"))
    habitacion = _buscar_habitacion(ventanilla, numero)
    if habitacion is None:
        return Propuesta(f"No encuentro la habitación {numero}.", "accion:rechazada")
    estado, a_donde, etiqueta = destino
    if habitacion.estado == estado:
        return Propuesta(f"La {numero} ya está {etiqueta}.", "accion:rechazada")
    if habitacion.estado == "Ocupada":
        return Propuesta(
            f"La {numero} está ocupada: primero hay que cobrar el turno.",
            "accion:rechazada",
            acciones=_abrir(habitacion.id, numero),
        )
    return _a_confirmar(
        "estado",
        f"Pasar la {numero} a {a_donde}",
        f"Listo: la {numero} quedó {etiqueta}.",
        habitacion_id=habitacion.id,
        estado=estado,
    )


def _abrir_turno(texto: str, resto: str, ventanilla, tiene_guardia: bool) -> Propuesta | None:
    m = re.search(HABITACION, resto)
    categoria = ventanilla.categoria_mencionada(texto)
    pide_alguna = re.search(r"\buna? (habitacion|turno)\b", resto) is not None
    if m is None and categoria is None and not pide_alguna:
        return None
    if not tiene_guardia:
        return Propuesta("Para abrir un turno hace falta tener la guardia abierta.", "accion:rechazada")
    if m is not None:
        numero = int(m.group("numero"))
        habitacion = _buscar_habitacion(ventanilla, numero)
        if habitacion is None:
            return Propuesta(f"No encuentro la habitación {numero}.", "accion:rechazada")
        if habitacion.estado != "Libre":
            return Propuesta(
                f"La {numero} no está disponible: está {habitacion.estado.lower()}.",
                "accion:rechazada",
                acciones=_abrir(habitacion.id, numero),
            )
    else:
        libres = [
            h
            for h in ventanilla.habitaciones
            if h.estado == "Libre" and (categoria is None or h.categoria_id == categoria.id)
        ]
        if not libres:
            nombre = f" {categoria.nombre}" if categoria else ""
            return Propuesta(f"No hay ninguna{nombre} disponible.", "accion:rechazada")
        habitacion = libres[0]
    tipo_cliente = "Moto" if re.search(r"\bmoto\b", texto) else "Auto"
    if re.search(r"\bpeaton\b|a pie|caminando", texto):
        tipo_cliente = "Peaton"
    encontrada = PATENTE.search(texto) if tipo_cliente != "Peaton" else None
    patente = encontrada.group(1).replace(" ", "").upper() if encontrada else None
    vigente = ventanilla.vigentes.get(habitacion.categoria_id)
    nombre = ventanilla.nombre_categoria(habitacion)
    etiqueta = f"{nombre} · {vigente.franja.nombre}" if vigente and vigente.franja else nombre
    partes = [p for p in (nombre, "Peatón" if tipo_cliente == "Peaton" else tipo_cliente, patente) if p]
    return _a_confirmar(
        "abrir_turno",
        f"Abrir la {habitacion.numero} ({' · '.join(partes)})",
        f"Listo: la {habitacion.numero} quedó ocupada.",
        detalle=(
            f"Tarifa de {etiqueta}: ${float(vigente.tarifa.tarifa_base):,.0f}.".replace(",", ".") if vigente else None
        ),
        habitacion_id=habitacion.id,
        tipo_cliente=tipo_cliente,
        patente=patente,
        # Lo que se le dijo al cliente es lo que se cobra: si cambió antes de confirmar, no abre.
        tarifa_id=vigente.tarifa.id if vigente else None,
    )


def _articulo(descripcion: str, ventanilla):
    """El artículo cuya descripción más se parece a lo pedido, sin importar el plural."""
    pedidas = {p[:-1] if p.endswith("s") else p for p in descripcion.split() if len(p) > 2}
    mejores = []
    for articulo in ventanilla.articulos:
        propias = {p[:-1] if p.endswith("s") else p for p in normalizar(articulo.descripcion).split()}
        coincidencias = len(pedidas & propias)
        if coincidencias:
            mejores.append((coincidencias, -len(propias), articulo.id, articulo))
    return max(mejores)[3] if mejores else None


def _consumo(resto: str, ventanilla, tiene_guardia: bool) -> Propuesta | None:
    m = re.match(
        r"\s*(?:le |me )?(?P<cantidad>\d{1,2}|una?|uno|dos|tres|cuatro|cinco)?\s*(?P<articulo>.+?)"
        r"\s+(?:a|en|para|de)\s+" + HABITACION,
        resto,
    )
    if m is None:
        return None
    articulo = _articulo(m.group("articulo"), ventanilla)
    numero = int(m.group("numero"))
    habitacion = _buscar_habitacion(ventanilla, numero)
    if habitacion is None:
        return Propuesta(f"No encuentro la habitación {numero}.", "accion:rechazada")
    if articulo is None:
        return Propuesta(f"No encuentro «{m.group('articulo')}» en el inventario.", "accion:rechazada")
    turno = ventanilla.turnos.get(habitacion.id)
    if turno is None:
        return Propuesta(f"La {numero} no tiene un turno en curso.", "accion:rechazada")
    if not tiene_guardia:
        return Propuesta("Para cargar un consumo hace falta tener la guardia abierta.", "accion:rechazada")
    texto_cantidad = m.group("cantidad") or "1"
    cantidad = CANTIDADES.get(texto_cantidad) or int(texto_cantidad)
    if articulo.stock_actual < cantidad:
        return Propuesta(f"Quedan {articulo.stock_actual} de «{articulo.descripcion}».", "accion:rechazada")
    subtotal = float(articulo.precio_unitario) * cantidad
    return _a_confirmar(
        "consumo",
        f"Cargar {cantidad} × {articulo.descripcion} a la {numero}",
        f"Listo: se cargó a la cuenta de la {numero}.",
        detalle=f"Suma ${subtotal:,.0f} a la cuenta.".replace(",", "."),
        turno_id=str(turno.id),
        articulo_id=articulo.id,
        cantidad=cantidad,
    )


def _novedad(pregunta: str, texto: str, ventanilla) -> Propuesta | None:
    if not re.search(r"\b(novedad|nota)\b", texto):
        return None
    m = re.search(r"(?:novedad|nota)(?: importante)?\s*(?:que\b)?\s*[:,.\-–]?\s*(.*)$", pregunta, re.I | re.S)
    escrito = m.group(1).strip() if m else ""
    if len(escrito) < 3:
        return Propuesta(
            "Decime qué querés dejar escrito: «dejá una novedad: falta papel en la 2».", "accion:rechazada"
        )
    numero = re.search(r"\b(?:la|el|habitaci[oó]n|hab\.?) ?(\d{1,4})\b", escrito, re.I)
    habitacion = _buscar_habitacion(ventanilla, int(numero.group(1))) if numero else None
    return _a_confirmar(
        "novedad",
        f"Dejar una novedad: «{escrito[:120]}»",
        "Listo: la novedad quedó a tu nombre.",
        texto=escrito[:500],
        importante=re.search(r"importante|urgente", texto) is not None,
        habitacion_id=habitacion.id if habitacion else None,
    )


def _cliente_perdido(texto: str, ventanilla, tiene_guardia: bool) -> Propuesta | None:
    if not re.search(r"\bcliente\b", texto) or not re.search(r"perdid|se fue|se va\b|se fueron", texto):
        return None
    if not tiene_guardia:
        return Propuesta("Para registrarlo hace falta tener la guardia abierta.", "accion:rechazada")
    motivo = SIN_LUGAR
    if re.search(r"esperar|espera\b", texto):
        motivo = ESPERA
    elif re.search(r"\bcaro\b|precio", texto):
        motivo = PRECIO
    categoria = ventanilla.categoria_mencionada(texto)
    etiquetas = {SIN_LUGAR: "no había lugar", ESPERA: "no quiso esperar", PRECIO: "le pareció caro"}
    busco = f", buscaba {categoria.nombre}" if categoria else ""
    return _a_confirmar(
        "cliente_perdido",
        f"Registrar un cliente que se fue ({etiquetas[motivo]}{busco})",
        "Listo: quedó registrado.",
        motivo=motivo,
        categoria_id=categoria.id if categoria else None,
    )


def interpretar(pregunta: str, texto: str, ventanilla, tiene_guardia: bool) -> Propuesta | None:
    """La propuesta de una orden, o None si la frase no es una orden que el asistente sepa cumplir."""
    orden = ORDEN.match(texto)
    # «Abrí un turno por error, ¿cómo lo borro?»: empieza igual que una orden, pero cuenta algo que ya pasó.
    if orden is None or re.search(r"\b(como|por que|por error|se puede)\b|equivoc", texto):
        return None
    verbo, resto = orden.group("verbo"), orden.group("resto")
    if verbo.startswith(("cobra", "cerra")):
        m = re.search(HABITACION, resto)
        habitacion = _buscar_habitacion(ventanilla, int(m.group("numero"))) if m else None
        return Propuesta(
            "El cobro no lo hago yo: necesita el medio de pago y se confirma en la habitación.",
            "accion:rechazada",
            acciones=_abrir(habitacion.id, habitacion.numero) if habitacion else [],
        )
    if verbo in ("abri", "abrime", "ocupa", "ocupame"):
        return _abrir_turno(texto, resto, ventanilla, tiene_guardia)
    if verbo.startswith(("carga", "agrega", "suma")):
        return _consumo(resto, ventanilla, tiene_guardia)
    return (
        _novedad(pregunta, texto, ventanilla)
        or _cliente_perdido(texto, ventanilla, tiene_guardia)
        or _estado(texto, ventanilla)
    )
