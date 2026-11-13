"""Asistente de la gerencia: responde preguntas en español sobre los datos del motel, sin servicios externos.

Interpreta la pregunta con reglas (palabras clave con tildes y mayúsculas normalizadas, período, categoría, conserje
y habitación mencionados) y, si ninguna coincide, con el clasificador por ejemplos de services.comprension; si duda,
pregunta. La contesta con los mismos cálculos de la inteligencia local y dice qué entendió, qué período miró y cómo lo
calculó. Además razona sobre los datos: compara dos períodos y dice de dónde sale la diferencia, proyecta el cierre del
mes, encuentra el mejor y el peor día, explica por qué cambió algo («¿por qué?»), dice si un número es mucho o poco
para el motel («¿es mucho?») y arma recomendaciones con las alertas, las tarifas sugeridas y el stock. Como el resto del
módulo, solo ve lo cerrado (RN-RES-03): la guardia en curso se suma cuando se arquea, y si un período todavía no tiene
datos arqueados lo dice en lugar de contestar «cero».
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, median, pstdev

from app.models.cliente_perdido import MOTIVOS
from app.services import comprension
from app.services import gemelo as simulador
from app.services import inteligencia as ia
from app.services.caja import FALTANTE, SOBRANTE

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
DIAS_SIN_TILDE = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

SUGERENCIAS = [
    "¿Cuánto facturamos la semana pasada?",
    "¿Cuántos turnos esperamos mañana?",
    "¿Qué categoría deja más plata?",
    "¿Quién tuvo más faltantes en los últimos 30 días?",
    "¿A qué hora hay más demanda los sábados?",
    "¿Qué artículos hay que reponer?",
    "¿Cuál es la habitación menos usada?",
    "¿Cuánto dura una estadía promedio en VIP?",
]

# Intenciones: palabras (sin tildes) que suman puntos. La primera de la lista gana los empates: por eso las preguntas
# que razonan (comparar, proyectar, aconsejar) van antes que las de un dato suelto.
INTENCIONES: list[tuple[str, list[str]]] = [
    ("ayuda", [r"\bayuda\b", r"que (podes|sabes|puedo)", r"como (te uso|funciona)"]),
    (
        "consejos",
        [
            r"\b(recomend|aconsej|consejo)",
            r"\bsuger(i|is|ime|ir|iria|irias|encias?)\b(?! de (tarifa|precio))",
            r"\bmejoras\b",
            r"que (deberia|tendria que|conviene|me conviene|podria|podemos|puedo) (hacer|mejorar|cambiar)",
            r"como (puedo|podemos|hago para|hacemos para|hacer para) (ganar|vender|facturar|mejorar|crecer|aumentar)",
            r"\b(ganar|vender|facturar) mas\b",
            r"que harias",
            r"en que (invertir|conviene invertir|me conviene invertir)",
        ],
    ),
    (
        "alertas",
        [
            r"\balertas?\b",
            r"algo (raro|extrano|sospechoso|fuera de lo comun|anormal)",
            r"(algo|que) (tengo|tenga|hay|habria) que (revisar|mirar|controlar|ver)",
            r"\banomal",
        ],
    ),
    (
        "tarifas_sugeridas",
        [
            r"(que|cual|cuales) (tarifas?|precios?|categorias?) (conviene|convendria|deberia|hay que)"
            r" (subir|bajar|cambiar|ajustar)",
            r"(deberia|conviene|convendria|hay que|tengo que|deberiamos) (subir|bajar|ajustar|aumentar|cambiar)"
            r" (los |las |el |la )?(precios?|tarifas?)",
            r"(estan|esta) bien (los precios|las tarifas|la tarifa|el precio)",
            r"(precios?|tarifas?) (muy )?(altos?|bajos?|caros?|baratos?|altas?|bajas?|caras?|baratas?)",
            r"sugerencias? de (tarifa|precio)",
            r"(precios?|tarifas?) (estan|esta|son|es)"
            r" (bien|mal|caros?|caras?|baratos?|baratas?|altos?|altas?|bajos?|bajas?)",
            r"(conviene|convendria|deberia|deberiamos|hay que|tendria que|tendriamos que)"
            r" (subir|bajar|aumentar|ajustar)"
            r" (la|el|los|las) ",
        ],
    ),
    (
        "proyeccion",
        [
            r"(vamos|va) a (facturar|hacer|ganar|cerrar|terminar|llegar|sacar|cobrar|vender|entrar|dejar)",
            r"fin de mes",
            r"a este ritmo",
            r"proyecc",
            r"(cerrariamos|terminariamos|llegariamos|cerraremos|terminaremos|cerraria|terminaria)",
            r"(como|cuanto|en cuanto) (cerramos|terminamos|cerraria|cierra) el mes",
            r"\bsi (seguimos|sigue|continua|continuamos|mantenemos) (asi|igual|este ritmo|a este ritmo)",
        ],
    ),
    (
        "comparar",
        [
            r"\bcompar",
            r"\bcontra (el|la|los|las|lo|ayer|hoy)\b",
            r"\b(mas|menos|mejor|peor)\b.{0,30}\bque (el |la |lo |los |las |en )?(semana|mes|ano|pasad|anterior|previ"
            r"|dia|finde|fin de"
            r" semana|ayer|hoy|antes|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre"
            r"|noviembre|diciembre|lunes|martes|miercoles|jueves|viernes|sabado|domingo)",
            r"respecto (al?|del?|de la)\b",
            r"diferencia (entre|con|contra)\b",
            r"\b(crecimos|caimos|mejoramos|empeoramos|subimos|bajamos)\b",
            r"\b(subio|bajo|crecio|cayo|aumento|disminuyo|mejoro|empeoro) (la |el |lo |los )?"
            r"(facturacion|plata|ingresos?|turnos?|ventas?|ocupacion|recaudacion)",
        ],
    ),
    (
        "dias",
        [
            r"(mejor|peor) dia",
            r"dia (record|con mas|con menos|de mas|de menos|que mas|que menos)",
            r"(que|cual) dia (facturamos|vendimos|cobramos|entro|hubo|hicimos|tuvimos|vinieron|fue|se facturo|se cobro)"
            r" (mas|menos)",
            r"(cual|que) (fue|es) el dia (que|con|de) (mas|menos)",
            r"dias? (mas|menos) (fuertes?|flojos?) (del|de la|de) (mes|semana|ano)",
        ],
    ),
    (
        "resumen",
        [
            r"\bresumen\b",
            r"como (venimos|estamos|va|vamos)(?! de (ingres|plata|turnos|factur|caja|ocupacion|venta))",
            r"\bnovedades\b",
            r"que (paso|hay de nuevo)",
            r"como (esta|anda|va|viene) (el negocio|el motel|todo|la cosa|el mes|el ano)",
        ],
    ),
    (
        "gemelo",
        [
            r"que pasa(ria)? si"
            r" .*(limpi|habitacion|precio|tarifa|agrego|sumo|subo|bajo|tuviera|hubiera|pongo|abro|vip)",
            r"\bsimul(a|ar|ame|acion)\b",
            r"si (la )?limpieza (tarda|demora|fuera|baja|dura)",
            r"(cuanto|que) (ganaria|ganariamos|cambiaria)",
            r"\bsi (limpiaramos|limpiamos|tardara|tardaramos|demoraramos|pongo|agrego|sumo|tuviera|tuvieramos|hubiera"
            r"|abro|construyo|subo|bajo|aumento|agregamos|sumamos|ponemos)\b",
        ],
    ),
    (
        "opiniones",
        [
            r"\b(opinion|opiniones|calificacion|calificaciones|queja|quejas|puntaje|resenas?|estrellas)\b",
            r"que (dicen|opinan|piensan) (los clientes|de nosotros)",
            r"como nos (califican|puntuan|ven)",
            r"\b(contentos?|conformes?|satisfechos?|insatisfechos?)\b",
        ],
    ),
    ("ropa", [r"\btoallas?\b", r"\bsabanas?\b", r"ropa de cama", r"\bropa\b", r"\blavanderia\b"]),
    (
        "arreglos",
        [
            r"\barreglos?\b",
            r"\bfallas?\b",
            r"\breparacion(es)?\b",
            r"(gast|cost)\w* .*mantenimiento",
            r"se (rompe|rompio|rompen)",
        ],
    ),
    (
        "perdidos",
        [
            r"clientes? perdid",
            r"\bperdimos\b",
            r"se (nos )?fueron",
            r"sin lugar",
            r"no (hubo|habia|tener|tenemos|teniamos) lugar",
            r"por falta de lugar",
            r"clientes? (rechazad|que se fue)",
            r"se (fue|fueron|van|iban) sin (entrar|quedarse)",
            r"gente que se (fue|va)",
            r"\bse (nos )?(estan |esta )?(yendo|van|iban|va) .*\b(clientes|gente)\b|\b(clientes|gente) .*\b(yendo|se"
            r" van)\b",
            r"\bsin (entrar|quedarse)\b",
        ],
    ),
    (
        "pronostico",
        [
            r"\bmanana\b",
            r"pronostic",
            r"\besperamos\b",
            r"\bespera",
            r"\bproxim",
            r"esta noche",
            r"\bva(mos|n)? a\b",
            r"\bprever\b",
            r"\bcalcul(as|a|amos|aria)\b",
            r"para (el|este) (lunes|martes|miercoles|jueves|viernes|sabado|domingo|fin de semana)",
            r"(el|este) (lunes|martes|miercoles|jueves|viernes|sabado|domingo) que viene",
        ],
    ),
    (
        "stock",
        [
            r"\bstock\b",
            r"\brepon",
            r"\bagot",
            r"falta comprar",
            r"\bpedir(le|les)?\b",
            r"\bcomprar(le|les)?\b",
            r"(conviene|hay que|tengo que|deberia) (pedir|comprar|encargar)\w* al proveedor",
            r"inventario",
            r"por (acabar|agotar|terminar)se?\b",
            r"se (esta|estan) (acabando|agotando|terminando)",
        ],
    ),
    (
        "articulos",
        [
            r"articulo",
            r"producto",
            r"(que|lo que|cual|cuales) (es lo que )?(se )?(mas|menos) (se )?vend",
            r"mas vendid",
            r"(cuant[ao]s?) \w+ (se )?vend",
            r"\bconsum",
            r"mas pedid",
            r"bebida",
            r"minibar",
        ],
    ),
    (
        "caja",
        [
            r"faltante",
            r"sobrante",
            r"\barqueo",
            r"diferencia",
            r"\btdc\b",
            r"\bcaja\b",
            r"descuadr",
            r"\b(roba|robando|robo|robaron|afana|afanando|chorea|choreando)\b",
            r"se queda con (la )?plata",
        ],
    ),
    (
        "medios",
        [
            r"efectivo",
            r"tarjeta",
            r"posnet",
            r"mercado ?pago",
            r"medios? de pago",
            r"\bcomo (nos )?(pagan|paga|cobramos)",
            r"con que pagan",
        ],
    ),
    ("sobreturno", [r"sobreturno", r"excedi", r"se pasan", r"tiempo extra", r"fraccion", r"pasan del tiempo"]),
    ("estadia", [r"estadia", r"duracion", r"cuanto (tiempo|duran|dura|se quedan)", r"permanencia", r"\bdura\b"]),
    ("ticket", [r"\bticket\b", r"promedio por turno", r"gasto promedio", r"cuanto gasta", r"precio promedio"]),
    (
        "ocupacion",
        [
            r"ocupacion",
            r"\bocupad",
            r"\bocup(o|amos|aron|a)\b",
            r"\bllen",
            r"\blibres?\b",
            r"porcentaje de uso",
            r"(que tan|cuan) llen",
        ],
    ),
    (
        "horas",
        [
            r"hora pico",
            r"a que hora",
            r"que hora",
            r"que dia",
            r"mejor dia",
            r"peor dia",
            r"\bcuando\b",
            r"horario",
            r"mas demanda",
            r"mas movimiento",
        ],
    ),
    (
        "habitaciones",
        [
            r"habitacion",
            r"\bpieza",
            r"\bcuarto",
            r"mas usad",
            r"menos usad",
            r"(anda|rinde|funciona) (mejor|peor)",
        ],
    ),
    (
        "ingresos",
        [
            r"ingres",
            r"factur",
            r"\bcobr",
            r"\bplata\b",
            r"recaud",
            r"\bgan",
            r"\bdeja",
            r"\bvent[ao]s?\b",
            r"dinero",
            r"\bpesos\b",
            r"rinde",
            r"rentab",
            r"cuanto (hicimos|hizo|se hizo|sacamos|saco|levantamos|juntamos|entro|ingreso|dejo|dejaron)\b",
            r"\bvendi(mos|eron|o)\b",
            r"(que|cual|cuales) categorias? (vende|factura|deja|rinde|gana|cobra|recauda)",
        ],
    ),
    (
        "turnos",
        [
            r"\bturnos?\b",
            r"\bclientes?\b",
            r"\bentrad",
            r"\bvisitas?\b",
            r"cuantos? (vinieron|entraron)",
            r"cuant[ao]s? (gente|personas|autos|motos|parejas|peatones)",
            r"cuant[ao]s? turnos",
            r"(gente|autos|parejas|motos) (entro|vino|hubo|entraron|vinieron)",
        ],
    ),
]
# Lo que se le dice a quien pregunta para que vea qué entendió Mot.
QUE_ENTENDI = {
    "ingresos": "Ingresos",
    "turnos": "Turnos",
    "ocupacion": "Ocupación",
    "horas": "Horarios de llegada",
    "pronostico": "Pronóstico",
    "estadia": "Duración de las estadías",
    "ticket": "Ticket promedio",
    "caja": "Arqueos y faltantes",
    "medios": "Medios de pago",
    "sobreturno": "Sobreturnos",
    "articulos": "Ventas del minibar",
    "habitaciones": "Uso de las habitaciones",
    "perdidos": "Clientes que se fueron",
    "comparar": "Comparación",
    "proyeccion": "Proyección del mes",
    "dias": "Mejor y peor día",
    "explicacion": "Por qué cambió",
    "valoracion": "Si es mucho o poco",
    "tarifas_sugeridas": "Tarifas que conviene cambiar",
    "consejos": "Recomendaciones",
    "alertas": "Alertas",
    "resumen": "Resumen",
    "stock": "Stock para reponer",
    "opiniones": "Opiniones de los clientes",
    "ropa": "Ropa",
    "arreglos": "Arreglos",
    "gemelo": "Simulación",
}
# La pregunta de cada intención en una forma fija: la siguiente pregunta («¿y la anterior?») se entiende sobre ella.
CANONICA = {
    "ingresos": "cuanto facturamos",
    "turnos": "cuantos turnos hubo",
    "ocupacion": "cual fue la ocupacion",
    "ticket": "cual fue el ticket promedio",
    "estadia": "cuanto dura la estadia",
    "sobreturno": "cuantos sobreturnos hubo",
    "medios": "con que medios de pago pagaron",
    "caja": "como dieron los arqueos de caja",
    "horas": "a que hora hubo mas demanda",
    "articulos": "que articulos se vendieron mas",
    "habitaciones": "que habitacion se uso mas",
    "perdidos": "cuantos clientes perdimos",
    "dias": "cual fue el mejor dia",
}
# Seguimientos que razonan sobre la respuesta anterior.
EXPLICAR = re.compile(
    r"^(y )?(por que|porque|a que se debe|como (puede ser|es posible|se explica)|que paso|de donde sale|explica(me|lo)?"
    r"|por que (bajo|subio|cayo|aumento|tan|hay|es|son|da))\b"
)
VALORAR = re.compile(
    r"^(y )?(eso )?(es|son|esta|fue|estuvo|estan)? ?(mucho|poco|bueno|malo|normal|bien|mal|alto|bajo|lo normal"
    r"|razonable|aceptable)\b|^(y )?(eso )?(es|esta) (bien|mal|bueno|normal)|\b(es|esta) (mucho|poco|normal|bien|bajo"
    r"|alto) para\b|comparado con lo normal|^(y )?(eso )?es (un buen|un mal) numero"
)
ANTERIOR = re.compile(r"\b(la|el) (anterior|previa|previo)\b|\bantes de es[oa]\b|^y antes\b|\bla otra\b")


def normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    limpio = re.sub(r"[^a-z0-9ñ/ ]", " ", sin_tildes)
    limpio = re.sub(r"(?<!\d)/|/(?!\d)", " ", limpio)
    return re.sub(r"\s+", " ", limpio).strip()


@dataclass
class Periodo:
    desde: date
    hasta: date  # inclusive
    etiqueta: str
    dias_semana: set[int] | None = None
    explicito: bool = True

    @property
    def en(self) -> str:
        """El período como complemento: «ayer», «el sábado 31/10», «en la semana pasada»."""
        if self.etiqueta in ("hoy", "ayer", "anteayer") or self.etiqueta.startswith(("el ", "del ", "desde ")):
            return self.etiqueta
        return f"en {self.etiqueta}"

    def canonico(self) -> str:
        """El período escrito de una forma que interpretar_periodo vuelve a entender igual."""
        if self.dias_semana:
            return normalizar(self.etiqueta)
        if self.desde == self.hasta:
            return f"el {self.desde.day}/{self.desde.month}/{self.desde.year}"
        return (
            f"del {self.desde.day}/{self.desde.month}/{self.desde.year} al {self.hasta.day}/{self.hasta.month}/"
            f"{self.hasta.year}"
        )

    @property
    def en_mayuscula(self) -> str:
        return self.en[0].upper() + self.en[1:]

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1

    def anterior(self) -> "Periodo":
        return Periodo(
            self.desde - timedelta(days=self.dias),
            self.desde - timedelta(days=1),
            "el período anterior",
            self.dias_semana,
        )

    def contiene(self, momento: datetime) -> bool:
        return self.desde <= momento.date() <= self.hasta and (
            self.dias_semana is None or momento.weekday() in self.dias_semana
        )

    def texto(self) -> str:
        rango = f"del {self.desde.day}/{self.desde.month} al {self.hasta.day}/{self.hasta.month}"
        if self.desde == self.hasta:
            rango = f"el {ia.fecha_corta(self.desde)}"
        if self.dias_semana:
            nombres = " y ".join(ia.DIAS[d] for d in sorted(self.dias_semana))
            rango += f", solo {nombres}"
        return rango


MES_NUMERO = {mes: i + 1 for i, mes in enumerate(MESES)}
_MESES = "|".join(MESES)
_DIAS = "|".join(DIAS_SIN_TILDE)
_CUANTOS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6}


def _fecha(dia: str, mes: str | int, anio: str | None, hoy: date) -> date | None:
    """Una fecha escrita; sin año, la más reciente que no sea futura."""
    numero_anio = (int(anio) + (2000 if int(anio) < 100 else 0)) if anio else hoy.year
    try:
        fecha = date(numero_anio, int(mes), int(dia))
    except ValueError:
        return None
    if anio is None and fecha > hoy:
        try:
            fecha = fecha.replace(year=fecha.year - 1)
        except ValueError:
            return None
    return fecha


def _fin_de_mes(dia: date) -> date:
    return date(dia.year + dia.month // 12, dia.month % 12 + 1, 1) - timedelta(days=1)


def _mes(anio: int, mes: int, hoy: date) -> "Periodo":
    inicio = date(anio, mes, 1)
    reciente = anio == hoy.year or inicio > hoy.replace(year=hoy.year - 1)
    etiqueta = MESES[mes - 1] if reciente else f"{MESES[mes - 1]} {anio}"
    return Periodo(inicio, min(_fin_de_mes(inicio), hoy), etiqueta)


def etiqueta_dia(dia: date, hoy: date) -> str:
    if dia == hoy:
        return "hoy"
    if dia == hoy - timedelta(days=1):
        return "ayer"
    return f"el {ia.DIAS[dia.weekday()]} {dia.day}/{dia.month}"


def _semana_de(dia: date, hoy: date, etiqueta: str | None = None) -> "Periodo":
    lunes = dia - timedelta(days=dia.weekday())
    return Periodo(lunes, min(lunes + timedelta(days=6), hoy), etiqueta or f"la semana del {lunes.day}/{lunes.month}")


def previo_de(periodo: "Periodo", hoy: date) -> "Periodo":
    """El período anterior del mismo tipo: la semana de antes, el mes de antes, el día de antes."""
    if periodo.dias_semana:
        return periodo.anterior()
    if periodo.desde.day == 1 and (periodo.hasta == _fin_de_mes(periodo.desde) or periodo.hasta == hoy):
        if periodo.desde.month == 1 and periodo.dias > 31:  # un año
            inicio = date(periodo.desde.year - 1, 1, 1)
            return Periodo(inicio, date(inicio.year, 12, 31), f"el año {inicio.year}")
        anterior = periodo.desde - timedelta(days=1)
        return _mes(anterior.year, anterior.month, hoy)
    if periodo.desde.weekday() == 0 and periodo.dias <= 7:
        return _semana_de(periodo.desde - timedelta(days=7), hoy)
    if periodo.dias == 1:
        dia = periodo.desde - timedelta(days=1)
        return Periodo(dia, dia, etiqueta_dia(dia, hoy))
    anterior = periodo.anterior()
    anterior.etiqueta = f"los {periodo.dias} días anteriores"
    return anterior


def interpretar_periodo(texto: str, hoy: date) -> Periodo:
    lunes = hoy - timedelta(days=hoy.weekday())
    # Fechas escritas: «del 1/11 al 10/11», «del 1 al 10 de noviembre», «el 5/11», «el 3 de noviembre».
    fecha = r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?"
    if m := re.search(rf"\b(?:del|desde el) {fecha} (?:al|hasta el) {fecha}", texto):
        desde, hasta = _fecha(m[1], m[2], m[3], hoy), _fecha(m[4], m[5], m[6], hoy)
        if desde and hasta and desde <= hasta:
            return Periodo(desde, min(hasta, hoy), f"del {desde.day}/{desde.month} al {hasta.day}/{hasta.month}")
    if m := re.search(rf"\bsemana del {fecha}", texto):
        if dia := _fecha(m[1], m[2], m[3], hoy):
            return _semana_de(dia, hoy)
    if m := re.search(rf"\bdel (\d{{1,2}}) al (\d{{1,2}}) de ({_MESES})\b", texto):
        desde, hasta = _fecha(m[1], MES_NUMERO[m[3]], None, hoy), _fecha(m[2], MES_NUMERO[m[3]], None, hoy)
        if desde and hasta and desde <= hasta:
            return Periodo(desde, min(hasta, hoy), f"del {desde.day}/{desde.month} al {hasta.day}/{hasta.month}")
    if m := re.search(rf"\b(?:el )?{fecha}\b", texto):
        if dia := _fecha(m[1], m[2], m[3], hoy):
            return Periodo(dia, dia, etiqueta_dia(dia, hoy))
    if m := re.search(rf"\b(?:el )?(\d{{1,2}}) de ({_MESES})\b", texto):
        if dia := _fecha(m[1], MES_NUMERO[m[2]], None, hoy):
            return Periodo(dia, dia, etiqueta_dia(dia, hoy))
    if m := re.search(r"ultim[oa]s? (\d+) (dias|semanas|meses)", texto):
        n = int(m.group(1)) * {"dias": 1, "semanas": 7, "meses": 30}[m.group(2)]
        return Periodo(hoy - timedelta(days=n - 1), hoy, f"los últimos {m.group(1)} {m.group(2)}")
    # «Desde el lunes», «desde ayer», «desde principio de mes», «desde el 5».
    if m := re.search(rf"\bdesde (?:el )?({_DIAS})\b", texto):
        inicio = hoy - timedelta(days=(hoy.weekday() - DIAS_SIN_TILDE.index(m[1])) % 7)
        return Periodo(inicio, hoy, f"desde el {ia.DIAS[inicio.weekday()]} {inicio.day}/{inicio.month}")
    if re.search(r"\bdesde ayer\b", texto):
        return Periodo(hoy - timedelta(days=1), hoy, "desde ayer")
    if re.search(r"desde (el )?(principio|comienzo|inicio)s? de(l)? mes|en lo que va del mes", texto):
        return Periodo(hoy.replace(day=1), hoy, "este mes")
    if m := re.search(r"\bdesde el (\d{1,2})\b", texto):
        if dia := _fecha(m[1], hoy.month, None, hoy):
            return Periodo(dia, hoy, f"desde el {dia.day}/{dia.month}")
    # «Hace dos semanas», «hace 3 días», «hace un mes».
    if m := re.search(r"\bhace (\d+|un|una|uno|dos|tres|cuatro|cinco|seis) (dias?|semanas?|mes|meses)\b", texto):
        n = int(m[1]) if m[1].isdigit() else _CUANTOS[m[1]]
        if m[2].startswith("dia"):
            dia = hoy - timedelta(days=n)
            return Periodo(dia, dia, etiqueta_dia(dia, hoy))
        if m[2].startswith("semana"):
            return _semana_de(hoy - timedelta(weeks=n), hoy)
        mes, anio = hoy.month - n, hoy.year
        while mes < 1:
            mes, anio = mes + 12, anio - 1
        return _mes(anio, mes, hoy)
    if re.search(r"\bhoy\b", texto):
        return Periodo(hoy, hoy, "hoy")
    if re.search(r"\banteayer\b", texto):
        return Periodo(hoy - timedelta(days=2), hoy - timedelta(days=2), "anteayer")
    if re.search(r"\b(ayer|anoche)\b", texto):
        return Periodo(hoy - timedelta(days=1), hoy - timedelta(days=1), "ayer")
    if re.search(r"semana (antepasada|trasanterior)|antepenultima semana", texto):
        return _semana_de(lunes - timedelta(days=14), hoy, "la semana antepasada")
    if re.search(r"semana (pasada|anterior)", texto):
        return Periodo(lunes - timedelta(days=7), lunes - timedelta(days=1), "la semana pasada")
    if re.search(r"(esta|la) semana|en la semana", texto):
        return Periodo(lunes, hoy, "esta semana")
    if re.search(r"ultima semana|ultimos siete dias", texto):
        return Periodo(hoy - timedelta(days=6), hoy, "la última semana")
    if re.search(r"mes (pasado|anterior)", texto):
        fin = hoy.replace(day=1) - timedelta(days=1)
        return Periodo(fin.replace(day=1), fin, f"{MESES[fin.month - 1]} (el mes pasado)")
    if re.search(r"este mes|en el mes|\bdel mes\b(?! (pasado|anterior))", texto):
        return Periodo(hoy.replace(day=1), hoy, "este mes")
    if re.search(r"ultimo mes", texto):
        return Periodo(hoy - timedelta(days=29), hoy, "el último mes")
    if re.search(r"ano (pasado|anterior)", texto):
        return Periodo(date(hoy.year - 1, 1, 1), date(hoy.year - 1, 12, 31), f"el año {hoy.year - 1}")
    if re.search(r"este ano|en el ano|en lo que va del ano|\bel ano\b", texto):
        return Periodo(date(hoy.year, 1, 1), hoy, "este año")
    for i, mes in enumerate(MESES):
        if re.search(rf"\b(en|de|durante) {mes}\b", texto):
            anio = hoy.year if i + 1 <= hoy.month else hoy.year - 1
            inicio = date(anio, i + 1, 1)
            fin = (date(anio + (i + 1) // 12, (i + 1) % 12 + 1, 1)) - timedelta(days=1)
            return Periodo(inicio, min(fin, hoy), mes)
    if re.search(r"fines? de semana|finde", texto):
        if re.search(r"\b(los|cada|todos los) (fines|findes)", texto):
            return Periodo(hoy - timedelta(weeks=8), hoy, "los fines de semana", {4, 5, 6})
        viernes = hoy - timedelta(days=(hoy.weekday() - 4) % 7)
        if viernes + timedelta(days=2) >= hoy:
            viernes -= timedelta(days=7)
        return Periodo(viernes, viernes + timedelta(days=2), "el último fin de semana")
    for i, dia in enumerate(DIAS_SIN_TILDE):
        if re.search(rf"\b(los|cada|todos los) {dia}s?\b", texto) or re.search(rf"\b{dia}s\b", texto):
            plural = ia.DIAS[i] if ia.DIAS[i].endswith("s") else ia.DIAS[i] + "s"
            return Periodo(hoy - timedelta(weeks=8), hoy, f"los {plural}", {i})
        if re.search(rf"\b{dia}\b", texto):
            ultimo = hoy - timedelta(days=(hoy.weekday() - i) % 7 or 7)
            return Periodo(ultimo, ultimo, f"el {ia.DIAS[i]} {ultimo.day}/{ultimo.month}")
    # El nombre del mes solo («compará octubre con septiembre»).
    for i, mes in enumerate(MESES):
        if re.search(rf"\b{mes}\b", texto):
            anio = hoy.year if i + 1 <= hoy.month else hoy.year - 1
            return _mes(anio, i + 1, hoy)
    return Periodo(hoy - timedelta(days=29), hoy, "los últimos 30 días", explicito=False)


def _intencion(texto: str) -> str | None:
    puntajes = []
    for orden, (nombre, patrones) in enumerate(INTENCIONES):
        puntos = sum(1 for p in patrones if re.search(p, texto))
        if puntos:
            puntajes.append((puntos, -orden, nombre))
    return max(puntajes)[2] if puntajes else None


def _respuesta(
    texto: str,
    intencion: str,
    periodo: Periodo | None = None,
    detalle: str | None = None,
    tabla: dict | None = None,
    sugerencias: list[str] | None = None,
) -> dict:
    return {
        "respuesta": texto,
        "intencion": intencion,
        "periodo": periodo.texto() if periodo else None,
        "detalle": detalle,
        "tabla": tabla,
        "sugerencias": sugerencias or [],
    }


ANALISIS = {nombre for nombre, _ in INTENCIONES} - {"ayuda"}
# Las que no dependen de un período: no se dice «del 15/10 al 13/11» al lado.
SIN_PERIODO = {"stock", "opiniones", "ropa", "arreglos", "resumen", "consejos", "alertas", "tarifas_sugeridas"}
SIN_PERIODO |= {"pronostico", "gemelo", "proyeccion", "ayuda"}


class Asistente:
    def __init__(self, ctx: ia.Contexto):
        self.ctx = ctx
        self.hoy = ctx.ahora.date()
        # El último día con datos arqueados: lo que sigue todavía no cuenta.
        fechas = [a.momento.date() for a in ctx.arqueos] or [t.fin.date() for t in ctx.turnos]
        self.ultimo_dato: date | None = max(fechas) if fechas else None
        self.primer_dato: date | None = min(t.fin.date() for t in ctx.turnos) if ctx.turnos else None
        self.dias_con_datos = {a.momento.date() for a in ctx.arqueos} | {t.fin.date() for t in ctx.turnos}

    # --- Filtros mencionados en la pregunta ---------------------------------------------------------------------

    def _categoria(self, texto: str) -> int | None:
        for categoria in self.ctx.categorias.values():
            if re.search(rf"\b{re.escape(normalizar(categoria.nombre))}\b", texto):
                return categoria.id
        return None

    def _conserje(self, texto: str) -> int | None:
        for operador_id, nombre in self.ctx.nombres.items():
            limpio = normalizar(nombre)
            if limpio and re.search(rf"\b{re.escape(limpio)}\b", texto):
                return operador_id
        if m := re.search(r"conserje ?(\d+)", texto):
            candidatos = [i for i, n in self.ctx.nombres.items() if normalizar(n).endswith(m.group(1))]
            return candidatos[0] if candidatos else None
        return None

    def _habitacion(self, texto: str) -> int | None:
        if m := re.search(r"(habitacion|pieza|cuarto|hab) ?(n ?)?(\d+)", texto):
            numero = int(m.group(3))
            return next((h.id for h in self.ctx.habitaciones if h.numero == numero), None)
        return None

    def _turnos(self, periodo: Periodo, categoria_id: int | None = None, conserje_id: int | None = None):
        return [
            t
            for t in self.ctx.turnos
            if periodo.contiene(t.fin)
            and (categoria_id is None or t.categoria_id == categoria_id)
            and (conserje_id is None or t.cobrado_por == conserje_id)
        ]

    def _aviso_corte(self, periodo: Periodo) -> str:
        ultimo = self.ultimo_dato
        if ultimo is not None and periodo.desde <= ultimo < periodo.hasta:
            return (
                f" Hay datos arqueados hasta el {ia.fecha_corta(ultimo)}: lo que siga se suma cuando se arqueen esas "
                "guardias."
            )
        if self.ctx.hay_guardia_abierta and periodo.hasta >= self.ctx.corte.date():
            return " No incluye la guardia en curso: se suma cuando se cierre con su arqueo."
        return ""

    def _sin_turnos(self, periodo: Periodo, intencion: str, que: str = "turnos cobrados", sujeto: str = "") -> dict:
        """Cuando el período no tiene turnos: si es porque todavía no se arqueó, lo dice y ofrece lo último cerrado."""
        ultimo = self.ultimo_dato
        if ultimo is not None and periodo.desde > ultimo:
            semana = _semana_de(ultimo, self.hoy)
            texto = (
                f"Todavía no hay {que}{sujeto} {periodo.en} en guardias arqueadas: lo último que está cerrado es del "
                f"{ia.fecha_corta(ultimo)}."
            )
            if self.ctx.hay_guardia_abierta:
                texto += " No incluye la guardia en curso: se suma cuando se cierre con su arqueo."
            pregunta = comprension.PREGUNTA_DE.get(intencion, "¿Cuánto facturamos?").rstrip("?")
            return _respuesta(
                texto,
                intencion,
                periodo,
                sugerencias=[f"{pregunta} la semana del {semana.desde.day}/{semana.desde.month}?"],
            )
        return _respuesta(f"No hubo {que}{sujeto} {periodo.en}.{self._aviso_corte(periodo)}", intencion, periodo)

    def _recortado(self, periodo: Periodo) -> Periodo | None:
        """El período hasta el último día con datos arqueados (None si todavía no tiene ninguno)."""
        ultimo = self.ultimo_dato
        if ultimo is None or periodo.desde > ultimo:
            return None
        if periodo.hasta <= ultimo:
            return periodo
        # Recortado, dice sus fechas reales: «del 2/11 al 4/11», no «la semana pasada».
        etiqueta = (
            etiqueta_dia(ultimo, self.hoy)
            if periodo.desde == ultimo
            else f"del {periodo.desde.day}/{periodo.desde.month} al {ultimo.day}/{ultimo.month}"
        )
        return Periodo(periodo.desde, ultimo, etiqueta, periodo.dias_semana)

    def _por_categoria(self, turnos) -> dict:
        grupos: dict[int, list] = {}
        for t in turnos:
            grupos.setdefault(t.categoria_id, []).append(t)
        filas = [
            [
                self.ctx.nombre_categoria(c),
                len(ts),
                ia.pesos(sum(t.total for t in ts)),
                ia.pesos(sum(t.total for t in ts) / len(ts)),
            ]
            for c, ts in sorted(grupos.items(), key=lambda p: -sum(t.total for t in p[1]))
        ]
        return {"columnas": ["Categoría", "Turnos", "Ingresos", "Ticket"], "filas": filas}

    # --- Entender ------------------------------------------------------------------------------------------------

    def _intencion(self, texto: str) -> str | None:
        intencion = _intencion(texto)
        # «¿Cuánto vendimos en noviembre?» es plata; «¿cuántas cervezas vendimos?» es el minibar.
        if intencion == "articulos" and not self._nombra_articulo(texto) and not re.search(
            r"articulo|producto|bebida|minibar|mas vendid|mas pedid|(que|lo que) (mas|menos) se vende|consum"
            r"|cuant[ao]s? \w+ (se )?vend",
            texto,
        ):
            intencion = "ingresos"
        return intencion

    def _nombra_articulo(self, texto: str) -> bool:
        for a in self.ctx.articulos:
            palabras = [p for p in normalizar(a.descripcion).split() if len(p) > 3]
            if any(re.search(rf"\b{re.escape(p[:-1] if p.endswith('s') else p)}", texto) for p in palabras[:2]):
                return True
        return False

    def _entendido(self, intencion: str, periodo: Periodo, categoria_id: int | None, conserje_id: int | None) -> str:
        partes = [QUE_ENTENDI.get(intencion, intencion.capitalize())]
        if intencion not in SIN_PERIODO:
            partes.append(periodo.texto())
        if categoria_id is not None:
            partes.append(self.ctx.nombre_categoria(categoria_id))
        if conserje_id is not None:
            partes.append(self.ctx.nombres.get(conserje_id, "—"))
        return " · ".join(partes)

    def _resuelta(self, intencion: str, texto: str, periodo: Periodo, categoria_id, conserje_id) -> str:
        """La pregunta entera, con lo que se tomó de las anteriores: la próxima («¿y la anterior?») parte de acá."""
        if intencion not in CANONICA:
            return texto
        base = CANONICA[intencion]
        if intencion == "habitaciones" and "menos" in texto:
            base = "que habitacion se uso menos"
        if intencion == "dias" and re.search(r"peor|menos|flojo", texto):
            base = "cual fue el peor dia"
        if intencion == "ingresos" and re.search(r"que categoria|por categoria|cual categoria|cada categoria", texto):
            base = "cuanto facturamos por categoria"
        partes = [base, periodo.canonico()]
        if (habitacion_id := self._habitacion(texto)) is not None:
            partes.append(f"habitacion {self.ctx.numero(habitacion_id)}")
        if categoria_id is not None:
            partes.append(normalizar(self.ctx.nombre_categoria(categoria_id)))
        if conserje_id is not None:
            partes.append(normalizar(self.ctx.nombres.get(conserje_id, "")))
        return " ".join(p for p in partes if p)

    # --- Respuestas ---------------------------------------------------------------------------------------------

    def responder(self, pregunta: str, anterior: str | None = None) -> dict:
        texto = comprension.preparar(normalizar(pregunta))
        if not texto:
            return self.ayuda()
        previo = comprension.preparar(normalizar(anterior)) if anterior else None
        # Seguimientos que razonan sobre lo que se acaba de responder: «¿por qué?», «¿es mucho?».
        if previo and len(texto.split()) <= 8 and EXPLICAR.search(texto) and _intencion(texto) is None:
            return self.explicacion(previo)
        if previo and len(texto.split()) <= 8 and VALORAR.search(texto):
            return self.valoracion(previo)
        intencion = self._intencion(texto)
        periodo = interpretar_periodo(texto, self.hoy)
        categoria_id, conserje_id = self._categoria(texto), self._conserje(texto)
        # Seguimiento («¿y la semana pasada?», «¿y en VIP?», «¿y la anterior?»): lo que falta sale de la anterior.
        if previo and (texto.startswith("y ") or (intencion is None and len(texto.split()) <= 4)):
            intencion = intencion or self._intencion(previo)
            if not periodo.explicito:
                periodo_previo = interpretar_periodo(previo, self.hoy)
                periodo = previo_de(periodo_previo, self.hoy) if ANTERIOR.search(texto) else periodo_previo
            categoria_id = categoria_id or self._categoria(previo)
            conserje_id = conserje_id or self._conserje(previo)
            if intencion == "habitaciones" and self._habitacion(texto) is None:
                texto = f"{texto} {previo}"
        # «¿Cuántos turnos tuvo la habitación 5?»: lo de una habitación lo responde el uso de las habitaciones.
        if intencion in ("turnos", "ingresos") and re.search(r"\b(habitacion|pieza|cuarto|hab) ?\d", texto):
            intencion = "habitaciones"
        if intencion is None and categoria_id is not None:
            intencion = "ingresos"
        if intencion is None and self._habitacion(texto) is not None:
            intencion = "habitaciones"
        if intencion is None:
            adivinadas = comprension.clasificar(texto, ANALISIS)
            if adivinadas and adivinadas[0][0] >= comprension.SEGURO:
                intencion = adivinadas[0][1]
            elif adivinadas and adivinadas[0][0] >= comprension.DUDOSO:
                return self.aclaracion(adivinadas)
            else:
                return _respuesta(
                    "No estoy seguro de haber entendido la pregunta. Puedo responder sobre ingresos, turnos,"
                    " ocupación, "
                    "estadías, horarios de más demanda, categorías, habitaciones, caja y faltantes, artículos y stock, "
                    "el pronóstico, y también comparar períodos, proyectar el mes, decirte el mejor día o qué te "
                    "conviene hacer.",
                    "desconocida",
                    sugerencias=[comprension.PREGUNTA_DE[i] for _, i in adivinadas if i in comprension.PREGUNTA_DE]
                    or SUGERENCIAS[:4],
                )
        metodo = {
            "ayuda": lambda: self.ayuda(),
            "resumen": lambda: self.resumen(),
            "consejos": lambda: self.consejos(),
            "alertas": lambda: self.alertas(),
            "tarifas_sugeridas": lambda: self.tarifas_sugeridas(categoria_id),
            "comparar": lambda: self.comparar(texto, periodo, categoria_id, conserje_id),
            "proyeccion": lambda: self.proyeccion(categoria_id),
            "dias": lambda: self.dias(texto, periodo, categoria_id),
            "perdidos": lambda: self.perdidos(periodo, categoria_id),
            "opiniones": lambda: self.opiniones(),
            "ropa": lambda: self.ropa(),
            "arreglos": lambda: self.arreglos(texto),
            "gemelo": lambda: self.gemelo(texto, categoria_id),
            "pronostico": lambda: self.pronostico(texto),
            "stock": lambda: self.stock(texto),
            "articulos": lambda: self.articulos(texto, periodo),
            "caja": lambda: self.caja(periodo, conserje_id),
            "medios": lambda: self.medios(periodo),
            "sobreturno": lambda: self.sobreturno(periodo, categoria_id),
            "estadia": lambda: self.estadia(periodo, categoria_id),
            "ticket": lambda: self.ticket(periodo, categoria_id),
            "ocupacion": lambda: self.ocupacion(periodo, categoria_id),
            "horas": lambda: self.horas(periodo),
            "habitaciones": lambda: self.habitaciones(texto, periodo),
            "ingresos": lambda: self.ingresos(texto, periodo, categoria_id, conserje_id),
            "turnos": lambda: self.turnos(periodo, categoria_id, conserje_id),
        }[intencion]
        sin_turnos = ("ayuda", "stock", "opiniones", "ropa", "arreglos", "alertas", "consejos", "tarifas_sugeridas")
        if not self.ctx.turnos and intencion not in sin_turnos:
            return _respuesta(
                "Todavía no hay turnos cerrados para analizar: las respuestas aparecen cuando se arquea la primera "
                "guardia con turnos.",
                intencion,
            )
        resultado = metodo()
        if intencion not in ("comparar",):
            resultado.setdefault("entendido", self._entendido(intencion, periodo, categoria_id, conserje_id))
        resultado.setdefault("pregunta_resuelta", self._resuelta(intencion, texto, periodo, categoria_id, conserje_id))
        return resultado

    def aclaracion(self, adivinadas: list[tuple[float, str]]) -> dict:
        opciones = [comprension.PREGUNTA_DE[i] for _, i in adivinadas if i in comprension.PREGUNTA_DE]
        return _respuesta(
            "No estoy seguro de qué me preguntás. ¿Es alguna de estas? Tocala y te respondo.",
            "aclaracion",
            sugerencias=opciones,
        )

    # --- Razonar -----------------------------------------------------------------------------------------------

    def _anterior_alineado(self, periodo: Periodo) -> Periodo:
        """El período anterior equivalente, con los mismos días que el actual tiene arqueados: si esta semana tiene
        datos hasta el miércoles, se compara con lunes a miércoles de la anterior."""
        recortado = self._recortado(periodo) or periodo
        # Menos de una semana se compara con los mismos días de la semana anterior (un martes con otro martes).
        corrimiento = timedelta(days=7 if periodo.dias < 7 else periodo.dias)
        return Periodo(
            recortado.desde - corrimiento, recortado.hasta - corrimiento, "el período anterior", periodo.dias_semana
        )

    def _nombre_anterior(self, periodo: Periodo) -> str:
        recortado = self._recortado(periodo)
        anterior = self._anterior_alineado(periodo)
        if periodo.dias == 1:
            return f"el {ia.DIAS[anterior.desde.weekday()]} anterior ({anterior.desde.day}/{anterior.desde.month})"
        if periodo.dias < 7:
            return f"los mismos días de la semana anterior, {anterior.texto()}"
        if recortado is not None and recortado.hasta < periodo.hasta:
            return f"los mismos días del período anterior, {anterior.texto()}"
        return "el período anterior equivalente"

    def _medidas(self, periodo: Periodo, categoria_id: int | None = None, conserje_id: int | None = None) -> dict:
        turnos = self._turnos(periodo, categoria_id, conserje_id)
        total = sum(t.total for t in turnos)
        return {
            "turnos": turnos,
            "cantidad": len(turnos),
            "ingresos": total,
            "ticket": total / len(turnos) if turnos else 0.0,
            "consumos": sum(t.consumos for t in turnos),
            "perdidos": sum(
                1
                for p in self.ctx.perdidos
                if periodo.contiene(p.momento) and (categoria_id is None or p.categoria_id == categoria_id)
            ),
        }

    def _diferencias(self, actuales, anteriores, clave) -> tuple:
        """Lo que más cambió entre dos listas de turnos, agrupando por `clave` (categoría o día de la semana)."""
        cambio: Counter = Counter()
        for t_ in actuales:
            cambio[clave(t_)] += t_.total
        for t_ in anteriores:
            cambio[clave(t_)] -= t_.total
        if not cambio:
            return None, 0.0
        return max(cambio.items(), key=lambda p: abs(p[1]))

    def _actual_de(self, pasado: Periodo) -> Periodo | None:
        """Para «¿cómo estamos contra el mes pasado?»: el período de ahora del que «el mes pasado» es el anterior."""
        lunes = self.hoy - timedelta(days=self.hoy.weekday())
        for actual in (
            Periodo(self.hoy.replace(day=1), self.hoy, "este mes"),
            Periodo(lunes, self.hoy, "esta semana"),
            Periodo(self.hoy, self.hoy, "hoy"),
            Periodo(date(self.hoy.year, 1, 1), self.hoy, "este año"),
        ):
            anterior = previo_de(actual, self.hoy)
            if (anterior.desde, anterior.hasta) == (pasado.desde, pasado.hasta):
                return actual
        return None

    def _dos_periodos(self, texto: str, periodo: Periodo) -> tuple[Periodo, Periodo]:
        """Los dos períodos que se comparan; el más reciente primero."""
        hallados: list[Periodo] = []
        for parte in re.split(r"\b(?:con|contra|que|y|frente a|respecto (?:al?|del?|de la))\b", texto):
            encontrado = interpretar_periodo(parte, self.hoy)
            if encontrado.explicito:
                if all((encontrado.desde, encontrado.hasta) != (h.desde, h.hasta) for h in hallados):
                    hallados.append(encontrado)
            elif hallados and re.search(r"\b(la|el|lo|los) (pasad[ao]s?|anterior(es)?|previ[ao]s?)\b", parte):
                hallados.append(previo_de(hallados[0], self.hoy))
        if len(hallados) >= 2:
            a, b = hallados[0], hallados[1]
        else:
            base = hallados[0] if hallados else periodo
            actual = self._actual_de(base)
            a, b = (actual, base) if actual is not None else (base, previo_de(base, self.hoy))
        return (b, a) if a.desde < b.desde else (a, b)

    def _alinear(self, a: Periodo, b: Periodo) -> tuple[Periodo | None, Periodo, str | None]:
        """Si el período reciente está a medias (sin arquear hasta el final), se comparan los mismos días del otro."""
        recortado = self._recortado(a)
        if recortado is None or recortado.hasta >= a.hasta:
            return recortado, b, None
        hasta = min(b.desde + timedelta(days=recortado.dias - 1), b.hasta)
        etiqueta = f"del {b.desde.day}/{b.desde.month} al {hasta.day}/{hasta.month}"
        b_etiqueta_original = b.etiqueta
        b = Periodo(b.desde, hasta, etiqueta, b.dias_semana)
        nota = (
            f"Como {a.etiqueta} tiene datos arqueados hasta el {ia.fecha_corta(recortado.hasta)}, comparo los mismos "
            f"{recortado.dias} días de {b_etiqueta_original.split(' (')[0]}, {b.texto()}."
        )
        return recortado, b, nota

    def comparar(self, texto: str, periodo: Periodo, categoria_id: int | None, conserje_id: int | None) -> dict:
        a, b = self._dos_periodos(texto, periodo)
        if self._recortado(b) is None:
            return self._sin_turnos(b, "comparar", "datos para comparar")
        a_alineado, b, nota = self._alinear(a, b)
        if a_alineado is None:
            return self._sin_turnos(a, "comparar", "datos para comparar")
        a = a_alineado
        ma, mb = self._medidas(a, categoria_id, conserje_id), self._medidas(b, categoria_id, conserje_id)
        cambio = ia.variacion(ma["ingresos"], mb["ingresos"])
        cambio_turnos = ia.variacion(ma["cantidad"], mb["cantidad"])
        cambio_ticket = ia.variacion(ma["ticket"], mb["ticket"])
        if cambio is None:
            texto_resp = f"{a.en_mayuscula} se cobraron {ia.pesos(ma['ingresos'])}; {b.en} no hubo turnos cobrados."
        else:
            texto_resp = (
                f"{a.en_mayuscula} se cobraron {ia.pesos(ma['ingresos'])} en {ma['cantidad']} turnos; {b.en}, "
                f"{ia.pesos(mb['ingresos'])} en {mb['cantidad']}."
            )
            if abs(cambio) < 0.02:
                texto_resp += " Prácticamente lo mismo."
            else:
                texto_resp += f" Es {ia.con_signo(cambio)} ({'más' if cambio > 0 else 'menos'})."
                if cambio_turnos is not None and cambio_ticket is not None:
                    if abs(cambio_turnos) >= abs(cambio_ticket):
                        texto_resp += (
                            f" La diferencia viene sobre todo de la cantidad de turnos ({ia.con_signo(cambio_turnos)});"
                            f" el ticket promedio cambió {ia.con_signo(cambio_ticket)}."
                        )
                    else:
                        texto_resp += (
                            f" La diferencia viene sobre todo del ticket promedio ({ia.con_signo(cambio_ticket)}); la "
                            f"cantidad de turnos cambió {ia.con_signo(cambio_turnos)}."
                        )
                if categoria_id is None:
                    clave, diferencia = self._diferencias(ma["turnos"], mb["turnos"], lambda x: x.categoria_id)
                    peso = abs(ma["ingresos"] - mb["ingresos"])
                    if clave is not None and diferencia and abs(diferencia) >= 0.3 * peso:
                        texto_resp += (
                            f" La categoría que más movió es {self.ctx.nombre_categoria(clave)}: "
                            f"{'sumó' if diferencia > 0 else 'restó'} {ia.pesos(abs(diferencia))}."
                        )

        def fila(nombre: str, x: float, y: float, dinero: bool = True) -> list:
            formato = ia.pesos if dinero else (lambda v: f"{v:.0f}")
            return [nombre, formato(x), formato(y), ia.con_signo(ia.variacion(x, y))]

        respuesta = _respuesta(
            texto_resp,
            "comparar",
            detalle=" ".join(
                p for p in (nota, "Turnos cobrados en guardias arqueadas; el ticket es lo cobrado por turno.") if p
            ),
            tabla={
                "columnas": ["", a.texto(), b.texto(), "Cambio"],
                "filas": [
                    fila("Ingresos", ma["ingresos"], mb["ingresos"]),
                    fila("Turnos", ma["cantidad"], mb["cantidad"], False),
                    fila("Ticket promedio", ma["ticket"], mb["ticket"]),
                    fila("Consumos", ma["consumos"], mb["consumos"]),
                    fila("Clientes que se fueron", ma["perdidos"], mb["perdidos"], False),
                ],
            },
            sugerencias=["¿Por qué?", "¿Cuál fue el mejor día del mes?", "¿Cuánto vamos a facturar este mes?"],
        )
        respuesta["entendido"] = f"Comparación · {a.texto()} contra {b.texto()}"
        respuesta["pregunta_resuelta"] = f"compara {a.canonico()} con {b.canonico()}"
        return respuesta

    def _diario(self, desde: date, hasta: date, categoria_id: int | None = None) -> dict[date, list]:
        """Ingresos y turnos de cada día con datos arqueados entre dos fechas (los días sin turnos, en cero)."""
        dias: dict[date, list] = {d: [0.0, 0] for d in self.dias_con_datos if desde <= d <= hasta}
        for t_ in self.ctx.turnos:
            dia = t_.fin.date()
            if desde <= dia <= hasta and (categoria_id is None or t_.categoria_id == categoria_id):
                fila = dias.setdefault(dia, [0.0, 0])
                fila[0] += t_.total
                fila[1] += 1
        return dias

    def proyeccion(self, categoria_id: int | None) -> dict:
        inicio, fin = self.hoy.replace(day=1), _fin_de_mes(self.hoy)
        mes = MESES[self.hoy.month - 1]
        ultimo = min(self.ultimo_dato or inicio - timedelta(days=1), self.hoy)
        hecho = sum(
            t_.total
            for t_ in self.ctx.turnos
            if inicio <= t_.fin.date() <= ultimo and (categoria_id is None or t_.categoria_id == categoria_id)
        )
        historia = self._diario(ultimo - timedelta(days=55), ultimo, categoria_id)
        if len(historia) < 7:
            return _respuesta("Para proyectar el mes necesito al menos una semana de guardias arqueadas.", "proyeccion")
        por_dia_semana: dict[int, list[float]] = {}
        for dia, (importe, _) in historia.items():
            por_dia_semana.setdefault(dia.weekday(), []).append(importe)
        general = mean(v for valores in por_dia_semana.values() for v in valores)
        restantes = [ultimo + timedelta(days=i) for i in range(1, (fin - ultimo).days + 1)]
        restantes = [d for d in restantes if d >= inicio]
        esperado = sum(mean(por_dia_semana.get(d.weekday(), [general])) for d in restantes)
        margen = 1.28 * sum(pstdev(por_dia_semana.get(d.weekday(), [general])) ** 2 for d in restantes) ** 0.5
        esperado, margen = round(esperado, -3), round(margen, -3)
        total = hecho + esperado
        anterior = previo_de(Periodo(inicio, self.hoy, "este mes"), self.hoy)
        total_anterior = sum(t_.total for t_ in self._turnos(anterior, categoria_id))
        sujeto = f" en {self.ctx.nombre_categoria(categoria_id)}" if categoria_id is not None else ""
        if ultimo >= inicio:
            texto = (
                f"A este ritmo, {mes} cerraría{sujeto} en unos {ia.pesos(total)} (entre "
                f"{ia.pesos(max(total - margen, hecho))} y {ia.pesos(total + margen)}). Hasta el "
                f"{ia.fecha_corta(ultimo)} van {ia.pesos(hecho)} arqueados, y para los {len(restantes)} días que"
                f" faltan "
                f"calculo unos {ia.pesos(esperado)}, según lo que suele dejar cada día de la semana."
            )
        else:
            texto = (
                f"Este mes todavía no tiene guardias arqueadas. Si se repite lo que suele dejar cada día de la semana, "
                f"{mes} cerraría{sujeto} en unos {ia.pesos(total)} (entre {ia.pesos(max(total - margen, 0))} y "
                f"{ia.pesos(total + margen)})."
            )
        if total_anterior:
            nombre = anterior.etiqueta.split(" (")[0]
            texto += (
                f" {nombre.capitalize()} cerró en {ia.pesos(total_anterior)}: sería "
                f"{ia.con_signo(ia.variacion(total, total_anterior))}."
            )
        return _respuesta(
            texto,
            "proyeccion",
            detalle="Lo arqueado del mes más el promedio de cada día de la semana en las últimas 8 semanas; el rango "
            "cubre 8 de cada 10 resultados posibles según cuánto varía cada día.",
            sugerencias=[
                "¿Cuál fue el mejor día del mes?",
                "¿Cómo estamos contra el mes pasado?",
                "¿Qué me recomendás?",
            ],
        )

    def dias(self, texto: str, periodo: Periodo, categoria_id: int | None) -> dict:
        recortado = self._recortado(periodo)
        diario = self._diario(recortado.desde, recortado.hasta, categoria_id) if recortado else {}
        if periodo.dias_semana:
            diario = {d: v for d, v in diario.items() if d.weekday() in periodo.dias_semana}
        if recortado is None or not diario:
            return self._sin_turnos(periodo, "dias", "días arqueados")
        por_turnos = bool(re.search(r"gente|turnos|clientes|movimiento|vinieron|entraron|llen", texto))
        indice = 1 if por_turnos else 0
        orden = sorted(diario.items(), key=lambda p: (p[1][indice], p[1][1 - indice]))
        promedio = mean(v[indice] for v in diario.values())
        quiere_peor = bool(re.search(r"\b(peor|flojo|menos)\b", texto))

        def describir(dia: date, valores: list) -> str:
            cuanto = f"{valores[1]} turnos" if por_turnos else f"{ia.pesos(valores[0])} en {valores[1]} turnos"
            return f"{etiqueta_dia(dia, self.hoy)}: {cuanto}"

        def unidad(valor: float) -> str:
            return f"{valor:.0f} turnos" if por_turnos else ia.pesos(valor)

        mejor, peor = orden[-1], orden[0]
        primero, segundo = (peor, mejor) if quiere_peor else (mejor, peor)
        texto_resp = (
            f"{recortado.en_mayuscula}, el {'peor' if quiere_peor else 'mejor'} día fue {describir(*primero)} "
            f"({ia.con_signo(ia.variacion(primero[1][indice], promedio))} contra el promedio de {unidad(promedio)} por "
            f"día). El {'mejor' if quiere_peor else 'más flojo'}, {describir(*segundo)}."
        )
        dias_semana = Counter(d.weekday() for d, _ in orden[::-1][:5])
        if not periodo.dias_semana and len(diario) >= 14 and dias_semana:
            dia, veces = dias_semana.most_common(1)[0]
            if veces >= 3:
                plural = ia.DIAS[dia] if ia.DIAS[dia].endswith("s") else ia.DIAS[dia] + "s"
                texto_resp += f" De los 5 mejores días, {veces} son {plural}."
        top = orden[:5] if quiere_peor else orden[::-1][:5]
        respuesta = _respuesta(
            texto_resp + self._aviso_corte(periodo),
            "dias",
            recortado,
            "Cada día con guardias arqueadas, por la fecha del cobro.",
            {
                "columnas": ["Día", "Ingresos", "Turnos"],
                "filas": [[etiqueta_dia(d, self.hoy).replace("el ", ""), ia.pesos(v[0]), v[1]] for d, v in top],
            },
            ["¿Por qué?", "¿A qué hora hay más demanda?", "¿Cómo estamos contra el mes pasado?"],
        )
        respuesta["entendido"] = f"Mejor y peor día · {recortado.texto()}"
        return respuesta

    def alertas(self) -> dict:
        lista = ia.alertas(self.ctx, ia.reposicion(self.ctx))
        if not lista:
            return _respuesta(
                "No hay nada fuera de lo normal para revisar: todo está dentro de lo esperado.", "alertas"
            )
        importantes = sum(1 for a in lista if a["severidad"] == "alta")
        texto = (
            f"Hay {len(lista)} {'cosa' if len(lista) == 1 else 'cosas'} para revisar"
            + (f", {importantes} importante{'s' if importantes > 1 else ''}" if importantes else "")
            + f". Lo primero: {lista[0]['titulo']}. {lista[0]['detalle']}"
        )
        if lista[0].get("sugerencia"):
            texto += f" {lista[0]['sugerencia']}"
        return _respuesta(
            texto,
            "alertas",
            tabla={
                "columnas": ["Importancia", "Qué", "Detalle"],
                "filas": [
                    [{"alta": "Alta", "media": "Media"}.get(a["severidad"], "Aviso"), a["titulo"], a["detalle"]]
                    for a in lista[:8]
                ],
            },
            detalle="Las mismas alertas de Inteligencia, de los últimos 30 días.",
            sugerencias=["¿Qué me recomendás?", "¿Quién tuvo más faltantes?", "¿Qué artículos hay que reponer?"],
        )

    def _tarifas_a_cambiar(self, categoria_id: int | None = None) -> list[dict]:
        sugeridas = [
            s
            for s in ia.sugerencias_de_tarifa(self.ctx)
            if s["accion"] != "mantener"
            and s["propuesta"]
            and (categoria_id is None or s["categoria_id"] == categoria_id)
        ]
        return sorted(sugeridas, key=lambda s: -(s["impacto_mensual"] or 0))

    def tarifas_sugeridas(self, categoria_id: int | None) -> dict:
        sugeridas = self._tarifas_a_cambiar(categoria_id)
        if not sugeridas:
            return _respuesta(
                "Por ahora no conviene tocar las tarifas: la ocupación y los sobreturnos no muestran una señal clara.",
                "tarifas_sugeridas",
                detalle="Se revisan con los turnos de las últimas 4 semanas.",
                sugerencias=["¿Cuál es la ocupación de los sábados?", "¿Qué me recomendás?"],
            )
        primera = sugeridas[0]
        impacto = f" (unos {ia.pesos(primera['impacto_mensual'])} más por mes)" if primera["impacto_mensual"] else ""
        texto = (
            f"Lo que más conviene: {primera['titulo'][0].lower()}{primera['titulo'][1:]} en {primera['categoria']}"
            f"{impacto}. {primera['explicacion']}"
        )
        if len(sugeridas) > 1:
            otras = len(sugeridas) - 1
            texto += f" Hay {otras} propuesta{'s' if otras > 1 else ''} más en Inteligencia → Tarifas."
        return _respuesta(
            texto,
            "tarifas_sugeridas",
            detalle=primera.get("supuesto") or "Simulación sobre los turnos reales de las últimas 4 semanas.",
            tabla={
                "columnas": ["Categoría", "Qué hacer", "Por mes"],
                "filas": [
                    [s["categoria"], s["titulo"], ia.pesos(s["impacto_mensual"]) if s["impacto_mensual"] else "—"]
                    for s in sugeridas
                ],
            },
            sugerencias=["¿Qué pasa si subo la tarifa 10%?", "¿Qué me recomendás?"],
        )

    def consejos(self) -> dict:
        """Lo que conviene hacer, por orden: lo urgente, lo que más plata deja, lo que se pierde y el stock."""
        reposiciones = ia.reposicion(self.ctx)
        lista = ia.alertas(self.ctx, reposiciones)
        consejos: list[tuple[int, str, str]] = []  # (orden, qué hacer, por qué)
        for alerta in lista:
            if alerta["severidad"] == "alta":
                consejos.append((0, *self._consejo_de(alerta)))
        for s in self._tarifas_a_cambiar()[:2]:
            impacto = f" Unos {ia.pesos(s['impacto_mensual'])} más por mes." if s["impacto_mensual"] else ""
            consejos.append((1, f"{s['titulo']} en {s['categoria']}", s["explicacion"] + impacto))
        desde = self.ctx.corte - timedelta(days=30)
        sin_lugar = sum(1 for p in self.ctx.perdidos if p.momento >= desde and p.motivo == "SIN_LUGAR")
        if sin_lugar >= 5:
            consejos.append(
                (
                    2,
                    "Liberar las habitaciones más rápido en las horas pico",
                    f"En 30 días se fueron {sin_lugar} clientes porque no había lugar. Probá en el simulador cuánto "
                    "cambia si la limpieza tarda menos.",
                )
            )
        urgentes = [r for r in reposiciones if r["urgencia"] == "alta" and r["sugerido"] > 0]
        if urgentes:
            nombres = ", ".join(r["descripcion"] for r in urgentes[:3])
            consejos.append((3, f"Reponer {nombres}", "Se agota antes de dos semanas al ritmo de venta actual."))
        for alerta in lista:
            if alerta["severidad"] == "media" and alerta.get("sugerencia"):
                consejos.append((4, *self._consejo_de(alerta)))
        if not consejos:
            return _respuesta(
                "Por ahora no veo nada que cambiar: no hay alertas importantes, las tarifas están en equilibrio y el "
                "stock alcanza.",
                "consejos",
                sugerencias=["¿Cómo estamos contra el mes pasado?", "¿Cuánto vamos a facturar este mes?"],
            )
        vistos: set[str] = set()
        elegidos: list[tuple[str, str]] = []
        for _, que, por_que in sorted(consejos, key=lambda c: c[0]):
            if que not in vistos:
                vistos.add(que)
                elegidos.append((que, por_que))
        elegidos = elegidos[:4]
        texto = "Te recomiendo, por orden: " + " ".join(
            f"{n}) {que.rstrip('.')}." for n, (que, _) in enumerate(elegidos, start=1)
        )
        return _respuesta(
            texto,
            "consejos",
            tabla={"columnas": ["Qué hacer", "Por qué"], "filas": [[q, p] for q, p in elegidos]},
            detalle="Sale de las alertas, las tarifas sugeridas, los clientes que se fueron y el stock.",
            sugerencias=[
                "¿Qué tarifa conviene subir?",
                "¿Qué alertas hay?",
                "¿Qué pasa si la limpieza tarda 20 minutos?",
            ],
        )

    @staticmethod
    def _consejo_de(alerta: dict) -> tuple[str, str]:
        """(qué hacer, por qué) a partir de una alerta: lo que pasa, y después qué conviene hacer."""
        sugerencia = alerta.get("sugerencia")
        que = alerta["titulo"]
        if sugerencia:
            que += f" — {sugerencia[0].lower()}{sugerencia[1:]}"
        return que, alerta["detalle"]

    def explicacion(self, previo: str) -> dict:
        """«¿Por qué?» después de una respuesta: de dónde sale el número o el cambio."""
        intencion = self._intencion(previo) or "ingresos"
        periodo = interpretar_periodo(previo, self.hoy)
        categoria_id, conserje_id = self._categoria(previo), self._conserje(previo)
        if intencion == "caja":
            return self._explicar_caja(periodo)
        if intencion == "comparar":
            a, b = self._dos_periodos(previo, periodo)
        else:
            a, b = periodo, previo_de(periodo, self.hoy)
        razones = []
        a_alineado, b, _ = self._alinear(a, b)
        if a_alineado is None:
            return self._sin_turnos(a, "explicacion", "datos arqueados")
        if a_alineado.hasta < a.hasta:
            faltan = (a.hasta - a_alineado.hasta).days
            razones.append(
                f"Lo principal: hay datos arqueados solo hasta el {ia.fecha_corta(a_alineado.hasta)}, así que {faltan} "
                f"de los {a.dias} días todavía no cuentan. Comparo los mismos días de los dos períodos."
            )
        a = a_alineado
        ma, mb = self._medidas(a, categoria_id, conserje_id), self._medidas(b, categoria_id, conserje_id)
        cambio = ia.variacion(ma["ingresos"], mb["ingresos"])
        if cambio is None:
            return _respuesta(f"No tengo con qué compararlo: {b.en} no hubo turnos cobrados.", "explicacion", a)
        cambio_turnos = ia.variacion(ma["cantidad"], mb["cantidad"])
        cambio_ticket = ia.variacion(ma["ticket"], mb["ticket"])
        razones.append(
            f"{a.en_mayuscula} se cobraron {ia.pesos(ma['ingresos'])} y {b.en}, {ia.pesos(mb['ingresos'])} "
            f"({ia.con_signo(cambio)})."
        )
        if cambio_turnos is not None and cambio_ticket is not None:
            pesa = "la cantidad de turnos" if abs(cambio_turnos) >= abs(cambio_ticket) else "el ticket promedio"
            razones.append(
                f"Los turnos cambiaron {ia.con_signo(cambio_turnos)} ({ma['cantidad']} contra {mb['cantidad']}) y el "
                f"ticket promedio {ia.con_signo(cambio_ticket)} ({ia.pesos(ma['ticket'])} contra "
                f"{ia.pesos(mb['ticket'])}): pesa más {pesa}."
            )
        if a.dias >= 7:
            dia, diferencia = self._diferencias(ma["turnos"], mb["turnos"], lambda x: x.fin.weekday())
            if dia is not None and diferencia:
                razones.append(
                    f"El día de la semana que más cambió es el {ia.DIAS[dia]} "
                    f"({'+' if diferencia > 0 else '−'}{ia.pesos(abs(diferencia))})."
                )
        if categoria_id is None:
            clave, diferencia = self._diferencias(ma["turnos"], mb["turnos"], lambda x: x.categoria_id)
            if clave is not None and diferencia:
                razones.append(
                    f"Por categoría, la que más movió es {self.ctx.nombre_categoria(clave)} "
                    f"({'+' if diferencia > 0 else '−'}{ia.pesos(abs(diferencia))})."
                )
        if ma["perdidos"] > mb["perdidos"] + 2:
            razones.append(f"Además se fueron más clientes sin quedarse: {ma['perdidos']} contra {mb['perdidos']}.")
        respuesta = _respuesta(
            " ".join(razones),
            "explicacion",
            a,
            detalle=f"Compara {a.texto()} con {b.texto()}, con turnos cobrados en guardias arqueadas.",
            sugerencias=["¿Es mucho?", "¿Qué me recomendás?", "¿Cuál fue el mejor día del mes?"],
        )
        respuesta["entendido"] = f"Por qué cambió · {a.texto()} contra {b.texto()}"
        respuesta["pregunta_resuelta"] = previo
        return respuesta

    def _explicar_caja(self, periodo: Periodo) -> dict:
        arqueos = [a for a in self.ctx.arqueos if periodo.contiene(a.momento) and a.categoria == FALTANTE]
        if not arqueos:
            return _respuesta(f"{periodo.en_mayuscula} no hubo faltantes en la caja.", "explicacion", periodo)
        quien, veces = Counter(a.operador_id for a in arqueos).most_common(1)[0]
        texto = (
            f"De los {len(arqueos)} arqueos con faltante, {veces} son de {self.ctx.nombres.get(quien, '—')} "
            f"({ia.porcentaje(veces / len(arqueos))})."
        )
        dia, en_dia = Counter(a.momento.weekday() for a in arqueos).most_common(1)[0]
        if en_dia >= 3:
            texto += f" Se repiten los {ia.DIAS[dia]}: {en_dia} faltantes."
        texto += " Conviene mirar esas guardias en Control de caja antes de sacar conclusiones."
        return _respuesta(texto, "explicacion", periodo, sugerencias=["¿Qué alertas hay?"])

    def valoracion(self, previo: str) -> dict:
        """«¿Es mucho?»: el número de la respuesta anterior contra lo normal del motel en períodos parecidos."""
        intencion = self._intencion(previo) or "ingresos"
        periodo = interpretar_periodo(previo, self.hoy)
        categoria_id = self._categoria(previo)
        clave = {"turnos": "cantidad", "ticket": "ticket"}.get(intencion, "ingresos")
        recortado = self._recortado(periodo)
        if recortado is None:
            return self._sin_turnos(periodo, "valoracion", "datos arqueados")
        # Un período corto se compara con el mismo tramo de las semanas anteriores (mismo día de la semana); uno largo,
        # por día, con cada una de las 8 semanas anteriores.
        por_dia = recortado.dias >= 7 and clave != "ticket"
        divisor = recortado.dias if por_dia else 1
        valor = self._medidas(recortado, categoria_id)[clave] / divisor
        valores = []
        for k in range(1, 9):
            if por_dia:
                fin = recortado.desde - timedelta(days=7 * (k - 1) + 1)
                otro = Periodo(fin - timedelta(days=6), fin, "")
            else:
                paso = timedelta(days=7 * k)
                otro = Periodo(recortado.desde - paso, recortado.hasta - paso, "", periodo.dias_semana)
            if self.primer_dato is None or otro.desde < self.primer_dato:
                break
            valores.append(self._medidas(otro, categoria_id)[clave] / (7 if por_dia else 1))
        if len(valores) < 3:
            return _respuesta(
                "Todavía no hay historia suficiente para decir si es mucho o poco: necesito al menos tres períodos "
                "parecidos con datos.",
                "valoracion",
                recortado,
            )
        tipico = median(valores)
        mejores = sum(1 for v in valores if v > valor)
        cambio = ia.variacion(valor, tipico) or 0.0
        # El juicio mira las dos cosas: cuánto se aparta de lo típico y en qué puesto queda.
        puesto = mejores / len(valores)
        if mejores == 0:
            juicio = f"Es muy bueno: ninguna de las {len(valores)} semanas anteriores lo superó."
        elif mejores == len(valores):
            juicio = f"Es bajo: las {len(valores)} semanas anteriores lo superaron."
        elif cambio >= 0.1 or (puesto <= 0.25 and cambio > 0):
            juicio = "Es más que lo habitual."
        elif cambio <= -0.1 or (puesto >= 0.75 and cambio < 0):
            juicio = "Es algo menos que lo habitual."
        else:
            juicio = "Está dentro de lo normal."

        def formato(v: float) -> str:
            texto = f"{v:.0f} turnos" if clave == "cantidad" else ia.pesos(v)
            return f"{texto} por día" if por_dia else texto

        tramo = "día" if recortado.dias == 1 else "tramo"
        comparadas = "semanas anteriores" if por_dia else f"semanas anteriores en el mismo {tramo}"
        respuesta = _respuesta(
            f"{juicio} {recortado.en_mayuscula} dio {formato(valor)}; lo típico en las {len(valores)} {comparadas} es "
            f"{formato(tipico)} ({ia.con_signo(cambio)}), y {mejores} de {len(valores)} fueron mejores.",
            "valoracion",
            recortado,
            detalle="Compara con el mismo tramo corrido hacia atrás, con la mediana como valor típico.",
            sugerencias=["¿Por qué?", "¿Qué me recomendás?"],
        )
        respuesta["entendido"] = f"Si es mucho o poco · {recortado.texto()}"
        respuesta["pregunta_resuelta"] = previo
        return respuesta

    def ayuda(self) -> dict:
        return _respuesta(
            "Soy Mot, el asistente de MotelOS. Respondo con los datos del motel, calculados acá mismo (nada sale de "
            "esta computadora). Probá preguntar por ingresos, turnos, ocupación, estadías, horarios, categorías, "
            "habitaciones, caja, artículos o el pronóstico. Podés agregar un período («ayer», «la semana pasada», "
            "«en octubre», «los sábados», «últimos 15 días»), una categoría o un conserje.",
            "ayuda",
            sugerencias=SUGERENCIAS,
        )

    def resumen(self) -> dict:
        kpis = ia.indicadores(self.ctx)
        reposiciones = ia.reposicion(self.ctx)
        lista = ia.alertas(self.ctx, reposiciones)
        datos = ia.resumen(self.ctx, kpis, ia.pronostico(self.ctx), lista, ia.mapa_demanda(self.ctx), reposiciones)
        texto = datos["titular"] + " " + " ".join(p["texto"] for p in datos["puntos"])
        return _respuesta(texto, "resumen", sugerencias=["¿Qué alertas hay?", "¿Cuántos turnos esperamos mañana?"])

    def gemelo(self, texto: str, categoria_id: int | None) -> dict:
        """«¿Qué pasa si la limpieza tarda 20 minutos?», «si agrego una VIP», «si subo la tarifa 10%»."""
        _, limpieza_actual = simulador.llegadas_de(self.ctx, 30)
        limpieza = None
        if m := re.search(r"(\d{1,3}) min\w* menos", texto):
            limpieza = max(limpieza_actual - int(m.group(1)), 1.0)
        elif m := re.search(r"limpieza\D{0,30}?(\d{1,3})", texto):
            limpieza = float(m.group(1))
        cambios: dict[int, int] = {}
        if m := re.search(r"(agreg|sum|tuviera|hubiera|constru)\w* (una|un|dos|tres|cuatro|\d+)\b", texto):
            palabras = {"una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4}
            cantidad = palabras.get(m.group(2)) or int(m.group(2))
            if categoria_id is None and self.ctx.perdidos:
                pedidas = Counter(p.categoria_id for p in self.ctx.perdidos if p.categoria_id is not None)
                categoria_id = pedidas.most_common(1)[0][0] if pedidas else None
            if categoria_id is None and self.ctx.categorias:
                categoria_id = next(iter(self.ctx.categorias))
            if categoria_id is not None:
                cambios[categoria_id] = cantidad
        precio = 0.0
        if (m := re.search(r"(sub|aument|baj)\w*\D{0,30}?(\d{1,2})\b", texto)) and re.search(r"precio|tarifa", texto):
            precio = float(m.group(2)) * (-1 if m.group(1) == "baj" else 1)
        if limpieza is None and not cambios and not precio:
            return _respuesta(
                "Puedo probar un cambio sobre lo que pasó de verdad, sin tocar nada. Decime qué querés cambiar: la "
                "limpieza, las habitaciones o el precio.",
                "gemelo",
                sugerencias=[
                    "¿Qué pasa si la limpieza tarda 20 minutos?",
                    "¿Qué pasa si agrego una VIP?",
                    "¿Qué pasa si subo la tarifa 10%?",
                ],
            )
        resultado = simulador.simular(self.ctx, simulador.Escenario(limpieza, cambios, precio))
        if not resultado["disponible"]:
            return _respuesta(resultado["conclusion"], "gemelo")
        base, nuevo = resultado["base"], resultado["escenario"]
        coincidencia = resultado["calibracion"]["coincidencia"]
        return _respuesta(
            resultado["conclusion"],
            "gemelo",
            detalle=f"Repite los últimos {resultado['dias']} días. Con las condiciones de hoy el modelo reproduce "
            f"{ia.porcentaje(coincidencia)} de los turnos reales. No descuenta costos.",
            tabla={
                "columnas": ["", "Hoy", "Con el cambio"],
                "filas": [
                    ["Turnos", base["turnos"], nuevo["turnos"]],
                    ["Clientes perdidos", base["perdidos"], nuevo["perdidos"]],
                    ["Ingresos", ia.pesos(base["ingresos"]), ia.pesos(nuevo["ingresos"])],
                ],
            },
            sugerencias=["¿Cuántos clientes perdimos?", "¿Cuánto tarda la limpieza?"],
        )

    def opiniones(self) -> dict:
        datos = ia.opiniones(self.ctx)
        if not datos["cantidad"]:
            return _respuesta(
                f"En los últimos {datos['dias']} días ningún cliente calificó su estadía.",
                "opiniones",
                detalle="Se califica desde la página del QR del ticket, de forma anónima.",
            )
        promedio = str(datos["promedio"]).replace(".", ",")
        texto = (
            f"En los últimos {datos['dias']} días calificaron {datos['cantidad']} clientes, con {promedio} de 5 de "
            "promedio."
        )
        if datos["problemas"]:
            texto += f" Lo que más marcan: {datos['problemas'][0]['problema'].lower()}."
        peores = datos["habitaciones"][:5]
        return _respuesta(
            texto,
            "opiniones",
            tabla={
                "columnas": ["Habitación", "Promedio", "Opiniones", "Lo que más marcan"],
                "filas": [
                    [f["numero"], str(f["promedio"]).replace(".", ","), f["cantidad"], f["problema"] or "—"]
                    for f in peores
                ],
            }
            if peores
            else None,
            detalle="Son anónimas: solo se ven totales, nunca una opinión suelta.",
            sugerencias=["¿Cuánto tarda la limpieza?", "¿Qué habitación se usa menos?"],
        )

    def ropa(self) -> dict:
        datos = ia.operacion(self.ctx)
        contadas = [r for r in datos["ropa"] if r["total"] is not None]
        if not contadas:
            return _respuesta("Todavía no se hizo ningún recuento de toallas y sábanas.", "ropa")
        cuanto = " y ".join(f"{r['total']} {r['etiqueta'].lower()}" for r in contadas)
        texto = f"Según el último recuento hay {cuanto}."
        faltas = datos["faltas"]
        if faltas:
            unidades = -sum(d["diferencia"] for d in faltas)
            texto += f" En los últimos {datos['dias']} días faltaron {unidades} en {len(faltas)} recuentos."
        else:
            texto += f" En los últimos {datos['dias']} días los recuentos coinciden."
        return _respuesta(
            texto,
            "ropa",
            tabla={
                "columnas": ["Cuándo", "Qué", "Diferencia", "Contaron"],
                "filas": [
                    [
                        datetime.fromisoformat(d["creado_en"]).astimezone(self.ctx.zona).strftime("%d/%m %H:%M"),
                        d["etiqueta"],
                        d["diferencia"],
                        d["operador"]
                        if d["operador"] == d["anterior_por"]
                        else f"{d['anterior_por']} y {d['operador']}",
                    ]
                    for d in faltas[:6]
                ],
            }
            if faltas
            else None,
            detalle="Lo que salió a la lavandería o se dio de baja no cuenta como faltante si se anotó.",
            sugerencias=["¿Qué habitación se rompe más?", "¿Cuánto gastamos en arreglos?"],
        )

    def arreglos(self, pregunta: str) -> dict:
        datos = ia.operacion(self.ctx)
        sin_resolver = len(datos["sin_resolver"])
        if not datos["resueltos"] and not sin_resolver:
            return _respuesta(f"En los últimos {datos['dias']} días no se registraron arreglos.", "arreglos")
        texto = (
            f"En los últimos {datos['dias']} días se resolvieron {datos['resueltos']} arreglos, por "
            f"{ia.pesos(datos['gastado'])}."
        )
        if sin_resolver:
            texto += " Queda uno sin resolver." if sin_resolver == 1 else f" Quedan {sin_resolver} sin resolver."
        filas = datos["por_habitacion"][:5]
        if filas and re.search(r"(rompe|falla|arregl)\w* mas|mas (se )?(rompe|falla)|mas fallas", pregunta):
            peor = filas[0]
            texto = (
                f"La {peor['numero']}: {peor['fallas']} fallas en {datos['dias']} días, sobre todo "
                f"{peor['rubro'].lower()}. {texto}"
            )
        return _respuesta(
            texto,
            "arreglos",
            tabla={
                "columnas": ["Habitación", "Fallas", "Lo que más se repite", "Costo"],
                "filas": [[f["numero"], f["fallas"], f["rubro"], ia.pesos(f["costo"])] for f in filas],
            }
            if filas
            else None,
            detalle=f"{datos['sin_costo']} resueltos todavía no tienen costo cargado." if datos["sin_costo"] else None,
            sugerencias=["¿Faltan toallas?", "¿Qué arreglos hay abiertos?"],
        )

    def perdidos(self, periodo: Periodo, categoria_id: int | None) -> dict:
        perdidos = [
            p
            for p in self.ctx.perdidos
            if periodo.contiene(p.momento) and (categoria_id is None or p.categoria_id == categoria_id)
        ]
        cuando = periodo.en_mayuscula
        if not perdidos:
            return _respuesta(
                f"{cuando} no se registraron clientes que se fueran sin quedarse.{self._aviso_corte(periodo)}",
                "perdidos",
                periodo,
                detalle="Los registra el conserje con «Se fue un cliente» en Habitaciones.",
            )
        turnos = self._turnos(periodo)
        ticket = sum(t.total for t in turnos) / len(turnos) if turnos else 0.0
        motivos = Counter(p.motivo for p in perdidos)
        filas = [[MOTIVOS.get(m, m), c] for m, c in motivos.most_common()]
        valor = f", unos {ia.pesos(len(perdidos) * ticket)} al ticket promedio" if ticket else ""
        return _respuesta(
            f"{cuando} se fueron {len(perdidos)} clientes sin quedarse{valor}.{self._aviso_corte(periodo)}",
            "perdidos",
            periodo,
            tabla={"columnas": ["Motivo", "Clientes"], "filas": filas},
            sugerencias=["¿Cuánto tarda la limpieza?", "¿Y la semana pasada?", "¿A qué hora hay más demanda?"],
        )

    def ingresos(self, texto: str, periodo: Periodo, categoria_id: int | None, conserje_id: int | None) -> dict:
        if (
            re.search(r"que categoria|por categoria|cual categoria|cada categoria|categorias", texto)
            and categoria_id is None
        ):
            turnos = self._turnos(periodo)
            tabla = self._por_categoria(turnos)
            if not tabla["filas"]:
                return self._sin_turnos(periodo, "ingresos")
            primera = tabla["filas"][0]
            return _respuesta(
                f"{periodo.en_mayuscula}, la categoría que más ingresos dejó es {primera[0]}: {primera[2]} en "
                f"{primera[1]} turnos (ticket promedio {primera[3]}).{self._aviso_corte(periodo)}",
                "ingresos",
                periodo,
                "Suma de lo cobrado por turno (estadía, sobreturno y consumos) en guardias ya arqueadas.",
                tabla,
                ["¿Qué categoría tiene más ocupación?", "¿Cuánto dura una estadía en cada categoría?"],
            )
        turnos = self._turnos(periodo, categoria_id, conserje_id)
        anteriores = self._turnos(self._anterior_alineado(periodo), categoria_id, conserje_id)
        total, total_ant = sum(t.total for t in turnos), sum(t.total for t in anteriores)
        sujeto = ""
        if categoria_id is not None:
            sujeto += f" en {self.ctx.nombre_categoria(categoria_id)}"
        if conserje_id is not None:
            sujeto += f" cobrados por {self.ctx.nombres.get(conserje_id, '—')}"
        if not turnos:
            return self._sin_turnos(periodo, "ingresos", sujeto=sujeto)
        cambio = ia.variacion(total, total_ant)
        comparacion = (
            f" Es {ia.con_signo(cambio)} contra {self._nombre_anterior(periodo)}, que dejó {ia.pesos(total_ant)}."
            if cambio is not None
            else ""
        )
        consumos = sum(t.consumos for t in turnos)
        return _respuesta(
            f"{periodo.en_mayuscula} se cobraron {ia.pesos(total)}{sujeto} en {len(turnos)} turnos (ticket promedio "
            f"{ia.pesos(total / len(turnos))}); {ia.pesos(consumos)} fueron consumos.{comparacion}"
            f"{self._aviso_corte(periodo)}",
            "ingresos",
            periodo,
            "Suma del total de cada turno cobrado en guardias ya arqueadas, por la fecha del cobro.",
            self._por_categoria(turnos) if categoria_id is None else None,
            ["¿Qué categoría deja más plata?", "¿Cómo pagan los clientes?"],
        )

    def turnos(self, periodo: Periodo, categoria_id: int | None, conserje_id: int | None) -> dict:
        turnos = self._turnos(periodo, categoria_id, conserje_id)
        anteriores = self._turnos(self._anterior_alineado(periodo), categoria_id, conserje_id)
        sujeto = f" en {self.ctx.nombre_categoria(categoria_id)}" if categoria_id is not None else ""
        if conserje_id is not None:
            sujeto += f" cobrados por {self.ctx.nombres.get(conserje_id, '—')}"
        if not turnos:
            return self._sin_turnos(periodo, "turnos", "turnos", sujeto)
        dias = len({t.fin.date() for t in turnos}) or 1
        cambio = ia.variacion(len(turnos), len(anteriores))
        return _respuesta(
            f"{periodo.en_mayuscula} hubo {len(turnos)} turnos{sujeto}"
            + (f", unos {len(turnos) / dias:.0f} por día" if periodo.dias > 1 and turnos else "")
            + (f"; {ia.con_signo(cambio)} contra {self._nombre_anterior(periodo)}." if cambio is not None else ".")
            + self._aviso_corte(periodo),
            "turnos",
            periodo,
            "Turnos finalizados y cobrados en guardias ya arqueadas.",
            self._por_categoria(turnos) if categoria_id is None and turnos else None,
            ["¿A qué hora hay más demanda?", "¿Cuántos turnos esperamos mañana?"],
        )

    def ticket(self, periodo: Periodo, categoria_id: int | None) -> dict:
        turnos = self._turnos(periodo, categoria_id)
        if not turnos:
            return self._sin_turnos(periodo, "ticket")
        promedio = sum(t.total for t in turnos) / len(turnos)
        consumos = sum(t.consumos for t in turnos) / len(turnos)
        sujeto = f" en {self.ctx.nombre_categoria(categoria_id)}" if categoria_id is not None else ""
        return _respuesta(
            f"El ticket promedio{sujeto} {periodo.en} fue de {ia.pesos(promedio)} por turno, de los que "
            f"{ia.pesos(consumos)} son consumos del minibar.",
            "ticket",
            periodo,
            "Total cobrado dividido la cantidad de turnos.",
            self._por_categoria(turnos) if categoria_id is None else None,
        )

    def estadia(self, periodo: Periodo, categoria_id: int | None) -> dict:
        turnos = self._turnos(periodo, categoria_id)
        if not turnos:
            return self._sin_turnos(periodo, "estadia", "estadías cerradas")
        minutos = [t.minutos for t in turnos]
        sujeto = f" en {self.ctx.nombre_categoria(categoria_id)}" if categoria_id is not None else ""
        grupos: dict[int, list[float]] = {}
        for t in turnos:
            grupos.setdefault(t.categoria_id, []).append(t.minutos)
        tabla = {
            "columnas": ["Categoría", "Promedio", "Mediana", "Con sobreturno"],
            "filas": [
                [
                    self.ctx.nombre_categoria(c),
                    ia.minutos_texto(mean(ms)),
                    ia.minutos_texto(median(ms)),
                    ia.porcentaje(sum(1 for t in turnos if t.categoria_id == c and t.sobreturno > 0) / len(ms)),
                ]
                for c, ms in grupos.items()
            ],
        }
        return _respuesta(
            f"Una estadía{sujeto} dura en promedio {ia.minutos_texto(mean(minutos))} (la mitad dura menos de "
            f"{ia.minutos_texto(median(minutos))}) {periodo.en}. "
            f"{ia.porcentaje(sum(1 for t in turnos if t.sobreturno > 0) / len(turnos))} paga sobreturno.",
            "estadia",
            periodo,
            "Desde la apertura hasta el cobro de cada turno.",
            tabla if categoria_id is None else None,
        )

    def sobreturno(self, periodo: Periodo, categoria_id: int | None) -> dict:
        turnos = self._turnos(periodo, categoria_id)
        if not turnos:
            return self._sin_turnos(periodo, "sobreturno")
        con = [t for t in turnos if t.sobreturno > 0]
        importe = sum(t.sobreturno for t in con)
        return _respuesta(
            f"{periodo.en_mayuscula}, {len(con)} de {len(turnos)} turnos ({ia.porcentaje(len(con) / len(turnos))}) "
            f"pagaron sobreturno, por {ia.pesos(importe)} en total "
            f"({ia.porcentaje(importe / (sum(t.total for t in turnos) or 1))} de los ingresos).",
            "sobreturno",
            periodo,
            "Importe de sobreturno de cada turno con su tarifa (RN-DER-01).",
            sugerencias=["¿Cuánto dura una estadía promedio?", "¿Qué tarifa conviene cambiar?"],
        )

    def ocupacion(self, periodo: Periodo, categoria_id: int | None) -> dict:
        inicio = self.ctx.inicio_dia(periodo.desde)
        fin = min(self.ctx.inicio_dia(periodo.hasta + timedelta(days=1)), self.ctx.corte)
        if fin <= inicio:
            ocupadas = sum(1 for h in self.ctx.habitaciones if h.estado == "Ocupada")
            return _respuesta(
                f"Ahora hay {ocupadas} de {len(self.ctx.habitaciones)} habitaciones ocupadas. La ocupación del día se "
                "calcula cuando se arquea la guardia en curso.",
                "ocupacion",
                periodo,
            )
        ventanas = [(inicio, fin)]
        if periodo.dias_semana:
            ventanas = [
                (self.ctx.inicio_dia(d), min(self.ctx.inicio_dia(d + timedelta(days=1)), self.ctx.corte))
                for d in (periodo.desde + timedelta(days=i) for i in range(periodo.dias))
                if d.weekday() in periodo.dias_semana and self.ctx.inicio_dia(d) < self.ctx.corte
            ]
        filas = []
        for c in sorted({h.categoria_id for h in self.ctx.habitaciones}):
            if categoria_id is not None and c != categoria_id:
                continue
            cupo = sum(1 for h in self.ctx.habitaciones if h.categoria_id == c)
            valor = ia.ocupacion([t for t in self.ctx.turnos if t.categoria_id == c], ventanas, cupo)
            filas.append([self.ctx.nombre_categoria(c), cupo, ia.porcentaje(valor or 0)])
        turnos = [t for t in self.ctx.turnos if categoria_id is None or t.categoria_id == categoria_id]
        cupo = sum(1 for h in self.ctx.habitaciones if categoria_id is None or h.categoria_id == categoria_id)
        general = ia.ocupacion(turnos, ventanas, cupo) or 0
        sujeto = f" de {self.ctx.nombre_categoria(categoria_id)}" if categoria_id is not None else ""
        return _respuesta(
            f"{periodo.en_mayuscula}, las habitaciones{sujeto} estuvieron ocupadas el {ia.porcentaje(general)} del "
            "tiempo.",
            "ocupacion",
            periodo,
            "Minutos con un turno abierto sobre los minutos disponibles de cada habitación.",
            {"columnas": ["Categoría", "Habitaciones", "Ocupación"], "filas": filas} if categoria_id is None else None,
            ["¿A qué hora hay más demanda?", "¿Qué tarifa conviene cambiar?"],
        )

    def horas(self, periodo: Periodo) -> dict:
        if not periodo.explicito:
            periodo = Periodo(self.hoy - timedelta(weeks=8), self.hoy, "las últimas 8 semanas")
        turnos = [t for t in self.ctx.turnos if periodo.contiene(t.inicio)]
        if not turnos:
            return _respuesta(f"No hay turnos {periodo.en}.", "horas", periodo)
        por_hora = Counter(t.inicio.hour for t in turnos)
        por_dia = Counter(t.inicio.weekday() for t in turnos)
        mejores = [f"{h} h" for h, _ in por_hora.most_common(3)]
        texto = f"{periodo.en_mayuscula}, las horas con más llegadas son las {', '.join(mejores)}."
        if not periodo.dias_semana and len(por_dia) > 1:
            fuerte = max(por_dia, key=por_dia.get)
            flojo = min(por_dia, key=por_dia.get)
            texto += f" El día más fuerte es el {ia.DIAS[fuerte]} y el más flojo, el {ia.DIAS[flojo]}."
        flojas = sorted(range(24), key=lambda h: por_hora.get(h, 0))[:3]
        texto += f" Las horas más tranquilas: {', '.join(f'{h} h' for h in sorted(flojas))}."
        tabla = {
            "columnas": ["Hora", "Llegadas"],
            "filas": [[f"{h} h", n] for h, n in sorted(por_hora.most_common(6))],
        }
        return _respuesta(
            texto,
            "horas",
            periodo,
            "Hora de apertura de cada turno (hora local).",
            tabla,
            ["¿Cuántos turnos esperamos mañana?", "¿Cuál es la ocupación de los sábados?"],
        )

    def pronostico(self, texto: str) -> dict:
        if re.search(r"\bmanana\b", texto) and not re.search(r"\bla manana\b|\bpor la manana\b", texto):
            dia = self.hoy + timedelta(days=1)
            esperado = ia.llegadas_del_dia(self.ctx, dia)
            return _respuesta(
                f"Para mañana ({ia.fecha_corta(dia)}) se esperan unos {esperado:.0f} turnos, según el patrón de los "
                f"{ia.DIAS[dia.weekday()]} de las últimas semanas y la tendencia reciente.",
                "pronostico",
                detalle="Promedio ponderado de la misma hora en las 8 semanas anteriores (lo más "
                "reciente pesa más), ajustado por la tendencia de las últimas dos semanas.",
                sugerencias=["¿A qué hora hay más demanda los sábados?", "¿Qué artículos hay que reponer?"],
            )
        pron = ia.pronostico(self.ctx)
        if not pron["horas"]:
            return _respuesta("Todavía no hay historia suficiente para pronosticar.", "pronostico")
        texto_resp = (
            f"En las próximas 24 horas se esperan unos {pron['total']:.0f} turnos (entre {pron['minimo']} y "
            f"{pron['maximo']}), con el pico de llegadas a las {pron['pico']['etiqueta']}."
        )
        for s in pron["saturacion"][:2]:
            desde, hasta = datetime.fromisoformat(s["desde"]), datetime.fromisoformat(s["hasta"])
            texto_resp += f" {s['categoria']} se llenaría entre las {desde.hour} y las {hasta.hour} h."
        precision = pron["precision"]
        detalle = "Promedio ponderado de la misma hora en las 8 semanas anteriores, ajustado por la tendencia."
        if precision:
            detalle += (
                f" Error medio del método en los últimos {precision['dias']} días: "
                f"{ia.porcentaje(precision['error_medio'])}."
            )
        return _respuesta(
            texto_resp,
            "pronostico",
            detalle=detalle,
            sugerencias=["¿Cuántos turnos esperamos mañana?", "¿Qué artículos hay que reponer?"],
        )

    def stock(self, texto: str) -> dict:
        lista = ia.reposicion(self.ctx)
        pedir = [r for r in lista if r["sugerido"] > 0]
        if not pedir:
            return _respuesta(
                "No hace falta reponer nada por ahora: todo el stock cubre al menos dos semanas.", "stock"
            )
        urgentes = [r for r in pedir if r["urgencia"] == "alta"]
        texto_resp = f"Conviene reponer {len(pedir)} artículos para cubrir dos semanas."
        if urgentes:
            texto_resp += (
                " Los más urgentes: "
                + ", ".join(
                    f"{r['descripcion']} (se agota en {r['dias_restantes']:.0f} días)".replace("en 0 días", "hoy")
                    for r in urgentes[:3]
                )
                + "."
            )
        tabla = {
            "columnas": ["Artículo", "Stock", "Venta por día", "Pedir"],
            "filas": [[r["descripcion"], r["stock"], f"{r['por_dia']:.1f}", r["sugerido"]] for r in pedir[:8]],
        }
        return _respuesta(
            texto_resp,
            "stock",
            detalle="Venta de los últimos 28 días (la última semana pesa el doble) y "
            "stock cargado; el pedido redondea a packs de 6.",
            tabla=tabla,
        )

    def articulos(self, texto: str, periodo: Periodo) -> dict:
        for a in self.ctx.articulos:
            palabras = [p for p in normalizar(a.descripcion).split() if len(p) > 3]
            if palabras and any(re.search(rf"\b{re.escape(p)}", texto) for p in palabras[:2]):
                ventas = [v for v in self.ctx.ventas if v.articulo_id == a.id and periodo.contiene(v.momento)]
                unidades = sum(v.cantidad for v in ventas)
                reposicion = next((r for r in ia.reposicion(self.ctx) if r["articulo_id"] == a.id), None)
                extra = ""
                if reposicion and reposicion["dias_restantes"] is not None:
                    extra = (
                        f" Quedan {a.stock_actual} unidades: alcanzan para unos "
                        f"{reposicion['dias_restantes']:.0f} días."
                    )
                return _respuesta(
                    f"De «{a.descripcion}» se vendieron {unidades} unidades {periodo.en} "
                    f"({ia.pesos(sum(v.subtotal for v in ventas))}).{extra}",
                    "articulos",
                    periodo,
                )
        unidades, importe = Counter(), Counter()
        for v in self.ctx.ventas:
            if periodo.contiene(v.momento):
                unidades[v.articulo_id] += v.cantidad
                importe[v.articulo_id] += v.subtotal
        if not unidades:
            return _respuesta(f"No hubo consumos {periodo.en}.", "articulos", periodo)
        nombre = {a.id: a.descripcion for a in self.ctx.articulos}
        top = unidades.most_common(5)
        return _respuesta(
            f"Lo más vendido {periodo.en}: "
            + ", ".join(f"{nombre.get(a, a)} ({u})" for a, u in top[:3])
            + f". En total, {sum(unidades.values())} unidades por {ia.pesos(sum(importe.values()))}.",
            "articulos",
            periodo,
            "Consumos cargados a los turnos.",
            {
                "columnas": ["Artículo", "Unidades", "Importe"],
                "filas": [[nombre.get(a, a), u, ia.pesos(importe[a])] for a, u in top],
            },
            ["¿Qué artículos hay que reponer?"],
        )

    def caja(self, periodo: Periodo, conserje_id: int | None) -> dict:
        arqueos = [a for a in self.ctx.arqueos if periodo.contiene(a.momento)]
        if conserje_id is not None:
            arqueos = [a for a in arqueos if a.operador_id == conserje_id]
        if not arqueos:
            return _respuesta(f"No hay arqueos {periodo.en}.", "caja", periodo)
        por_operador: dict[int, list] = {}
        for a in arqueos:
            por_operador.setdefault(a.operador_id, []).append(a)
        filas = []
        for operador_id, propios in por_operador.items():
            faltantes = [a for a in propios if a.categoria == FALTANTE]
            sobrantes = [a for a in propios if a.categoria == SOBRANTE]
            filas.append(
                [
                    self.ctx.nombres.get(operador_id, "—"),
                    len(propios),
                    len(faltantes),
                    ia.pesos(-sum(a.diferencia for a in faltantes)),
                    len(sobrantes),
                    ia.porcentaje((len(faltantes) + len(sobrantes)) / len(propios)),
                ]
            )
        filas.sort(key=lambda f: -f[2])
        total_faltante = -sum(a.diferencia for a in arqueos if a.categoria == FALTANTE)
        con_diferencia = sum(1 for a in arqueos if a.diferencia)
        texto = (
            f"{periodo.en_mayuscula} se confirmaron {len(arqueos)} arqueos: {con_diferencia} con diferencia "
            f"(TDC {ia.porcentaje(con_diferencia / len(arqueos))}) y {ia.pesos(total_faltante)} de faltantes en total."
        )
        if conserje_id is None and len(filas) > 1 and filas[0][2] > 0:
            texto += f" Quien más faltantes tuvo es {filas[0][0]} ({filas[0][2]}, por {filas[0][3]})."
        return _respuesta(
            texto,
            "caja",
            periodo,
            "Arqueos confirmados (RF-09); la TDC es la proporción con faltante o sobrante.",
            {"columnas": ["Conserje", "Arqueos", "Faltantes", "Importe", "Sobrantes", "TDC"], "filas": filas},
            ["¿Qué alertas hay?", "¿Cuánto facturamos la semana pasada?"],
        )

    def medios(self, periodo: Periodo) -> dict:
        totales = Counter()
        for c in self.ctx.cobros:
            if periodo.contiene(c.momento):
                totales[c.medio] += c.monto
        if not totales:
            return _respuesta(f"No hay cobros {periodo.en}.", "medios", periodo)
        suma = sum(totales.values())
        etiqueta = {"EFECTIVO": "Efectivo", "POSNET": "POSNET", "MERCADO_PAGO": "Mercado Pago"}
        filas = [[etiqueta.get(m, m), ia.pesos(v), ia.porcentaje(v / suma)] for m, v in totales.most_common()]
        return _respuesta(
            f"{periodo.en_mayuscula}: "
            + ", ".join(f"{f[0]} {f[2]}" for f in filas)
            + f" de {ia.pesos(suma)} cobrados.",
            "medios",
            periodo,
            "Cobros registrados por medio de pago en guardias ya arqueadas.",
            {"columnas": ["Medio", "Importe", "Parte"], "filas": filas},
        )

    def habitaciones(self, texto: str, periodo: Periodo) -> dict:
        habitacion_id = self._habitacion(texto)
        turnos = [t for t in self.ctx.turnos if periodo.contiene(t.fin)]
        usos = Counter(t.habitacion_id for t in turnos)
        ingresos = Counter()
        for t in turnos:
            ingresos[t.habitacion_id] += t.total
        if habitacion_id is not None:
            numero = self.ctx.numero(habitacion_id)
            return _respuesta(
                f"La habitación {numero} tuvo {usos[habitacion_id]} turnos {periodo.en} y dejó "
                f"{ia.pesos(ingresos[habitacion_id])}.",
                "habitaciones",
                periodo,
            )
        activas = [h for h in self.ctx.habitaciones if h.estado != "Mantenimiento"]
        if not activas:
            return _respuesta("No hay habitaciones en servicio.", "habitaciones", periodo)
        orden = sorted(activas, key=lambda h: usos[h.id])
        menos, mas = orden[0], orden[-1]
        quiere_menos = bool(re.search(r"menos", texto))
        elegida = menos if quiere_menos else mas
        texto_resp = (
            f"La habitación {'menos' if quiere_menos else 'más'} usada {periodo.en} es la {elegida.numero} "
            f"({self.ctx.nombre_categoria(elegida.categoria_id)}), con {usos[elegida.id]} turnos. "
            f"La {'más' if quiere_menos else 'menos'} usada es la {(mas if quiere_menos else menos).numero} "
            f"({usos[(mas if quiere_menos else menos).id]})."
        )
        tabla = {
            "columnas": ["Habitación", "Categoría", "Turnos", "Ingresos"],
            "filas": [
                [h.numero, self.ctx.nombre_categoria(h.categoria_id), usos[h.id], ia.pesos(ingresos[h.id])]
                for h in sorted(activas, key=lambda h: -usos[h.id])
            ],
        }
        return _respuesta(texto_resp, "habitaciones", periodo, "Turnos cobrados por habitación.", tabla)


def responder(ctx: ia.Contexto, pregunta: str, anterior: str | None = None) -> dict:
    return Asistente(ctx).responder(pregunta, anterior)
