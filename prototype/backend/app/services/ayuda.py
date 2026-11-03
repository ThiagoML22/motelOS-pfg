"""Asistente de ayuda para todo el personal: cómo se usa el sistema y cómo está la ventanilla ahora.

Responde dos tipos de preguntas, sin servicios externos:
- **Cómo se hace algo** («¿cómo abro un turno?», «se cortó la conexión, ¿qué hago?»): una base de temas con los pasos y
  un botón para ir a la pantalla que corresponde. Algunos temas son solo de la gerencia (tarifas, conserjes...).
- **Cómo está la ventanilla** («¿qué habitaciones están libres?», «¿cuál vence primero?», «¿cuánto debe la 5?»,
  «¿cuántas aguas quedan?», «¿cuánto sale la VIP?»): datos que el conserje ya ve en su pantalla, calculados al momento.

RN-RES-03: nunca responde el total de la caja de una guardia abierta (el cierre es ciego, también para este asistente).
Las preguntas de ingresos y análisis las responde el asistente de la gerencia (services.asistente); a un conserje se
le explica que esa información es de la gerencia.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.inquilino import CLAVE
from app.models.articulo import Articulo
from app.models.categoria import CategoriaHabitacion
from app.models.configuracion import ConfiguracionCaja
from app.models.habitacion import Habitacion
from app.models.novedad import Novedad
from app.models.operador import ROL_ADMINISTRADOR, Operador
from app.models.pedido import PENDIENTE, PedidoReposicion
from app.models.tarifa import Tarifa
from app.models.turno import Turno
from app.services import conocimiento
from app.services import inteligencia as ia
from app.services.asistente import INTENCIONES, _intencion, normalizar
from app.services.asistente import responder as responder_analisis
from app.services.caja import guardia_abierta
from app.services.liquidacion import con_zona, liquidar_turno

# Frases que piden instrucciones: con ellas, un tema de ayuda gana sobre el análisis de datos.
COMO = re.compile(
    r"\b(como|donde|que hago|que tengo que|puedo|se puede|hay que|pasos|ayuda|explica|para que sirve|no puedo"
    r"|no me deja)\b"
)
TODOS = "todos"
GERENCIA = "gerencia"


@dataclass(frozen=True)
class Tema:
    id: str
    titulo: str
    claves: tuple[str, ...]
    pasos: tuple[str, ...]
    vista: str | None = None
    roles: str = TODOS
    nota: str | None = None


TEMAS: tuple[Tema, ...] = (
    Tema(
        "abrir_guardia",
        "Abrir la guardia",
        (
            r"\bguardia\b.*\b(abr|empez|inici|comenz)",
            r"\b(abr|empez|inici)\w* (la |mi )?guardia",
            r"(empiez|empez|inici|comienz|arranc)\w* (mi |el )?(turno|dia) de trabajo",
            r"(empiez|empez|arranc)\w* a trabajar",
        ),
        (
            "Al ingresar sin guardia abierta aparece «Abrir su guardia».",
            "Leé debajo las novedades que dejaron las guardias anteriores.",
            "Tocá «Abrir guardia»: tu caja empieza con el fondo de cambio.",
            "Si la guardia abierta es de otro conserje, primero la cierra él con su arqueo.",
        ),
        "dashboard",
    ),
    Tema(
        "abrir_turno",
        "Abrir un turno (ocupar una habitación)",
        (
            r"\b(abr|ocup|registr|ingres|carg)\w* (un |el |una )?(turno|habitacion|cliente|auto)",
            r"llego un (cliente|auto)",
            r"\bentrar? (un )?cliente",
        ),
        (
            "En Habitaciones, tocá una habitación disponible (verde).",
            "Elegí el tipo de cliente (auto, moto o peatón) y cargá la patente si corresponde.",
            "El diálogo muestra la tarifa de la categoría: confirmá «Abrir turno».",
            "El cronómetro corre en el servidor y la tarjeta pasa a azul.",
        ),
        "dashboard",
    ),
    Tema(
        "consumo",
        "Cargar un consumo del minibar",
        (
            r"\bconsumo",
            r"\bminibar",
            r"\b(carg|agreg|sum)\w* (una |un )?(bebida|articulo|producto|gaseosa|agua|cerveza)",
        ),
        (
            "En la tarjeta de la habitación ocupada tocá «+ consumo» (o abrí la habitación).",
            "Elegí el artículo y la cantidad y confirmá.",
            "Se descuenta del stock y se suma a la cuenta del turno.",
        ),
        "dashboard",
    ),
    Tema(
        "cobrar",
        "Cobrar y cerrar un turno",
        (r"\bcobr", r"\b(cerr|cierr)\w* (el |un )?turno", r"\bpag(a|ar|o)\b", r"se va el cliente", r"\bliquid"),
        (
            "Abrí la habitación ocupada: la cuenta muestra estadía, sobreturno y consumos.",
            "Elegí el medio de pago (efectivo, POSNET o Mercado Pago; con tarjeta cargá el número de comprobante).",
            "El monto tiene que cubrir exactamente el saldo (RN-EXI-03).",
            "Al confirmar sale la constancia y la habitación pasa a «Limpieza».",
        ),
        "dashboard",
    ),
    Tema(
        "liberar",
        "Liberar una habitación después de la limpieza",
        (r"\bliber", r"\blimpi", r"dejar (la habitacion )?(libre|disponible)"),
        (
            "Cuando la habitación quedó lista, tocá «Liberar» en su tarjeta.",
            "Pasa a «Disponible» (verde) y se puede volver a ocupar.",
        ),
        "dashboard",
    ),
    Tema(
        "mantenimiento",
        "Poner una habitación en mantenimiento",
        (
            r"mantenimiento",
            r"fuera de servicio",
            r"\b(rot[oa]|no funciona|desperfecto|no anda (el|la) (aire|ducha|tele))",
        ),
        (
            "En el menú (⋮) de la tarjeta de una habitación libre elegí «Mantenimiento».",
            "Dejá una novedad contando el problema, para la gerencia y la guardia siguiente.",
            "Cuando esté arreglada, volvé a ponerla «Disponible».",
        ),
        "dashboard",
    ),
    Tema(
        "tarifa",
        "Cómo se calcula lo que paga el cliente",
        (
            r"sobreturno",
            r"\bfraccion",
            r"\btolerancia",
            r"\btope\b",
            r"por que (le )?cobr",
            r"como se calcula",
            r"se paso (de|del) tiempo",
        ),
        (
            "Cada categoría tiene su tarifa: una estadía base (por ejemplo 2 h por $8.000).",
            "Pasada la estadía base se cobra una fracción extra (por ejemplo $2.500 cada 30 min), "
            "contada desde el fin de la "
            "estadía base; algunas categorías tienen minutos de tolerancia y un tope (como un pernocte).",
            "El turno conserva la tarifa con la que se abrió, aunque después la gerencia la cambie.",
            "La tarjeta se pone amarilla cuando está por vencer y roja cuando se excede.",
        ),
        "dashboard",
    ),
    Tema(
        "cierre_caja",
        "Cerrar la caja al terminar la guardia",
        (
            r"\b(cerr|cierr)\w* (la |mi )?caja",
            r"\barqueo",
            r"\bcierre\b",
            r"terminar (la |mi )?guardia",
            r"fin de (la )?guardia",
            r"\brecuento",
            r"contar (la )?plata",
            r"\bme voy\b",
        ),
        (
            "Antes de irte entrá a «Cierre de caja».",
            "Contá la gaveta y declará efectivo, POSNET y Mercado Pago. "
            "El sistema no te muestra el total: es un cierre "
            "ciego (RN-RES-03).",
            "Confirmá: el sistema calcula la diferencia (correcto, faltante o sobrante) y cierra tu guardia.",
            "Descargá el comprobante en PDF para firmarlo.",
        ),
        "caja",
    ),
    Tema(
        "total_caja",
        "Por qué no se ve el total de la caja",
        (
            r"cuanto (llevo|tengo|hice|cobre|recaude|hay en (la )?caja)",
            r"llevo (cobrado|recaudado|hecho)",
            r"total de (la |mi )?caja",
            r"ver (el )?total",
        ),
        (
            "Mientras la guardia está abierta nadie ve el total que espera el sistema, ni la gerencia: "
            "es el cierre ciego.",
            "Lo ves al confirmar tu arqueo, junto con la diferencia.",
            "Así el recuento de la gaveta es honesto y la diferencia se mide de verdad.",
        ),
        "caja",
    ),
    Tema(
        "guardia_ajena",
        "La guardia abierta es de otro conserje",
        (
            r"guardia (de otro|abierta de|ajena)",
            r"no (puedo|me deja) (operar|abrir|cobrar)",
            r"esta abierta la guardia",
        ),
        (
            "Hay una sola ventanilla: solo opera quien tiene la guardia abierta.",
            "El conserje anterior tiene que cerrar su caja con el arqueo.",
            "Si se fue sin cerrarla, la gerencia hace un cierre supervisado desde Control de caja.",
        ),
        None,
    ),
    Tema(
        "conexion",
        "Se cortó la conexión",
        (r"conexion", r"\binternet\b", r"se (corto|cayo)", r"sin (red|conexion|sistema)", r"no carga"),
        (
            "Arriba aparece un aviso amarillo y no se pueden abrir ni cobrar turnos: así nada queda a medias.",
            "Los cronómetros siguen en el servidor; no se pierde tiempo de los turnos.",
            "El sistema reintenta solo cada 2 segundos y se actualiza al volver (RNF-09).",
            "Lo que no llegaste a confirmar antes del corte, hacelo de nuevo cuando vuelva.",
        ),
        None,
    ),
    Tema(
        "inventario",
        "Cargar mercadería o un artículo nuevo",
        (
            r"\breponer",
            r"llego (la )?mercaderia",
            r"nuevo articulo",
            r"(agregar|dar de alta) (un )?articulo",
            r"\binventario",
        ),
        (
            "Entrá a «Inventario».",
            "«Nuevo artículo» da de alta uno (código, descripción, precio y stock).",
            "«Reponer» suma las unidades que llegaron de un artículo que ya existe.",
            "Todo queda a tu nombre y la gerencia lo ve en Actividad.",
        ),
        "inventario",
    ),
    Tema(
        "novedades",
        "Dejar una novedad para la guardia siguiente",
        (r"\bnovedad", r"\bnota\b", r"avisar a (la )?gerencia", r"dejar (un )?(aviso|escrito)"),
        (
            "En Habitaciones tocá «Dejar novedad» (o desde la campanita).",
            "Escribí qué pasó; podés marcarla como importante y elegir una habitación.",
            "La lee la guardia siguiente antes de abrir y la gerencia en la campanita. No se borra.",
        ),
        "dashboard",
    ),
    Tema(
        "clave",
        "Cambiar mi clave o mi nombre",
        (r"\bclave\b", r"contrasena", r"password", r"nombre visible", r"\bmi perfil"),
        (
            "Tocá tu nombre arriba a la derecha y elegí «Mi perfil».",
            "Ahí cambiás tu nombre visible y tu clave (te pide la actual).",
            "Si la olvidaste, la gerencia te la restablece desde Configuración → Conserjes.",
        ),
        "perfil",
    ),
    Tema(
        "tema",
        "Modo oscuro",
        (r"modo oscuro", r"\btema\b", r"\bluna\b", r"modo claro"),
        (
            "Tocá la lunita del encabezado: la pantalla pasa a modo oscuro (y el sol la devuelve al claro).",
            "En Mi perfil elegís si sigue al sistema operativo.",
        ),
        None,
    ),
    Tema(
        "atajos",
        "Buscar y moverse rápido",
        (r"\batajo", r"ctrl ?k", r"\bbuscar\b", r"teclado"),
        (
            "Ctrl+K (o la lupa del encabezado) abre el buscador.",
            "Escribí una sección, el número de una habitación («7») o una acción («novedad», «oscuro»).",
            "Con las flechas elegís y con Enter vas.",
        ),
        None,
    ),
    Tema(
        "patente",
        "La patente del cliente",
        (r"\bpatente", r"\bdominio\b", r"\bvehiculo"),
        (
            "Se carga al abrir el turno y sirve para identificar el auto en la ventanilla.",
            "Se borra sola 24 horas después de cerrado el turno (RNF-08): no queda en el historial.",
        ),
        "dashboard",
    ),
    Tema(
        "comprobante",
        "Comprobantes e impresiones",
        (r"comprobante", r"\bpdf\b", r"imprim", r"constancia"),
        (
            "Al cobrar un turno sale la constancia de cobro para imprimir.",
            "Al cerrar la caja descargás el comprobante del arqueo en PDF para firmar.",
            "La gerencia los vuelve a descargar desde Control de caja.",
        ),
        None,
    ),
    Tema(
        "recibir_pedido",
        "Recibir la mercadería de un pedido",
        (r"recib\w* (un |el |la )?(pedido|mercaderia)", r"llego (el pedido|la mercaderia|el proveedor)"),
        (
            "En «Inventario», en «Pedidos a proveedores», tocá «Recibir» en el pedido.",
            "Anotá lo que llegó de cada artículo (0 si no vino).",
            "Al confirmar se suma al stock y queda en Actividad a tu nombre.",
        ),
        "inventario",
    ),
    # Solo la gerencia.
    Tema(
        "armar_pedido",
        "Armar un pedido a un proveedor",
        (r"(arm|hac|cre|carg|nuev|mand)\w* (un |el )?pedido", r"pedido (al|a un|para el) proveedor"),
        (
            "En «Inventario» tocá «Nuevo pedido» (o en Inteligencia, «Armar pedido con esto»).",
            "Empieza con la reposición sugerida: ajustá cantidades, agregá o quitá artículos y anotá el proveedor.",
            "Al crearlo se descarga el PDF para mandárselo al proveedor; queda pendiente hasta que se recibe.",
        ),
        "inventario",
        GERENCIA,
    ),
    Tema(
        "exportar_mes",
        "Exportar los arqueos de un mes",
        (
            r"\bexport",
            r"informe (mensual|del mes)",
            r"(bajar|descargar)\w* (los )?arqueos",
            r"\bexcel\b",
            r"arqueos (del|de un|de) mes",
        ),
        (
            "En «Control de caja», bajá hasta «Historial de arqueos».",
            "En el mes que quieras, «PDF» descarga el informe (resumen y cada guardia) y «Excel» la planilla.",
            "Si filtrás por un conserje arriba, el informe sale solo con sus arqueos.",
        ),
        "gerencia",
        GERENCIA,
    ),
    Tema(
        "config_articulos",
        "Cambiar el precio de un artículo o darlo de baja",
        (
            r"(cambi|modific|sub|baj)\w* (el )?precio de (un |una |la |el )?(articulo|producto|bebida)",
            r"baja (de )?(un )?articulo",
        ),
        (
            "Configuración → «Artículos».",
            "Cambiá el precio o dalo de baja; los consumos ya cargados conservan el precio que tenían.",
        ),
        "configuracion",
        GERENCIA,
    ),
    Tema(
        "config_habitaciones",
        "Agregar, renumerar o dar de baja habitaciones",
        (r"(agreg|cre|nuev|baj|renumer|sac)\w* (una )?habitacion", r"habitacion nueva"),
        (
            "Configuración → «Habitaciones».",
            "Agregá una con su número y su categoría, cambiale la categoría o dala de baja (sale de la grilla "
            "y conserva su historia).",
        ),
        "configuracion",
        GERENCIA,
    ),
    Tema(
        "config_fondo",
        "Cambiar el fondo de cambio",
        (r"(cambi|modific|sub|baj)\w* (el )?fondo",),
        (
            "Configuración → «Fondo de cambio».",
            "El monto nuevo rige desde la guardia siguiente: la que está abierta conserva el suyo.",
        ),
        "configuracion",
        GERENCIA,
    ),
    Tema(
        "aplicar_sugerencia",
        "Aplicar una sugerencia de tarifa",
        (r"aplic\w* (una |la )?sugerencia", r"sugerencias? de tarifa"),
        (
            "En «Inteligencia», en «Sugerencias de tarifa por categoría», tocá «Ver y aplicar».",
            "Revisá la tarifa actual contra la propuesta y el efecto estimado por mes, y confirmá.",
            "La nueva tarifa rige para los turnos que se abran desde ese momento.",
        ),
        "inteligencia",
        GERENCIA,
    ),
    Tema(
        "config_tarifas",
        "Cambiar tarifas y categorías",
        (
            r"(cambi|modific|configur|sub|baj)\w* (la |las |el |los |una |un )?(tarifa|precio)",
            r"nueva categoria",
            r"(crear|agregar) (una )?categoria",
        ),
        (
            "Configuración → «Categorías y tarifas».",
            "«Cambiar tarifa» de una categoría: estadía base, fracción, tolerancia y tope, "
            "con el simulador de lo que paga "
            "el cliente.",
            "Rige para los turnos nuevos; los que están en curso conservan la suya.",
            "En Inteligencia hay sugerencias de tarifa simuladas sobre las estadías reales.",
        ),
        "configuracion",
        GERENCIA,
    ),
    Tema(
        "conserjes",
        "Dar de alta o de baja un conserje",
        (r"(alta|agreg|crea|nuevo|baja|sacar)\w* (un |a un )?(conserje|empleado|usuario)", r"restablecer (la )?clave"),
        (
            "Configuración → «Conserjes».",
            "«Nuevo conserje» con usuario, nombre y clave inicial; la baja lo desactiva sin borrar su historia.",
            "El ícono de llave restablece la clave de un conserje.",
        ),
        "configuracion",
        GERENCIA,
    ),
    Tema(
        "apariencia",
        "Color, eslogan y avisos del motel",
        (r"\bcolor", r"\beslogan", r"\bmarca\b", r"\bsonido", r"alerta sonora", r"aviso (de )?por vencer"),
        (
            "Configuración → «Apariencia y avisos».",
            "Elegí el color de marca (se ve en vivo), el eslogan del ingreso, "
            "los minutos del aviso «por vencer» y si suenan "
            "las alertas en la ventanilla.",
        ),
        "configuracion",
        GERENCIA,
    ),
    Tema(
        "supervisado",
        "Cerrar la guardia de un conserje que se fue",
        (r"supervisad", r"cierre supervisado", r"guardia abandonada", r"se fue sin cerrar"),
        (
            "Control de caja: arriba aparece la guardia abierta de ese conserje.",
            "«Cierre supervisado»: contás la gaveta, declarás y dejás una observación.",
            "El arqueo queda a nombre del conserje y registra que lo confirmó la gerencia.",
        ),
        "gerencia",
        GERENCIA,
    ),
    Tema(
        "actividad",
        "Ver quién cambió qué",
        (r"\bactividad", r"quien (cambio|cargo|hizo)", r"\bregistro\b"),
        (
            "En «Actividad» está cada cambio de inventario y configuración con quién y en qué guardia.",
            "Lo que cargan los conserjes queda «por revisar» hasta que lo marcás como visto.",
            "Se puede filtrar y exportar a CSV.",
        ),
        "actividad",
        GERENCIA,
    ),
    Tema(
        "control_caja",
        "Revisar arqueos y faltantes",
        (r"control de caja", r"historial de (caja|arqueos)", r"ver (los )?arqueos"),
        (
            "En «Control de caja» están los arqueos por mes y por día, con la TDC y los faltantes por conserje.",
            "Tocá un arqueo para ver sus cobros y descargar el PDF.",
        ),
        "gerencia",
        GERENCIA,
    ),
)

VISTAS = {
    "dashboard": "Ir a Habitaciones",
    "inventario": "Ir a Inventario",
    "caja": "Ir a Cierre de caja",
    "gerencia": "Ir a Control de caja",
    "configuracion": "Ir a Configuración",
    "actividad": "Ir a Actividad",
    "perfil": "Ir a Mi perfil",
    "inteligencia": "Ir a Inteligencia",
}

SUGERENCIAS_CONSERJE = [
    "¿Cómo abro un turno?",
    "¿Qué habitaciones están libres?",
    "¿Cuál vence primero?",
    "¿Cómo cierro la caja?",
    "¿Cuánto sale la VIP?",
    "Se cortó la conexión, ¿qué hago?",
]


@dataclass
class Respuesta:
    respuesta: str
    intencion: str
    pasos: list[str] = field(default_factory=list)
    acciones: list[dict] = field(default_factory=list)
    sugerencias: list[str] = field(default_factory=list)
    detalle: str | None = None
    tabla: dict | None = None

    def como_dict(self) -> dict:
        return {
            "respuesta": self.respuesta,
            "intencion": self.intencion,
            "periodo": None,
            "detalle": self.detalle,
            "tabla": self.tabla,
            "sugerencias": self.sugerencias,
            "pasos": self.pasos,
            "acciones": self.acciones,
        }


def _ir(vista: str | None) -> list[dict]:
    return [{"etiqueta": VISTAS[vista], "vista": vista, "habitacion_id": None}] if vista in VISTAS else []


def _tema(texto: str, es_gerencia: bool) -> Tema | None:
    mejores = []
    for orden, tema in enumerate(TEMAS):
        if tema.roles == GERENCIA and not es_gerencia:
            continue
        puntos = sum(1 for clave in tema.claves if re.search(clave, texto))
        if puntos:
            mejores.append((puntos, -orden, tema))
    return max(mejores, key=lambda m: (m[0], m[1]))[2] if mejores else None


def _numero(texto: str) -> int | None:
    m = re.search(r"(?:habitacion|hab|pieza|cuarto|la|el)\s*(?:n\s*)?(\d{1,4})\b", texto)
    return int(m.group(1)) if m else None


class Ventanilla:
    """Lo que el conserje ya ve en su pantalla, leído al momento."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ahora = datetime.now(UTC)

    async def cargar(self) -> None:
        self.habitaciones = list(
            (
                await self.db.execute(select(Habitacion).where(Habitacion.activa.is_(True)).order_by(Habitacion.numero))
            ).scalars()
        )
        self.categorias = {c.id: c for c in (await self.db.execute(select(CategoriaHabitacion))).scalars()}
        self.tarifas = {
            t.categoria_id: t for t in (await self.db.execute(select(Tarifa).where(Tarifa.vigente.is_(True)))).scalars()
        }
        self.turnos = {
            t.habitacion_id: t
            for t in (await self.db.execute(select(Turno).where(Turno.estado == "En Curso"))).scalars()
        }
        self.tarifas_de_turnos = (
            {
                t.id: t
                for t in (
                    await self.db.execute(
                        select(Tarifa).where(Tarifa.id.in_({x.tarifa_id for x in self.turnos.values()}))
                    )
                ).scalars()
            }
            if self.turnos
            else {}
        )
        self.articulos = list((await self.db.execute(select(Articulo).where(Articulo.activo.is_(True)))).scalars())
        self.nombres = {i: n for i, n in (await self.db.execute(select(Operador.id, Operador.nombre_visible))).all()}

    def nombre_categoria(self, habitacion: Habitacion) -> str:
        categoria = self.categorias.get(habitacion.categoria_id)
        return categoria.nombre if categoria else ""

    def categoria_mencionada(self, texto: str) -> CategoriaHabitacion | None:
        for c in self.categorias.values():
            if c.activa and re.search(rf"\b{re.escape(normalizar(c.nombre))}\b", texto):
                return c
        return None

    def minutos(self, turno: Turno) -> float:
        return (self.ahora - con_zona(turno.hora_inicio)).total_seconds() / 60

    def libres(self) -> Respuesta:
        libres = [h for h in self.habitaciones if h.estado == "Libre"]
        if not libres:
            return Respuesta("No hay habitaciones disponibles en este momento.", "libres")
        por_categoria: dict[str, list[int]] = {}
        for h in libres:
            por_categoria.setdefault(self.nombre_categoria(h), []).append(h.numero)
        texto = (
            f"Hay {len(libres)} disponibles: "
            + "; ".join(
                f"{nombre or 'Sin categoría'} {', '.join(map(str, numeros))}"
                for nombre, numeros in por_categoria.items()
            )
            + "."
        )
        limpieza = [h.numero for h in self.habitaciones if h.estado == "En Limpieza"]
        if limpieza:
            texto += f" En limpieza: {', '.join(map(str, limpieza))}."
        acciones = [
            {"etiqueta": f"Abrir la {h.numero}", "vista": "dashboard", "habitacion_id": h.id} for h in libres[:3]
        ]
        return Respuesta(texto, "libres", acciones=acciones)

    def por_vencer(self) -> Respuesta:
        filas = []
        for h in self.habitaciones:
            turno = self.turnos.get(h.id)
            if turno is None:
                continue
            tarifa = self.tarifas_de_turnos.get(turno.tarifa_id)
            base = tarifa.estadia_base_min if tarifa else 120
            filas.append((base - self.minutos(turno), h))
        if not filas:
            return Respuesta("No hay turnos en curso.", "vencimientos")
        filas.sort(key=lambda f: f[0])
        partes = []
        for restante, h in filas[:5]:
            if restante < 0:
                partes.append(
                    f"la {h.numero} ({self.nombre_categoria(h)}) está excedida hace {ia.minutos_texto(-restante)}"
                )
            else:
                partes.append(f"la {h.numero} ({self.nombre_categoria(h)}) vence en {ia.minutos_texto(restante)}")
        texto = "Por orden: " + "; ".join(partes) + "."
        acciones = [
            {"etiqueta": f"Abrir la {h.numero}", "vista": "dashboard", "habitacion_id": h.id} for _, h in filas[:3]
        ]
        return Respuesta(
            texto[0].upper() + texto[1:],
            "vencimientos",
            acciones=acciones,
            detalle="Contado desde la apertura con la estadía base de la tarifa de cada turno.",
        )

    async def cuenta(self, numero: int) -> Respuesta:
        habitacion = next((h for h in self.habitaciones if h.numero == numero), None)
        if habitacion is None:
            return Respuesta(f"No encuentro la habitación {numero}.", "cuenta")
        turno = self.turnos.get(habitacion.id)
        if turno is None:
            estado = {
                "Libre": "está disponible",
                "En Limpieza": "está en limpieza",
                "Mantenimiento": "está en mantenimiento",
            }
            return Respuesta(
                f"La {numero} no tiene un turno en curso: {estado.get(habitacion.estado, habitacion.estado)}.", "cuenta"
            )
        liquidacion = await liquidar_turno(self.db, turno)
        texto = (
            f"La {numero} ({self.nombre_categoria(habitacion)}) lleva "
            f"{ia.minutos_texto(liquidacion.minutos_transcurridos)}: "
            f"debe {ia.pesos(float(liquidacion.saldo_pendiente))} "
            f"(estadía {ia.pesos(float(turno.tarifa_base))}, sobreturno "
            f"{ia.pesos(float(turno.total_sobreturno))}, consumos {ia.pesos(float(turno.total_consumos))})."
        )
        habitacion_id = habitacion.id
        await self.db.rollback()  # solo se consultó: el cálculo no se guarda desde acá
        return Respuesta(
            texto,
            "cuenta",
            acciones=[{"etiqueta": f"Abrir la {numero}", "vista": "dashboard", "habitacion_id": habitacion_id}],
            detalle="Calculado ahora con la tarifa del turno (RN-DER-01).",
        )

    def tarifas_texto(self, categoria: CategoriaHabitacion | None) -> Respuesta:
        elegidas = (
            [categoria]
            if categoria
            else sorted(
                (c for c in self.categorias.values() if c.activa and c.id in self.tarifas), key=lambda c: c.orden
            )
        )
        partes = []
        for c in elegidas:
            t = self.tarifas.get(c.id)
            if t is None:
                continue
            texto = (
                f"{c.nombre}: {ia.pesos(float(t.tarifa_base))} por {ia.minutos_texto(t.estadia_base_min)}; después "
                f"{ia.pesos(float(t.tarifa_fraccion))} cada {t.fraccion_min} min"
            )
            extras = []
            if t.tolerancia_min:
                extras.append(f"{t.tolerancia_min} min de tolerancia")
            if t.tope is not None:
                extras.append(f"tope {ia.pesos(float(t.tope))}")
            partes.append(texto + (f" ({', '.join(extras)})" if extras else ""))
        if not partes:
            return Respuesta("No encuentro tarifas vigentes.", "tarifas")
        return Respuesta(
            ". ".join(partes) + ".", "tarifas", detalle="Tarifas vigentes para los turnos que se abran ahora."
        )

    async def stock(self, texto: str) -> Respuesta | None:
        if re.search(r"(poco|bajo|sin) stock|que (falta|hay que reponer)|se (esta|estan) (acabando|agotando)", texto):
            bajos = [a for a in self.articulos if a.stock_actual <= 5]
            if not bajos:
                return Respuesta("Ningún artículo está por debajo de 5 unidades.", "stock", acciones=_ir("inventario"))
            lista = ", ".join(
                f"{a.descripcion} ({a.stock_actual})" for a in sorted(bajos, key=lambda a: a.stock_actual)
            )
            return Respuesta(f"Con poco stock: {lista}.", "stock", acciones=_ir("inventario"))
        for a in self.articulos:
            palabras = [p for p in normalizar(a.descripcion).split() if len(p) > 3]
            if palabras and any(
                re.search(rf"\b{re.escape(p[:-1] if p.endswith('s') else p)}", texto) for p in palabras[:2]
            ):
                aviso = " Conviene reponer." if a.stock_actual <= 5 else ""
                return Respuesta(
                    f"Quedan {a.stock_actual} de «{a.descripcion}».{aviso}", "stock", acciones=_ir("inventario")
                )
        return None

    def palabras_propias(self) -> set[str]:
        """Palabras del motel (categorías, artículos, personal) que el corrector no debe tocar."""
        textos = [c.nombre for c in self.categorias.values()] + [a.descripcion for a in self.articulos]
        textos += list(self.nombres.values())
        return {p for t in textos for p in normalizar(t).split() if len(p) >= 4}

    def estado_general(self) -> Respuesta:
        cuenta = {e: sum(1 for h in self.habitaciones if h.estado == e) for e in ESTADOS}
        texto = (
            f"Ahora hay {cuenta['Ocupada']} ocupadas, {cuenta['Libre']} disponibles, {cuenta['En Limpieza']} en "
            f"limpieza y {cuenta['Mantenimiento']} en mantenimiento."
        )
        proxima = self._proxima_a_vencer()
        if proxima:
            restante, h = proxima
            texto += f" La que vence primero es la {h.numero}" + (
                f" (excedida hace {ia.minutos_texto(-restante)})."
                if restante < 0
                else f" (en {ia.minutos_texto(restante)})."
            )
        return Respuesta(texto, "estado", acciones=_ir("dashboard"))

    def _proxima_a_vencer(self):
        filas = []
        for h in self.habitaciones:
            turno = self.turnos.get(h.id)
            if turno is not None:
                tarifa = self.tarifas_de_turnos.get(turno.tarifa_id)
                filas.append(((tarifa.estadia_base_min if tarifa else 120) - self.minutos(turno), h))
        return min(filas, key=lambda f: f[0]) if filas else None

    def ocupadas(self) -> Respuesta:
        filas = [(h, self.turnos[h.id]) for h in self.habitaciones if h.id in self.turnos]
        if not filas:
            return Respuesta("No hay habitaciones ocupadas ahora.", "ocupadas")
        partes = [f"la {h.numero} ({self.nombre_categoria(h)}, {ia.minutos_texto(self.minutos(t))})" for h, t in filas]
        return Respuesta(
            f"Hay {len(filas)} ocupadas: " + ", ".join(partes) + ".",
            "ocupadas",
            acciones=[
                {"etiqueta": f"Abrir la {h.numero}", "vista": "dashboard", "habitacion_id": h.id} for h, _ in filas[:3]
            ],
        )

    def en_estado(self, estado: str, nombre: str) -> Respuesta:
        numeros = [h.numero for h in self.habitaciones if h.estado == estado]
        if not numeros:
            return Respuesta(f"No hay habitaciones en {nombre}.", "estado")
        plural = "habitación" if len(numeros) == 1 else "habitaciones"
        return Respuesta(
            f"En {nombre}: {len(numeros)} {plural} ({', '.join(map(str, numeros))}).",
            "estado",
            acciones=_ir("dashboard"),
        )

    async def guardia(self) -> Respuesta:
        abierta = await guardia_abierta(self.db)
        if abierta is None:
            return Respuesta("No hay una guardia abierta en la ventanilla.", "guardia")
        zona = ZoneInfo(settings.ZONA_HORARIA)
        desde = con_zona(abierta.abierta_en).astimezone(zona)
        hora_fin = (int(abierta.franja[:2]) + 8) % 24
        nombre = self.nombres.get(abierta.operador_id, "—")
        return Respuesta(
            f"La guardia de la {FRANJA.get(abierta.franja, abierta.franja)} la tiene {nombre} desde las "
            f"{desde:%H:%M}; termina a las {hora_fin:02d}:00.",
            "guardia",
        )

    async def fondo(self) -> Respuesta:
        configuracion = await self.db.get(ConfiguracionCaja, self.db.info.get(CLAVE))
        monto = float(configuracion.fondo_cambio) if configuracion else float(settings.FONDO_INICIAL_CAJA)
        return Respuesta(
            f"Cada caja empieza con un fondo de cambio de {ia.pesos(monto)}. Se suma al efectivo que espera el sistema "
            "en el arqueo; si la gerencia lo cambia, rige desde la guardia siguiente.",
            "fondo",
        )

    async def pedidos(self) -> Respuesta:
        pendientes = list(
            (await self.db.execute(select(PedidoReposicion).where(PedidoReposicion.estado == PENDIENTE))).scalars()
        )
        if not pendientes:
            return Respuesta("No hay pedidos a proveedores por recibir.", "pedidos", acciones=_ir("inventario"))
        partes = [f"N.º {p.id}" + (f" de {p.proveedor}" if p.proveedor else "") for p in pendientes]
        return Respuesta(
            f"{'Hay un pedido' if len(pendientes) == 1 else f'Hay {len(pendientes)} pedidos'} por recibir: "
            + ", ".join(partes)
            + ". Cuando llegue la mercadería, tocá «Recibir» en Inventario.",
            "pedidos",
            acciones=_ir("inventario"),
        )

    async def novedades(self) -> Respuesta:
        desde = self.ahora - timedelta(hours=24)
        lista = list(
            (
                await self.db.execute(
                    select(Novedad)
                    .where(Novedad.creado_en >= desde)
                    .order_by(Novedad.importante.desc(), Novedad.id.desc())
                )
            ).scalars()
        )
        if not lista:
            return Respuesta("No hay novedades en las últimas 24 horas.", "novedades", acciones=_ir("dashboard"))
        partes = [
            ("⚠ " if n.importante else "") + f"{n.texto} ({self.nombres.get(n.operador_id, '—')})" for n in lista[:3]
        ]
        mas = f" Y {len(lista) - 3} más." if len(lista) > 3 else ""
        return Respuesta("Últimas novedades: " + " · ".join(partes) + "." + mas, "novedades", acciones=_ir("dashboard"))


ESTADOS = ("Ocupada", "Libre", "En Limpieza", "Mantenimiento")
FRANJA = {"06:00": "mañana", "14:00": "tarde", "22:00": "noche"}
ENTRADAS = TEMAS + conocimiento.DEFINICIONES
# Lo que un conserje puede preguntar del análisis: no muestra dinero (RN-RES-03 y datos de la gerencia).
ANALISIS_CONSERJE = {"horas", "pronostico", "estadia", "ocupacion"}
# Lo que es dinero o caja: al conserje se le dice que es de la gerencia sin buscar otra respuesta.
DINERO = {"ingresos", "caja", "ticket", "medios", "sobreturno", "resumen"}
INTENCIONES_ANALISIS = {nombre for nombre, _ in INTENCIONES}


def _respuesta_de(entrada, es_gerencia: bool, otras: list | None = None) -> dict:
    """Una entrada del conocimiento (tema con pasos o definición) como respuesta, con «¿quisiste decir?»."""
    quisiste = [_como_pregunta(e) for e in (otras or [])]
    if isinstance(entrada, conocimiento.Definicion):
        return Respuesta(
            entrada.texto, f"definicion:{entrada.id}", acciones=_ir(entrada.vista), sugerencias=quisiste
        ).como_dict()
    return Respuesta(
        entrada.titulo + ":",
        f"ayuda:{entrada.id}",
        pasos=list(entrada.pasos),
        acciones=_ir(entrada.vista),
        sugerencias=quisiste or (SUGERENCIAS_CONSERJE[:4] if not es_gerencia else []),
    ).como_dict()


def _como_pregunta(entrada) -> str:
    if isinstance(entrada, conocimiento.Definicion):
        return f"¿Qué es {entrada.termino[0].lower() + entrada.termino[1:]}?"
    return f"¿{entrada.titulo}?" if entrada.titulo.lower().startswith(("cómo", "qué", "por qué")) else entrada.titulo


CHARLA = (
    (re.compile(r"^(hola|buen(os|as)? (dia|dias|tarde|tardes|noche|noches)|que tal|buenas)\b"), "saludo"),
    (re.compile(r"^(gracias|muchas gracias|genial|perfecto|joya|barbaro|listo)\b"), "gracias"),
    (
        re.compile(
            r"(quien sos|que sos|que (podes|sabes) hacer|en que (me )?(podes|puedes) ayudar|que te puedo preguntar)"
        ),
        "capacidades",
    ),
)


def _charla(tipo: str, es_gerencia: bool) -> dict:
    sugerencias = SUGERENCIAS_GERENCIA if es_gerencia else SUGERENCIAS_CONSERJE
    if tipo == "gracias":
        return Respuesta(
            "¡De nada! Si necesitás algo más, preguntame.", "charla", sugerencias=sugerencias[:3]
        ).como_dict()
    texto = (
        "Soy el asistente de MotelOS y funciono acá mismo, sin internet. Te explico cómo usar cualquier parte del "
        "sistema y qué significa cada cosa («¿qué es la tolerancia?»), y te digo cómo está la ventanilla ahora "
        "(libres, ocupadas, vencimientos, la cuenta de una habitación, stock, novedades, pedidos)."
    )
    if es_gerencia:
        texto += (
            " A la gerencia, además, le respondo con los datos del motel: ingresos, turnos, caja, categorías y "
            "pronóstico."
        )
    if tipo == "saludo":
        texto = "¡Hola! " + texto
    return Respuesta(texto, "charla", sugerencias=sugerencias).como_dict()


SUGERENCIAS_GERENCIA = [
    "¿Cuánto facturamos la semana pasada?",
    "¿Quién está de guardia?",
    "¿Qué es la TDC?",
    "¿Cómo cambio una tarifa?",
    "¿Qué novedades hay?",
    "¿Cuántos turnos esperamos mañana?",
]


async def responder(
    db: AsyncSession,
    operador: Operador,
    pregunta: str,
    anterior_pregunta: str | None = None,
    anterior_intencion: str | None = None,
) -> tuple[dict | None, str]:
    """La respuesta del asistente para todo el personal, y la pregunta ya corregida.

    Devuelve (None, texto) cuando es una pregunta de análisis de la gerencia: la responde services.asistente con el
    texto corregido (y la pregunta anterior, si es un seguimiento).
    """
    es_gerencia = operador.rol == ROL_ADMINISTRADOR
    ventanilla = Ventanilla(db)
    await ventanilla.cargar()
    original = normalizar(pregunta)
    if not original:
        return _charla("capacidades", es_gerencia), original

    # 0. Saludos, agradecimientos y «¿qué podés hacer?» (antes de corregir: son palabras de conversación).
    for patron, tipo in CHARLA:
        if patron.search(original):
            return _charla(tipo, es_gerencia), original
    texto = conocimiento.corregir(original, ENTRADAS, ventanilla.palabras_propias())

    # 1. Situaciones conocidas («me equivoqué en el arqueo») y «¿qué es…?», «¿para qué sirve…?»: el glosario.
    definicion = conocimiento.situacion(texto, es_gerencia) or conocimiento.definicion(texto, es_gerencia)
    if definicion is not None:
        return _respuesta_de(definicion, es_gerencia), texto

    pide_instrucciones = bool(COMO.search(texto))
    intencion_datos = _intencion(texto)
    if intencion_datos == "ayuda":  # «necesito ayuda con…»: lo resuelven los temas y la búsqueda, no el análisis
        intencion_datos = None
    tema = _tema(texto, es_gerencia)

    # 2. Instrucciones pedidas con «cómo», «dónde», «qué hago»...
    if tema and pide_instrucciones:
        return _respuesta_de(tema, es_gerencia), texto

    # 3. La ventanilla ahora (lo que el conserje ya ve en su pantalla).
    vivo = await _ventanilla_ahora(ventanilla, texto, es_gerencia, anterior_intencion)
    if vivo is not None:
        return vivo.como_dict(), texto

    # 4. Un tema sin «cómo»: si no es una pregunta de datos, o si pregunta un conserje.
    if tema and (intencion_datos is None or not es_gerencia):
        return _respuesta_de(tema, es_gerencia), texto

    # 5. Análisis de datos (de la gerencia; del conserje, solo lo que no muestra dinero). También los seguimientos
    # («¿y la semana pasada?») de una pregunta de análisis.
    seguimiento = (
        intencion_datos is None
        and anterior_intencion in INTENCIONES_ANALISIS
        and not pide_instrucciones
        and (texto.startswith("y ") or len(texto.split()) <= 4)
    )
    intencion_efectiva = intencion_datos or (anterior_intencion if seguimiento else None)
    fuera_de_alcance = Respuesta(
        "Eso lo responde el asistente de la gerencia (ingresos, caja y análisis del motel). Yo te ayudo a usar el "
        "sistema, te explico cómo funciona y te digo cómo está la ventanilla ahora.",
        "fuera_de_alcance",
        sugerencias=SUGERENCIAS_CONSERJE,
    ).como_dict()
    if intencion_efectiva is not None:
        if es_gerencia:
            return None, texto
        if intencion_efectiva in ANALISIS_CONSERJE:
            ctx = await ia.contexto(db)
            datos = responder_analisis(ctx, texto, anterior_pregunta if seguimiento else None)
            return {**datos, "pasos": [], "acciones": []}, texto
        if intencion_efectiva in DINERO:
            return fuera_de_alcance, texto

    # 6. Búsqueda por parecido en todo el conocimiento, con «¿quisiste decir?».
    parecidas = conocimiento.buscar(texto, ENTRADAS, es_gerencia, 3)
    if parecidas and parecidas[0][0] >= 0.6:
        return _respuesta_de(parecidas[0][1], es_gerencia, [e for _, e in parecidas[1:]]), texto
    if es_gerencia:
        return None, texto
    if intencion_efectiva is not None:
        return fuera_de_alcance, texto
    return Respuesta(
        "No encontré cómo ayudarte con eso. Probá preguntarme cómo hacer algo («¿cómo cobro un turno?»), qué significa "
        "algo («¿qué es la tolerancia?») o cómo está la ventanilla («¿qué habitaciones están libres?»).",
        "desconocida",
        sugerencias=[_como_pregunta(e) for _, e in parecidas] or SUGERENCIAS_CONSERJE,
    ).como_dict(), texto


async def _ventanilla_ahora(
    ventanilla: Ventanilla, texto: str, es_gerencia: bool, anterior: str | None
) -> Respuesta | None:
    if re.search(
        r"como (esta|anda|viene) (la ventanilla|el motel|todo|la cosa)|estado (de la ventanilla|general)"
        r"|resumen de (la )?ventanilla",
        texto,
    ):
        return ventanilla.estado_general()
    if re.search(
        r"quien (esta|tiene|atiende|abrio)|de guardia\b|guardia (actual|abierta|de ahora)"
        r"|(cuando|a que hora) (termina|cierra|cambia|sale)|cuanto (le )?falta (a|para)",
        texto,
    ):
        return await ventanilla.guardia()
    if re.search(r"\b(libres?|disponibles?|desocupad|vacias?|hay lugar)\b", texto):
        return ventanilla.libres()
    if re.search(r"\b(que|cuales|cuantas) (habitaciones )?(estan |hay )?ocupad", texto):
        return ventanilla.ocupadas()
    if re.search(r"\b(venc|por vencer|excedid|se pasaron|termina primero|sale primero)", texto):
        return ventanilla.por_vencer()
    if re.search(r"\b(que|cuales|cuantas|hay) .*\blimpieza\b", texto):
        return ventanilla.en_estado("En Limpieza", "limpieza")
    if re.search(r"\b(que|cuales|cuantas|hay) .*\bmantenimiento\b", texto):
        return ventanilla.en_estado("Mantenimiento", "mantenimiento")
    numero = _numero(texto)
    if numero is not None and (
        re.search(r"\b(debe|cuenta|saldo|cuanto (va|lleva|paga|es|debe)|cuanto le cobro)\b", texto)
        or (anterior == "cuenta" and re.match(r"^(y )?(la |el )?(habitacion )?\d", texto))
    ):
        return await ventanilla.cuenta(numero)
    categoria = ventanilla.categoria_mencionada(texto)
    if (re.search(r"\b(cuanto (sale|cuesta|vale)|precios?|tarifas?)\b", texto) and (categoria or not es_gerencia)) or (
        anterior == "tarifas" and categoria is not None
    ):
        return ventanilla.tarifas_texto(categoria)
    cambiar_algo = re.search(r"\b(cambiar|modificar|subir|bajar|cambio el|cambia el)\b", texto)
    if re.search(r"\bfondo\b", texto) and not COMO.search(texto) and not cambiar_algo:
        return await ventanilla.fondo()
    if re.search(r"\bpedidos?\b", texto) and re.search(r"\b(hay|pendiente|llego|llegaron|recibir|falta)", texto):
        return await ventanilla.pedidos()
    if (
        re.search(r"\bnovedad(es)?\b", texto)
        and re.search(r"\b(hay|que|ultimas?|leer|ver|dejaron)\b", texto)
        and not re.search(r"\b(dejo|dejar|escrib|cargo|cargar)\b", texto)
    ):
        return await ventanilla.novedades()
    if (
        re.search(r"\b(quedan?|hay|stock|tenemos)\b", texto)
        or re.search(r"(poco|bajo|sin) stock|que (falta|hay que reponer)|se (esta|estan) (acabando|agotando)", texto)
        or anterior == "stock"
    ):
        return await ventanilla.stock(texto)
    return None
