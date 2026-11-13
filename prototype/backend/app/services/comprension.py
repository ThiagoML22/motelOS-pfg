"""Comprensión del lenguaje de Mot: lo que se escribe «como se habla», llevado a una forma que las reglas entienden.

Todo es local, sin servicios externos ni modelos descargados. Tres piezas:

- **preparar**: saca muletillas y pedidos de cortesía («che», «decime», «quería saber si»), saludos delante de la
  pregunta («hola mot, ¿cuánto…?»), letras estiradas («holaaa»), abreviaturas del chat («q», «xq», «tmb»), lunfardo
  («guita», «mangos», «birra») y pasa a cifras los números escritos con letras cuando nombran una habitación («la
  siete» → «la 7»).
- **dividir**: separa dos preguntas escritas juntas («¿cuánto facturamos ayer y cuántos turnos hubo?»).
- **clasificar**: cuando ninguna regla reconoce la pregunta, la compara con frases de ejemplo de cada intención
  (palabras en común pesadas por lo raras que son, más parecido por trozos de letras para los errores de tipeo) y
  devuelve las más parecidas con su puntaje. Con un puntaje alto se responde; con uno dudoso, Mot pregunta.
"""

import math
import re
from collections import Counter
from functools import lru_cache

# --- Preparar -------------------------------------------------------------------------------------------------------

NUMEROS = {
    "uno": 1,
    "una": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintidos": 22,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "treinta": 30,
}
# Un número en letras es una habitación cuando va después de estas palabras: «la siete», «la habitación doce».
_NUMERO_DE_HABITACION = re.compile(
    r"\b(la|el|a la|en la|de la|habitacion|habitaciones|pieza|cuarto|hab|numero|nro)\s+(" + "|".join(NUMEROS) + r")\b"
)
# «la una» también es una hora («a la una»): igual da 1, que es lo que se quiere decir en los dos casos.

# Palabras del chat y del habla de todos los días, a su forma completa.
ABREVIATURAS = {
    "q": "que",
    "k": "que",
    "xq": "porque",
    "pq": "porque",
    "porq": "porque",
    "x": "por",
    "tmb": "tambien",
    "tb": "tambien",
    "tbn": "tambien",
    "d": "de",
    "toy": "estoy",
    "ta": "esta",
    "tas": "estas",
    "bn": "bien",
    "hs": "horas",
    "hrs": "horas",
    "nro": "numero",
    "cant": "cantidad",
    "xfa": "por favor",
    "plis": "por favor",
    "pls": "por favor",
    "gral": "general",
    "aprox": "aproximadamente",
    "vs": "contra",
    "versus": "contra",
}
LUNFARDO = {
    "guita": "plata",
    "mangos": "plata",
    "mango": "plata",
    "lucas": "mil pesos",
    "luca": "mil pesos",
    "moneda": "plata",
    "biyuya": "plata",
    "tarasca": "plata",
    "dinero": "plata",
    "laburo": "trabajo",
    "laburar": "trabajar",
    "laburando": "trabajando",
    "birra": "cerveza",
    "birras": "cervezas",
    "chela": "cerveza",
    "chelas": "cervezas",
    "coca": "gaseosa cola",
    "cocacola": "gaseosa cola",
    "gaseosas": "gaseosa",
    "forros": "preservativos",
    "condones": "preservativos",
    "condon": "preservativo",
    "telo": "motel",
    "albergue": "motel",
    "finde": "fin de semana",
    "findes": "fines de semana",
}

# Muletillas y cortesías al principio: no cambian lo que se pregunta.
_MULETILLAS = re.compile(
    r"^(?:che|eh|ey|mot|bueno|mira|oime|oye|escucha|a ver|una pregunta|una consulta"
    r"|te (?:hago una )?(?:pregunta|consulta)"
    r"|te pregunto|te consulto|disculpa(?:me)?|perdon|por favor|porfa|ok|okey|y bueno|ahora|entonces|otra cosa"
    r"|otra pregunta)\b[\s,]*"
)
_PEDIDOS = re.compile(
    r"^(?:me (?:podes|podrias|puedes|podria|queres) (?:decir|contar|pasar|mostrar|averiguar|fijar|explicar)"
    r"|(?:podes|podrias|puedes|podria) (?:decirme|contarme|pasarme|mostrarme|averiguar(?:me)?|fijarte|explicarme)"
    r"|decime|dime|contame|cuentame|me (?:decis|contas|pasas|mostras|das)|(?:yo )?(?:queria|quisiera|quiero|necesito"
    r"|me gustaria|necesitaria) (?:saber|ver|consultar|preguntar(?:te)?|averiguar)|sabes|tenes idea(?: de)?"
    r"|fijate|averigua(?:me)?|tirame)\b[\s,]*(?:si |que |de )?"
)
_AL_FINAL = re.compile(r"[\s,]+(?:por favor|porfa|gracias|che|dale)$")
# «gracias capo», «decime, genio»: el apodo al final se saca, salvo que sea lo que se dice («sos un genio»).
_APODO = re.compile(
    r"(?<!\bun)(?<!\buna)(?<!\bsos)(?<!\bes)(?<!\bre)(?<!\bmuy)[\s,]+"
    r"(?:capo|genio|amigo|mostro|crack|maestro|idolo|groso)$"
)
# Un saludo delante de la pregunta: «hola mot, ¿cuánto facturamos?». Si después no hay nada, era solo el saludo.
SALUDO_DELANTE = re.compile(r"^(?:hola|holis|buen(?:os|as)?"
r" (?:dia|dias|tarde|tardes|noche|noches)|buenas)\b[\s,]*(?:mot\b)?[\s,]*")


def _colapsar(texto: str) -> str:
    """«holaaaa» → «hola», «siiii» → «si». Dos letras iguales quedan (llave, carro)."""
    return re.sub(r"([a-z])\1{2,}", r"\1", texto)


def _palabras_a_forma(texto: str) -> str:
    salida = []
    for palabra in texto.split():
        salida.append(ABREVIATURAS.get(palabra) or LUNFARDO.get(palabra) or palabra)
    return " ".join(salida)


def _numeros(texto: str) -> str:
    return _NUMERO_DE_HABITACION.sub(lambda m: f"{m.group(1)} {NUMEROS[m.group(2)]}", texto)


def sin_muletillas(texto: str) -> str:
    anterior = None
    while anterior != texto:
        anterior = texto
        texto = _MULETILLAS.sub("", texto)
        texto = _PEDIDOS.sub("", texto)
        texto = _AL_FINAL.sub("", texto)
        texto = _APODO.sub("", texto) if len(texto.split()) > 2 else texto
    return texto.strip()


def preparar(texto: str) -> str:
    """El texto ya normalizado (minúsculas, sin tildes ni signos) en la forma que entienden las reglas."""
    texto = _colapsar(texto)
    texto = _palabras_a_forma(texto)
    texto = _numeros(texto)
    return sin_muletillas(texto)


def quitar_saludo(texto: str) -> tuple[str, bool]:
    """(lo que queda después del saludo, si había un saludo)."""
    resto = SALUDO_DELANTE.sub("", texto, count=1)
    return sin_muletillas(resto), resto != texto


# --- Dividir --------------------------------------------------------------------------------------------------------

_INTERROGATIVOS = r"(?:cuanto|cuanta|cuantos|cuantas|que|cual|cuales|quien|como|donde|cuando|hay|a que)"
_SEPARADOR = re.compile(rf"\s+(?:y (?:ademas |tambien )?|ademas |tambien )(?={_INTERROGATIVOS}\b)")


def dividir(texto: str) -> list[str]:
    """Dos preguntas escritas juntas, por separado. Solo corta si después del «y» empieza otra pregunta."""
    partes = [p.strip() for p in _SEPARADOR.split(texto) if p.strip()]
    return partes if len(partes) > 1 and all(len(p.split()) >= 2 for p in partes) else [texto]


# --- Clasificar -----------------------------------------------------------------------------------------------------

# Frases de ejemplo por intención. No son las únicas formas: el clasificador busca la más parecida.
EJEMPLOS: dict[str, tuple[str, ...]] = {
    # Análisis de la gerencia
    "ingresos": (
        "cuanto facturamos",
        "cuanta plata entro",
        "cuanto se cobro",
        "cuanto hicimos de plata",
        "recaudacion del mes",
        "cuanto dinero ganamos",
        "total cobrado",
        "ingresos de la semana",
        "cuanto entro en caja en total",
        "la facturacion",
    ),
    "turnos": (
        "cuantos turnos hubo",
        "cuantos clientes vinieron",
        "cuanta gente entro",
        "cuantas parejas vinieron",
        "cantidad de turnos",
        "cuantos autos entraron",
        "cuantas visitas tuvimos",
    ),
    "ocupacion": (
        "porcentaje de ocupacion",
        "que tan lleno estuvo el motel",
        "cuanto se ocupo",
        "nivel de ocupacion de las habitaciones",
        "estuvimos llenos",
    ),
    "horas": (
        "a que hora viene mas gente",
        "cual es la hora pico",
        "que dia de la semana hay mas movimiento",
        "horario mas tranquilo",
        "cuando se llena",
    ),
    "pronostico": (
        "cuantos turnos esperamos manana",
        "cuanta gente va a venir",
        "que se espera para esta noche",
        "pronostico de la semana",
        "como va a estar el sabado",
    ),
    "estadia": ("cuanto tiempo se quedan", "duracion promedio de una estadia", "cuanto dura un turno"),
    "ticket": ("ticket promedio", "cuanto gasta cada cliente", "gasto promedio por turno"),
    "caja": (
        "faltantes en la caja",
        "diferencias en los arqueos",
        "quien tuvo faltantes",
        "algun conserje roba plata",
        "como vienen los cierres de caja",
    ),
    "medios": ("como pagan los clientes", "cuanto con tarjeta y cuanto en efectivo", "pagos por mercado pago"),
    "sobreturno": ("cuantos se pasan del tiempo", "cuanto dejaron los sobreturnos", "turnos excedidos cobrados"),
    "stock": ("que hay que reponer", "que se esta acabando", "que tengo que comprar para el minibar"),
    "articulos": ("que es lo que mas se vende", "cuantas cervezas se vendieron", "productos mas pedidos"),
    "habitaciones": ("que habitacion se usa menos", "cual es la habitacion que mas deja", "uso de cada habitacion"),
    "perdidos": ("cuantos clientes se fueron sin entrar", "gente que perdimos por no tener lugar", "clientes perdidos"),
    "opiniones": ("que opinan los clientes", "como nos califican", "estan conformes los clientes", "las resenas"),
    "ropa": ("faltan toallas", "cuantas sabanas hay", "recuento de ropa"),
    "arreglos": ("que habitacion se rompe mas", "cuanto gastamos en arreglos", "fallas de las habitaciones"),
    "gemelo": ("que pasaria si la limpieza tarda menos", "y si agrego una habitacion", "simular subir el precio"),
    "resumen": ("como venimos", "dame un resumen", "como esta el negocio", "como va todo en general"),
    "comparar": (
        "comparar esta semana con la pasada",
        "vendimos mas que el mes pasado",
        "como estamos contra el mes anterior",
        "diferencia entre octubre y septiembre",
    ),
    "proyeccion": (
        "cuanto vamos a facturar este mes",
        "a cuanto llegamos a fin de mes",
        "como cerramos el mes a este ritmo",
        "proyeccion del mes",
    ),
    "dias": ("cual fue el mejor dia", "que dia facturamos mas", "el peor dia del mes", "dia record"),
    "consejos": (
        "que me recomendas",
        "como puedo ganar mas",
        "que deberia mejorar",
        "dame un consejo",
        "que harias vos",
        "en que me conviene invertir",
    ),
    "alertas": ("que alertas hay", "hay algo raro", "algo que tenga que revisar", "algun problema"),
    "tarifas_sugeridas": ("que tarifa conviene subir", "deberia subir los precios", "estan bien los precios"),
    # La ventanilla ahora
    "libres": ("hay habitaciones libres", "tenes alguna disponible", "hay lugar", "que habitacion puedo dar"),
    "ocupadas": ("que habitaciones estan ocupadas", "cuales tienen gente", "cuantas estan ocupadas"),
    "vencimientos": ("cual vence primero", "quien esta pasado de hora", "hay alguna excedida", "a quien se le termina"),
    "cuenta": ("cuanto debe la habitacion", "cuanto le cobro", "cuanto tiene que pagar", "como va la cuenta"),
    "guardia": ("quien esta de guardia", "a que hora termina mi guardia", "cuanto me falta para irme"),
    "proxima": ("cuando se libera alguna", "cuanto tiene que esperar el cliente", "cual se desocupa primero"),
    "novedades": ("que novedades dejaron", "que paso en la guardia anterior", "hay alguna nota"),
    "pedidos": ("llego el pedido", "hay pedidos pendientes", "pedidos al proveedor"),
    "estado": ("como esta la ventanilla", "como viene la noche", "cuales estan en limpieza", "resumen de habitaciones"),
    "tarifas": ("cuanto sale la habitacion", "precio del turno", "cuanto cobro la simple", "que tarifa rige"),
    # Conversación
    "charla:saludo": ("hola", "buenas", "como estas", "todo bien", "que haces"),
    "charla:gracias": ("gracias", "sos un genio", "muy bien", "excelente", "te pasaste", "buenisimo"),
    "charla:capacidades": ("que podes hacer", "en que me ayudas", "quien sos", "para que servis"),
}

# Las preguntas con que se ofrece cada intención cuando hay que preguntar «¿quisiste decir…?».
PREGUNTA_DE = {
    "ingresos": "¿Cuánto facturamos?",
    "turnos": "¿Cuántos turnos hubo?",
    "ocupacion": "¿Cuál fue la ocupación?",
    "horas": "¿A qué hora hay más demanda?",
    "pronostico": "¿Cuántos turnos esperamos mañana?",
    "estadia": "¿Cuánto dura una estadía promedio?",
    "ticket": "¿Cuál es el ticket promedio?",
    "caja": "¿Quién tuvo más faltantes?",
    "medios": "¿Cómo pagan los clientes?",
    "sobreturno": "¿Cuánto dejan los sobreturnos?",
    "stock": "¿Qué artículos hay que reponer?",
    "articulos": "¿Qué es lo que más se vende?",
    "habitaciones": "¿Qué habitación se usa menos?",
    "perdidos": "¿Cuántos clientes se fueron?",
    "opiniones": "¿Qué dicen los clientes?",
    "ropa": "¿Faltan toallas?",
    "arreglos": "¿Qué habitación se rompe más?",
    "gemelo": "¿Qué pasa si la limpieza tarda 20 minutos?",
    "resumen": "¿Cómo venimos?",
    "comparar": "¿Cómo estamos contra el mes pasado?",
    "proyeccion": "¿Cuánto vamos a facturar este mes?",
    "dias": "¿Cuál fue el mejor día del mes?",
    "consejos": "¿Qué me recomendás?",
    "alertas": "¿Qué alertas hay?",
    "tarifas_sugeridas": "¿Qué tarifa conviene subir?",
    "libres": "¿Qué habitaciones están libres?",
    "ocupadas": "¿Cuáles están ocupadas?",
    "vencimientos": "¿Cuál vence primero?",
    "cuenta": "¿Cuánto debe la 5?",
    "guardia": "¿Quién está de guardia?",
    "proxima": "¿Cuándo se libera la próxima?",
    "novedades": "¿Qué novedades hay?",
    "pedidos": "¿Hay pedidos pendientes?",
    "estado": "¿Cómo está la ventanilla?",
    "tarifas": "¿Cuánto sale cada categoría?",
}

_VACIAS = set(
    "a al algo algun alguna como con cual cuales cuando de del donde el ella en es esa ese esta este hay la las le lo "
    "los me mi mis muy no nos o para pero por que se si sin sobre su sus te tengo tiene tu un una uno unos y ya yo "
    "puedo podes quiero necesito saber decime dime vos usted ustedes esto eso aca alla ahi".split()
)


def _raiz(palabra: str) -> str:
    return palabra[:5] if len(palabra) > 5 else palabra


def _tokens(texto: str) -> list[str]:
    return [_raiz(p) for p in re.findall(r"[a-zñ0-9]+", texto) if p not in _VACIAS]


def _trigramas(texto: str) -> Counter:
    limpio = f"  {' '.join(p for p in texto.split() if p not in _VACIAS)}  "
    return Counter(limpio[i : i + 3] for i in range(len(limpio) - 2))


def _coseno(a: Counter, b: Counter) -> float:
    comun = sum(a[k] * b[k] for k in a.keys() & b.keys())
    if not comun:
        return 0.0
    return comun / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


@lru_cache(maxsize=1)
def _indice():
    documentos = [(intencion, frase) for intencion, frases in EJEMPLOS.items() for frase in frases]
    apariciones = Counter(t for _, frase in documentos for t in set(_tokens(frase)))
    total = len(documentos)
    idf = {t: math.log((1 + total) / (1 + n)) + 1 for t, n in apariciones.items()}
    vectores = [
        (intencion, Counter({t: idf[t] for t in _tokens(frase)}), _trigramas(frase)) for intencion, frase in documentos
    ]
    return idf, vectores


def clasificar(texto: str, opciones: set[str] | None = None, cantidad: int = 3) -> list[tuple[float, str]]:
    """Las intenciones más parecidas a la pregunta, de 0 a 1. `opciones` limita a algunas intenciones."""
    idf, vectores = _indice()
    consulta = Counter({t: idf.get(t, 2.5) for t in _tokens(texto)})
    if not consulta:
        return []
    trigramas = _trigramas(texto)
    mejores: dict[str, float] = {}
    for intencion, vector, tri in vectores:
        if opciones is not None and intencion not in opciones:
            continue
        # Las palabras en común pesan más; los trozos de letras salvan los errores de tipeo y las formas verbales.
        puntaje = 0.7 * _coseno(consulta, vector) + 0.3 * _coseno(trigramas, tri)
        if puntaje > mejores.get(intencion, 0.0):
            mejores[intencion] = puntaje
    return sorted(((round(p, 3), i) for i, p in mejores.items()), reverse=True)[:cantidad]


# Umbrales: con «seguro» se responde; entre «dudoso» y «seguro», se pregunta.
SEGURO = 0.5
DUDOSO = 0.3
