"""Asistente de la gerencia: responde preguntas en español sobre los datos del motel, sin servicios externos.

Interpreta la pregunta con reglas (palabras clave con tildes y mayúsculas normalizadas, período, categoría, conserje
y habitación mencionados) y la contesta con los mismos cálculos de la inteligencia local. Cada respuesta dice qué
período miró y cómo lo calculó. Como el resto del módulo, solo ve lo cerrado (RN-RES-03): la guardia en curso se suma
cuando se arquea.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, median

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

# Intenciones: palabras (sin tildes) que suman puntos. La primera de la lista gana los empates.
INTENCIONES: list[tuple[str, list[str]]] = [
    ("ayuda", [r"\bayuda\b", r"que (podes|sabes|puedo)", r"como (te uso|funciona)"]),
    ("resumen", [r"\bresumen\b", r"como (venimos|estamos|va|vamos)", r"\bnovedades\b", r"que (paso|hay de nuevo)"]),
    (
        "pronostico",
        [
            r"\bmanana\b",
            r"pronostic",
            r"\besperamos\b",
            r"\bespera",
            r"\bproxim",
            r"esta noche",
            r"\bva(mos)? a\b",
            r"\bprever\b",
        ],
    ),
    ("stock", [r"\bstock\b", r"\brepon", r"\bagot", r"falta comprar", r"\bpedir\b", r"\bcomprar\b", r"inventario"]),
    ("articulos", [r"articulo", r"producto", r"\bvend", r"\bconsum", r"mas pedid", r"bebida", r"minibar"]),
    ("caja", [r"faltante", r"sobrante", r"\barqueo", r"diferencia", r"\btdc\b", r"\bcaja\b", r"descuadr"]),
    ("medios", [r"efectivo", r"tarjeta", r"posnet", r"mercado ?pago", r"medios? de pago", r"\bcomo (pagan|cobramos)"]),
    ("sobreturno", [r"sobreturno", r"excedi", r"se pasan", r"tiempo extra", r"fraccion"]),
    ("estadia", [r"estadia", r"duracion", r"cuanto (tiempo|duran|dura|se quedan)", r"permanencia", r"\bdura\b"]),
    ("ticket", [r"\bticket\b", r"promedio por turno", r"gasto promedio", r"cuanto gasta", r"precio promedio"]),
    ("ocupacion", [r"ocupacion", r"\bocupad", r"\bllen", r"\blibres?\b", r"porcentaje de uso"]),
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
    ("habitaciones", [r"habitacion", r"\bpieza", r"\bcuarto", r"mas usad", r"menos usad"]),
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
        ],
    ),
    ("turnos", [r"\bturnos?\b", r"\bclientes?\b", r"\bentrad", r"\bvisitas?\b", r"cuantos? (vinieron|entraron)"]),
]


def normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]", " ", sin_tildes)).strip()


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
        if self.etiqueta in ("hoy", "ayer", "anteayer") or self.etiqueta.startswith("el "):
            return self.etiqueta
        return f"en {self.etiqueta}"

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


def interpretar_periodo(texto: str, hoy: date) -> Periodo:
    lunes = hoy - timedelta(days=hoy.weekday())
    if m := re.search(r"ultim[oa]s? (\d+) (dias|semanas|meses)", texto):
        n = int(m.group(1)) * {"dias": 1, "semanas": 7, "meses": 30}[m.group(2)]
        return Periodo(hoy - timedelta(days=n - 1), hoy, f"los últimos {m.group(1)} {m.group(2)}")
    if re.search(r"\bhoy\b", texto):
        return Periodo(hoy, hoy, "hoy")
    if re.search(r"\banteayer\b", texto):
        return Periodo(hoy - timedelta(days=2), hoy - timedelta(days=2), "anteayer")
    if re.search(r"\bayer\b", texto):
        return Periodo(hoy - timedelta(days=1), hoy - timedelta(days=1), "ayer")
    if re.search(r"semana (pasada|anterior)", texto):
        return Periodo(lunes - timedelta(days=7), lunes - timedelta(days=1), "la semana pasada")
    if re.search(r"(esta|la) semana|en la semana", texto):
        return Periodo(lunes, hoy, "esta semana")
    if re.search(r"ultima semana|ultimos siete dias", texto):
        return Periodo(hoy - timedelta(days=6), hoy, "la última semana")
    if re.search(r"mes (pasado|anterior)", texto):
        fin = hoy.replace(day=1) - timedelta(days=1)
        return Periodo(fin.replace(day=1), fin, f"{MESES[fin.month - 1]} (el mes pasado)")
    if re.search(r"este mes|en el mes", texto):
        return Periodo(hoy.replace(day=1), hoy, "este mes")
    if re.search(r"ultimo mes", texto):
        return Periodo(hoy - timedelta(days=29), hoy, "el último mes")
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


class Asistente:
    def __init__(self, ctx: ia.Contexto):
        self.ctx = ctx
        self.hoy = ctx.ahora.date()

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
        if self.ctx.hay_guardia_abierta and periodo.hasta >= self.ctx.corte.date():
            return " No incluye la guardia en curso: se suma cuando se cierre con su arqueo."
        return ""

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

    # --- Respuestas ---------------------------------------------------------------------------------------------

    def responder(self, pregunta: str) -> dict:
        texto = normalizar(pregunta)
        if not texto:
            return self.ayuda()
        intencion = _intencion(texto)
        periodo = interpretar_periodo(texto, self.hoy)
        categoria_id, conserje_id = self._categoria(texto), self._conserje(texto)
        if intencion is None and categoria_id is not None:
            intencion = "ingresos"
        if intencion is None and self._habitacion(texto) is not None:
            intencion = "habitaciones"
        metodo = {
            "ayuda": lambda: self.ayuda(),
            "resumen": lambda: self.resumen(),
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
        }.get(intencion or "")
        if metodo is None:
            return _respuesta(
                "No estoy seguro de haber entendido la pregunta. Puedo responder sobre ingresos, turnos, ocupación, "
                "estadías, horarios de más demanda, categorías, habitaciones, caja y faltantes, artículos y stock, y "
                "el pronóstico de los próximos días.",
                "desconocida",
                sugerencias=SUGERENCIAS[:4],
            )
        if not self.ctx.turnos and intencion not in ("ayuda", "stock"):
            return _respuesta(
                "Todavía no hay turnos cerrados para analizar: las respuestas aparecen cuando se arquea la primera "
                "guardia con turnos.",
                intencion,
            )
        return metodo()

    def ayuda(self) -> dict:
        return _respuesta(
            "Soy el asistente de MotelOS. Respondo con los datos del motel, calculados acá mismo (nada sale de esta "
            "computadora). Probá preguntar por ingresos, turnos, ocupación, estadías, horarios, categorías, "
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

    def ingresos(self, texto: str, periodo: Periodo, categoria_id: int | None, conserje_id: int | None) -> dict:
        if re.search(r"que categoria|por categoria|cual categoria|categorias", texto) and categoria_id is None:
            turnos = self._turnos(periodo)
            tabla = self._por_categoria(turnos)
            if not tabla["filas"]:
                return _respuesta(f"No hay turnos cobrados {periodo.en}.", "ingresos", periodo)
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
        anteriores = self._turnos(periodo.anterior(), categoria_id, conserje_id)
        total, total_ant = sum(t.total for t in turnos), sum(t.total for t in anteriores)
        sujeto = ""
        if categoria_id is not None:
            sujeto += f" en {self.ctx.nombre_categoria(categoria_id)}"
        if conserje_id is not None:
            sujeto += f" cobrados por {self.ctx.nombres.get(conserje_id, '—')}"
        if not turnos:
            return _respuesta(
                f"No hay turnos cobrados{sujeto} {periodo.en}.{self._aviso_corte(periodo)}",
                "ingresos",
                periodo,
            )
        cambio = ia.variacion(total, total_ant)
        comparacion = (
            f" Es {ia.con_signo(cambio)} respecto del período anterior equivalente ({ia.pesos(total_ant)})."
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
        anteriores = self._turnos(periodo.anterior(), categoria_id, conserje_id)
        sujeto = f" en {self.ctx.nombre_categoria(categoria_id)}" if categoria_id is not None else ""
        if conserje_id is not None:
            sujeto += f" cobrados por {self.ctx.nombres.get(conserje_id, '—')}"
        dias = len({t.fin.date() for t in turnos}) or 1
        cambio = ia.variacion(len(turnos), len(anteriores))
        return _respuesta(
            f"{periodo.en_mayuscula} hubo {len(turnos)} turnos{sujeto}"
            + (f", unos {len(turnos) / dias:.0f} por día" if periodo.dias > 1 and turnos else "")
            + (f" ({ia.con_signo(cambio)} contra el período anterior)." if cambio is not None else ".")
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
            return _respuesta(f"No hay turnos cobrados {periodo.en}.", "ticket", periodo)
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
            return _respuesta(f"No hay estadías cerradas {periodo.en}.", "estadia", periodo)
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
            return _respuesta(f"No hay turnos cobrados {periodo.en}.", "sobreturno", periodo)
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


def responder(ctx: ia.Contexto, pregunta: str) -> dict:
    return Asistente(ctx).responder(pregunta)
