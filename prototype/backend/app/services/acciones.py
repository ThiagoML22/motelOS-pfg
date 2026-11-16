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

from app.models.cliente_perdido import ESPERA, OTRO, PRECIO, SIN_LUGAR
from app.services import moderacion
from app.services.asistente import normalizar

CANTIDADES = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5}
ORDEN = re.compile(
    r"^(?:(?:por favor|porfa|dale|che|bueno)\s+)*"
    r"(?P<verbo>pasa|pasame|pasala|pasalo|pone|poneme|ponele|ponela|ponelo|deja|dejame|manda|mandame|mandala|mandale"
    r"|libera|liberame|habilita|abri|abrime|ocupa|ocupame"
    r"|carga|cargale|cargame|agrega|agregale|agregame|suma|sumale|sumame|anota|anotame|anotale|registra|escribi"
    r"|cobra|cobrale|cerra|cerrale|traslada|trasladame|muda|mudame|cambia|cambiame)\b(?P<resto>.*)$"
)
HABITACION = r"(?:la |el )?(?:habitacion |hab |n |numero )*(?P<numero>\d{1,4})\b"
DESTINOS = (
    ("Mantenimiento", r"mantenimiento|fuera de servicio", "mantenimiento", "en mantenimiento"),
    ("En Limpieza", r"limpieza|a limpiar", "limpieza", "en limpieza"),
    ("Libre", r"\blibres?\b|disponibles?", "disponible", "disponible"),
)
TRASLADO = re.compile(
    r"(?:la |el |habitacion |hab |n |numero )*(?P<desde>\d{1,4})\b.*?\b(?:a|para)\s+"
    r"(?:la |el |habitacion |hab |n |numero )*(?P<hacia>\d{1,4})\b"
)
# Lo que se cuenta en lugar de ordenar: «la 4 ya está limpia», «se fue un cliente porque no había lugar».
YA_LIMPIA = re.compile(
    r"^(?:ya )?(?:la |el )?(?:habitacion )?(?P<numero>\d{1,4}) (?:ya )?(?:esta|quedo|queda|estan) (?:ya )?"
    r"(?:limpi[ao]|list[ao]|libre|disponible|repasad[ao])\b"
)
SE_FUE = re.compile(
    r"^se (?:me |nos )?(?:fue|fueron|va|acaba de ir) (?:un |una |el |la )?"
    r"(?:cliente|pareja|auto|moto|senor|senora|chico|chica|tipo)"
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


def _a_libre(numero: int, ventanilla) -> Propuesta:
    """«La 4 ya está limpia»: se propone dejarla disponible."""
    habitacion = _buscar_habitacion(ventanilla, numero)
    if habitacion is None:
        return Propuesta(f"No encuentro la habitación {numero}.", "accion:rechazada")
    if habitacion.estado == "Libre":
        return Propuesta(f"La {numero} ya está disponible.", "accion:rechazada")
    if habitacion.estado == "Ocupada":
        return Propuesta(
            f"La {numero} figura ocupada: primero hay que cobrar el turno.",
            "accion:rechazada",
            acciones=_abrir(habitacion.id, numero),
        )
    return _a_confirmar(
        "estado",
        f"Dejar la {numero} disponible",
        f"Listo: la {numero} quedó disponible.",
        habitacion_id=habitacion.id,
        estado="Libre",
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


def _traslado(texto: str, resto: str, ventanilla, tiene_guardia: bool) -> Propuesta | None:
    m = TRASLADO.search(resto)
    if m is None:
        return None
    if not tiene_guardia:
        return Propuesta("Para trasladar un turno hace falta tener la guardia abierta.", "accion:rechazada")
    desde, hacia = int(m.group("desde")), int(m.group("hacia"))
    origen, destino = _buscar_habitacion(ventanilla, desde), _buscar_habitacion(ventanilla, hacia)
    if origen is None or destino is None:
        return Propuesta(f"No encuentro la habitación {desde if origen is None else hacia}.", "accion:rechazada")
    turno = ventanilla.turnos.get(origen.id)
    if turno is None:
        return Propuesta(f"La {desde} no tiene un turno en curso.", "accion:rechazada")
    if destino.estado != "Libre":
        return Propuesta(f"La {hacia} no está disponible: está {destino.estado.lower()}.", "accion:rechazada")
    if re.search(r"\b(falla|rot[ao]|no anda|no funciona|no enfria|no calienta)\b", texto):
        return Propuesta(
            "Si es por una falla, trasladalo desde la habitación: ahí queda el arreglo abierto con lo que falló.",
            "accion:rechazada",
            acciones=_abrir(origen.id, desde),
        )
    return _a_confirmar(
        "traslado",
        f"Trasladar el turno de la {desde} a la {hacia}",
        f"Listo: el turno pasó a la {hacia} y la {desde} quedó en limpieza.",
        detalle="Conserva la hora, la tarifa con la que entró, la cuenta y el QR del cliente.",
        turno_id=str(turno.id),
        habitacion_id=destino.id,
        motivo_traslado="CLIENTE" if re.search(r"\bcliente\b|pidio|quiere", texto) else "OTRO",
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


def _cliente_perdido(texto: str, ventanilla, tiene_guardia: bool, contado: bool = False) -> Propuesta | None:
    if not contado and (
        not re.search(r"\bcliente\b", texto) or not re.search(r"perdid|se fue|se va\b|se fueron", texto)
    ):
        return None
    if not tiene_guardia:
        return Propuesta("Para registrarlo hace falta tener la guardia abierta.", "accion:rechazada")
    motivo, detalle = SIN_LUGAR, None
    if re.search(r"esperar|espera\b", texto):
        motivo = ESPERA
    elif re.search(r"\bcaro\b|precio", texto):
        motivo = PRECIO
    elif re.search(r"(no (habia|hay|tenia|tenemos|teniamos) lugar|sin lugar|lleno|completo)", texto):
        motivo = SIN_LUGAR
    elif m := re.search(r"\b(?:porque|por que|ya que|pq)\b\s+(.+)$", texto):
        # Otro motivo: lo que contó, en pocas palabras y con el mismo filtro que la reseña del cliente.
        escrito = moderacion.limpiar(m.group(1))[:80]
        if moderacion.revisar(escrito):
            return Propuesta(
                "Contalo de otra manera, sin groserías ni datos de la persona, y lo registro.", "accion:rechazada"
            )
        motivo, detalle = OTRO, escrito
    categoria = ventanilla.categoria_mencionada(texto)
    etiquetas = {SIN_LUGAR: "no había lugar", ESPERA: "no quiso esperar", PRECIO: "le pareció caro"}
    busco = f", buscaba {categoria.nombre}" if categoria else ""
    return _a_confirmar(
        "cliente_perdido",
        f"Registrar un cliente que se fue ({etiquetas.get(motivo, detalle)}{busco})",
        "Listo: quedó registrado.",
        motivo=motivo,
        motivo_detalle=detalle,
        categoria_id=categoria.id if categoria else None,
    )


def interpretar(pregunta: str, texto: str, ventanilla, tiene_guardia: bool) -> Propuesta | None:
    """La propuesta de una orden, o None si la frase no es una orden que el asistente sepa cumplir."""
    # «Abrí un turno por error, ¿cómo lo borro?», «se fue un cliente, ¿qué hago?»: empiezan igual que una orden o un
    # aviso, pero piden ayuda.
    if re.search(r"\b(como|por que|por error|se puede|que hago|que tengo que|que hay que)\b|equivoc", texto):
        return None
    if (m := YA_LIMPIA.match(texto)) is not None:
        return _a_libre(int(m.group("numero")), ventanilla)
    if SE_FUE.match(texto) is not None:
        return _cliente_perdido(texto, ventanilla, tiene_guardia, contado=True)
    orden = ORDEN.match(texto)
    if orden is None:
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
    if verbo.startswith(("traslada", "muda", "cambia")) or re.search(r"\bturno\b", resto):
        traslado = _traslado(texto, resto, ventanilla, tiene_guardia)
        if traslado is not None:
            return traslado
    if verbo.startswith(("carga", "agrega", "suma")):
        return _consumo(resto, ventanilla, tiene_guardia)
    # «Ponele una cerveza a la 1» es un consumo; «poné la 3 en mantenimiento», un cambio de estado.
    if verbo.startswith("pone"):
        pedido = re.match(r"\s*(?:le |me )?(?:\d{1,2}|una?|uno|dos|tres|cuatro|cinco)?\s*(.+?)\s+(?:a|en|para) ", resto)
        nombra_articulo = pedido is not None and _articulo(pedido.group(1), ventanilla) is not None
        con_cantidad = re.match(r"\s*(?:le |me )?(?:\d{1,2}|una?|uno|dos|tres|cuatro|cinco)\s+\w", resto) is not None
        if (nombra_articulo or con_cantidad) and pedido and not re.search(r"\b(la|el|habitacion)\b", pedido.group(1)):
            return _consumo(resto, ventanilla, tiene_guardia)
    return (
        _novedad(pregunta, texto, ventanilla)
        or _cliente_perdido(texto, ventanilla, tiene_guardia)
        or _estado(texto, ventanilla)
    )
