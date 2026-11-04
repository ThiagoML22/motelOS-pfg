"""Conocimiento del asistente sobre MotelOS: glosario, reglas del negocio explicadas y búsqueda por parecido.

Complementa los temas de ayuda (services.ayuda) para que el asistente entienda preguntas formuladas de muchas maneras:
- **Sinónimos** («pieza» es habitación, «guita» es plata) y **corrección de errores de tipeo** («factruamos»), con el
  vocabulario del propio sistema (difflib, sin servicios externos).
- **Glosario** para «¿qué es…?», «¿qué significa…?», «¿para qué sirve…?», «¿cómo funciona…?».
- **Búsqueda por parecido** sobre todo el conocimiento cuando ninguna regla coincide: devuelve lo más parecido y
  propone las otras opciones como «¿quisiste decir…?».
"""

import difflib
import re
from dataclasses import dataclass

TODOS = "todos"
GERENCIA = "gerencia"


@dataclass(frozen=True)
class Definicion:
    id: str
    termino: str
    patrones: tuple[str, ...]
    texto: str
    vista: str | None = None
    roles: str = TODOS
    # Palabras que ayudan a encontrarla en la búsqueda por parecido.
    extra: str = ""
    # Situaciones que la piden aunque no se pregunte «¿qué es…?» («me equivoqué en el arqueo»).
    situaciones: tuple[str, ...] = ()


DEFINICIONES: tuple[Definicion, ...] = (
    Definicion(
        "motelos",
        "Qué es MotelOS",
        (r"\bmotel ?os\b", r"este sistema", r"el sistema\b"),
        "MotelOS es el sistema de gestión del motel: la grilla de habitaciones con sus turnos, la caja de cada "
        "guardia con su cierre ciego, el inventario del minibar, la configuración de tarifas y personal, y la "
        "inteligencia de la gerencia. Funciona en el servidor del propio motel, sin depender de internet.",
        extra="programa aplicacion software para que sirve",
    ),
    Definicion(
        "guardia",
        "Guardia",
        (r"\bguardias?\b", r"\bfranjas?\b"),
        "Es el turno de trabajo de un conserje en la ventanilla: hay tres por día (mañana de 6 a 14, tarde de 14 "
        "a 22 y noche de 22 a 6). Cada guardia tiene su caja, que empieza con el fondo de cambio y se cierra con "
        "un arqueo. Solo hay una guardia abierta a la vez.",
        "dashboard",
        extra="horario turno trabajo mañana tarde noche",
    ),
    Definicion(
        "traspaso",
        "Traspaso de guardia",
        (r"\btraspaso\b",),
        "Es lo que recibe quien entra: los turnos en curso, los pedidos sin resolver, las habitaciones en limpieza o "
        "mantenimiento, los arreglos abiertos, las novedades y la ropa. Lo confirma al abrir su guardia y queda "
        "registrado, sin importes ni patentes.",
        "dashboard",
        extra="cambio de guardia recibir entregar",
    ),
    Definicion(
        "traslado",
        "Traslado de turno",
        (r"\btraslado\b",),
        "Es pasar un turno a otra habitación disponible. Conserva su hora, la tarifa con la que entró, su cuenta y el "
        "QR del cliente; la habitación de origen pasa a limpieza, o a mantenimiento si fue por una falla.",
        "dashboard",
        extra="cambiar habitacion mudar cliente",
    ),
    Definicion(
        "arreglo",
        "Arreglo",
        (r"\barreglos?\b",),
        "Es una falla o un mantenimiento de una habitación, con quién lo reparó y, si se sabe, cuánto costó. Cada "
        "habitación tiene su historial. El costo es informativo: no mueve la caja.",
        "dashboard",
        extra="falla reparacion mantenimiento tecnico",
    ),
    Definicion(
        "recuento_ropa",
        "Recuento de ropa",
        (r"recuento de (la )?ropa", r"conteo de (la )?ropa", r"recuento de toallas"),
        "Es contar todas las toallas y sábanas del motel en cada cambio de guardia: limpias, sucias y puestas en las "
        "habitaciones. Quien cierra cuenta a ciegas y quien entra confirma o corrige. Lo que salió a la lavandería, "
        "se compró o se dio de baja se anota aparte, y una diferencia sin explicar la ve la gerencia.",
        "caja",
        extra="toallas sabanas contar lavanderia faltante",
    ),
    Definicion(
        "turno",
        "Turno",
        (r"\bturnos?\b",),
        "Es la estadía de un cliente en una habitación: empieza al abrirla, corre el cronómetro en el servidor y "
        "termina al cobrarla. El turno conserva la tarifa con la que se abrió.",
        "dashboard",
        extra="estadia cliente ocupar",
    ),
    Definicion(
        "estadia_base",
        "Estadía base",
        (r"estadia base", r"tiempo base"),
        "Es el tiempo que incluye el precio base de la categoría (por ejemplo, 2 horas por $8.000). Pasado ese "
        "tiempo se cobra sobreturno.",
        extra="duracion precio base",
    ),
    Definicion(
        "sobreturno",
        "Sobreturno",
        (r"\bsobreturnos?\b",),
        "Es lo que se cobra cuando el cliente se queda más que la estadía base: una fracción (por ejemplo, $2.500 "
        "cada 30 minutos o parte) contada desde el fin de la estadía base, después de la tolerancia si la hay, y "
        "sin pasar el tope de la categoría (RN-DER-01).",
        extra="extra excedido tiempo adicional",
    ),
    Definicion(
        "fraccion",
        "Fracción",
        (r"\bfraccion",),
        "Es cada bloque de tiempo extra que se cobra después de la estadía base (por ejemplo, 30 minutos). Una "
        "fracción empezada se cobra entera.",
        extra="bloque extra",
    ),
    Definicion(
        "tolerancia",
        "Tolerancia",
        (r"\btolerancia",),
        "Son minutos de gracia después de la estadía base antes de cobrar la primera fracción. Si se superan, la "
        "fracción se cuenta desde el fin de la estadía base, no desde el fin de la tolerancia.",
        extra="gracia minutos",
    ),
    Definicion(
        "tope",
        "Tope o pernocte",
        (r"\btope\b", r"\bpernocte"),
        "Es el precio máximo de una estadía en una categoría: por más horas que pasen, la estadía (base más "
        "sobreturno) no cobra más que el tope. Sirve para ofrecer un pernocte.",
        extra="maximo noche",
    ),
    Definicion(
        "categoria",
        "Categoría de habitación",
        (r"\bcategorias?\b",),
        "Cada habitación pertenece a una categoría (Simple, Especial, VIP o las que cree la gerencia), y cada "
        "categoría tiene su color y su tarifa vigente: estadía base, fracción, tolerancia y tope.",
        "configuracion",
        extra="tipo vip simple especial suite",
    ),
    Definicion(
        "tarifa",
        "Tarifa",
        (r"\btarifas?\b",),
        "Es cómo se cobra una estadía en una categoría. Cuando la gerencia la cambia se crea una nueva, que rige "
        "para los turnos que se abran desde ese momento; las anteriores quedan en el historial (RN-DER-06).",
        "configuracion",
        extra="precio cobro",
    ),
    Definicion(
        "tarifa_especial",
        "Tarifa especial",
        (r"tarifas? especial(es)?", r"franjas? (de tarifa|de precio|horaria)"),
        "Es un precio distinto para ciertos días y horas de una categoría, por ejemplo las noches de fin de semana. "
        "El turno toma la que rige cuando se abre y la conserva hasta el cobro; fuera de esos horarios rige la tarifa "
        "general. La noche del viernes sigue el sábado de madrugada.",
        "configuracion",
        extra="noche fin semana horario dia hora franja",
        situaciones=(
            r"por que .{0,30}(mas caro|mas barato|cobra mas|cobro mas|sale mas|cambio el precio|otro precio)",
            r"(precio|tarifa) (distint|diferent|cambi)\w* .{0,20}(noche|hora|dia)",
        ),
    ),
    Definicion(
        "arqueo",
        "Arqueo",
        (r"\barqueos?\b",),
        "Es el recuento de la caja al cerrar la guardia: el conserje declara lo que hay en efectivo, POSNET y "
        "Mercado Pago, y el sistema lo compara con lo que registró (más el fondo de cambio). Confirmado, no se "
        "modifica (RN-RES-02) y tiene su comprobante en PDF.",
        "caja",
        extra="recuento cierre caja contar",
    ),
    Definicion(
        "cierre_ciego",
        "Cierre ciego",
        (r"cierre ciego", r"\bciego\b", r"rn ?res ?03"),
        "Mientras la guardia está abierta, nadie (ni el conserje ni la gerencia ni yo) ve el total "
        "que espera el sistema. El conserje cuenta la gaveta sin saber cuánto «debería» haber, y recién al "
        "confirmar ve la diferencia. Así el recuento es honesto (RN-RES-03).",
        "caja",
        extra="total oculto no se ve caja",
        situaciones=(
            r"por que no (veo|se ve|aparece|me muestra)",
            r"no (veo|me aparece|me muestra) (cuanta|el total|la plata|lo que)",
        ),
    ),
    Definicion(
        "tdc",
        "TDC (tasa de discrepancia de caja)",
        (r"\btdc\b", r"tasa de discrepancia"),
        "Es la proporción de arqueos con diferencia (faltante o sobrante) sobre el total. La línea de base del "
        "motel era 10%: por encima, la caja se está descuadrando más de lo normal.",
        "gerencia",
        GERENCIA,
        extra="indicador porcentaje diferencias",
    ),
    Definicion(
        "faltante",
        "Faltante y sobrante",
        (r"\bfaltantes?\b", r"\bsobrantes?\b"),
        "Faltante: se declaró menos de lo que registró el sistema. Sobrante: se declaró más. Correcto: coinciden "
        "exacto. La diferencia la calcula la base de datos al confirmar el arqueo (RN-DER-03).",
        "gerencia",
        extra="diferencia caja descuadre",
    ),
    Definicion(
        "fondo",
        "Fondo de cambio",
        (r"fondo de cambio", r"\bfondo\b"),
        "Es el efectivo con el que empieza cada caja para dar vuelto (lo fija la gerencia). Se suma al efectivo "
        "que espera el sistema en el arqueo. Un cambio rige desde la guardia siguiente.",
        extra="vuelto cambio inicial",
    ),
    Definicion(
        "supervisado",
        "Cierre supervisado",
        (r"supervisad",),
        "Si un conserje se fue sin cerrar su caja, la gerencia la cierra por él: cuenta la gaveta, declara a "
        "ciegas y deja una observación. El arqueo queda a nombre del conserje y registra quién lo confirmó.",
        "gerencia",
        GERENCIA,
        extra="abandonada se fue",
    ),
    Definicion(
        "saldo_exacto",
        "Cobro exacto",
        (r"rn ?exi ?03", r"saldo exacto", r"monto exacto"),
        "Un turno solo se cierra cuando lo cobrado cubre exactamente el saldo: ni de más ni de menos "
        "(RN-EXI-03). Así cada peso de la caja corresponde a un turno.",
        extra="pago justo",
    ),
    Definicion(
        "cobro_cruzado",
        "Cobro de un turno de la guardia anterior",
        (r"rn ?der ?04", r"cobro cruzado", r"turno de (la )?guardia anterior"),
        "Si un turno se abrió en una guardia y se cobra en la siguiente, el cobro entra en la caja de quien lo "
        "cobra (RN-DER-04). El turno muestra quién lo abrió.",
        extra="anterior otra guardia",
    ),
    Definicion(
        "inmutable",
        "Por qué no se puede corregir un arqueo",
        (r"rn ?res ?02", r"corregir (un )?arqueo", r"modificar (un )?arqueo"),
        "Los arqueos, las guardias cerradas, los turnos cobrados y los registros no se modifican ni se borran: "
        "la base de datos lo impide (RN-RES-02). Un error se aclara con una observación o una novedad, no "
        "cambiando la historia.",
        extra="borrar editar cambiar",
        situaciones=(
            r"me equivoque",
            r"(corregir|modificar|borrar|cambiar|arreglar).{0,25}arqueo",
            r"arqueo.{0,40}(corregir|modificar|borrar|cambiar|arreglar)",
        ),
    ),
    Definicion(
        "patente",
        "Patente",
        (r"\bpatentes?\b", r"rnf ?08"),
        "Se carga al abrir el turno para identificar el vehículo y se borra sola 24 horas después de cerrado "
        "(RNF-08): no queda en el historial.",
        extra="auto vehiculo dominio privacidad",
    ),
    Definicion(
        "reconexion",
        "Corte de conexión",
        (r"rnf ?09", r"reconex"),
        "Si se corta la conexión con el servidor aparece un aviso y no se pueden abrir ni cobrar turnos. Los "
        "cronómetros siguen en el servidor; al volver, la ventanilla se actualiza sola en menos de 5 segundos "
        "(RNF-09).",
        extra="internet red caida",
    ),
    Definicion(
        "bloqueo",
        "Usuario bloqueado",
        (r"bloquead", r"no puedo (entrar|ingresar)", r"intentos"),
        "Después de 5 claves incorrectas seguidas el usuario queda bloqueado 15 minutos. Si no recordás la clave, "
        "la gerencia la restablece desde Configuración → Conserjes.",
        extra="login clave incorrecta acceso",
        situaciones=(r"no (puedo|me deja) (entrar|ingresar|loguear)", r"\bbloquead"),
    ),
    Definicion(
        "sesion",
        "Duración de la sesión",
        (r"\bsesion\b",),
        "La sesión dura una guardia de 8 horas más una de margen. Si vence, el sistema pide ingresar de nuevo. "
        "Cerrar sesión está en el menú de tu nombre, arriba a la derecha.",
        extra="vence salir",
        situaciones=(r"se me cerro (la )?sesion", r"me (saco|echo) del sistema"),
    ),
    Definicion(
        "novedad",
        "Novedad",
        (r"\bnovedad(es)?\b",),
        "Es una nota que el personal deja para la guardia siguiente y para la gerencia (por ejemplo, «la 7 tiene "
        "la ducha floja»). Se puede marcar como importante y asociar a una habitación. No se borra.",
        "dashboard",
        extra="nota aviso mensaje",
    ),
    Definicion(
        "actividad",
        "Registro de actividad",
        (r"registro de actividad", r"\bactividad\b", r"por revisar"),
        "Guarda cada cambio de inventario y configuración con quién lo hizo y en qué guardia. Lo que carga un "
        "conserje queda «por revisar» hasta que la gerencia lo marca como visto.",
        "actividad",
        GERENCIA,
        extra="auditoria cambios historial",
    ),
    Definicion(
        "pedido",
        "Pedido de reposición",
        (r"\bpedidos?\b",),
        "La gerencia arma un pedido al proveedor (puede partir de la reposición sugerida) y lo descarga en PDF. "
        "Cuando llega la mercadería, el conserje o la gerencia lo recibe con lo que vino de verdad, que se suma "
        "al stock.",
        "inventario",
        extra="proveedor compra mercaderia",
    ),
    Definicion(
        "reposicion",
        "Reposición sugerida",
        (r"reposicion sugerida",),
        "Es lo que conviene pedir de cada artículo para cubrir dos semanas, según lo vendido en los últimos 28 "
        "días (la última semana pesa el doble), redondeado a packs de 6.",
        "inteligencia",
        GERENCIA,
        extra="stock comprar sugerencia",
    ),
    Definicion(
        "inteligencia",
        "Inteligencia",
        (r"\binteligencia\b", r"\bpronostico"),
        "Es el análisis de la gerencia, calculado en el propio servidor: resumen del día, alertas (faltantes, "
        "habitaciones poco usadas, stock), pronóstico de 24 horas con su error medido, sugerencias de tarifa "
        "simuladas sobre las estadías reales y reposición. Solo mira lo ya arqueado.",
        "inteligencia",
        GERENCIA,
        extra="analisis prediccion ia",
    ),
    Definicion(
        "pronostico_metodo",
        "Cómo se calcula el pronóstico",
        (r"como (se calcula|funciona) el pronostico",),
        "Para cada hora se promedia la misma hora del mismo día en las 8 semanas anteriores (lo más reciente pesa "
        "más) y se ajusta por la tendencia de las últimas dos semanas. La ocupación suma las estadías que siguen "
        "según cuánto duran en este motel.",
        "inteligencia",
        extra="prediccion estimacion metodo",
    ),
    Definicion(
        "multiinquilino",
        "Varios moteles en el mismo sistema",
        (r"multiinquilino", r"varios moteles", r"otro motel", r"codigo del (motel|establecimiento)"),
        "Cada motel entra con su código y solo ve sus datos: la base de datos lo garantiza con seguridad por fila "
        "(Row Level Security). La plataforma da de alta y suspende moteles, sin ver su operación.",
        extra="establecimiento empresa sucursal",
    ),
    Definicion(
        "ocupacion",
        "Ocupación",
        (r"\bocupacion\b",),
        "Es la parte del tiempo que las habitaciones estuvieron ocupadas: minutos con un turno abierto sobre los "
        "minutos disponibles.",
        extra="porcentaje uso",
    ),
    Definicion(
        "ticket",
        "Ticket promedio",
        (r"ticket promedio",),
        "Es lo que deja en promedio cada turno: estadía, sobreturno y consumos, dividido la cantidad de turnos.",
        roles=GERENCIA,
        extra="gasto promedio",
    ),
    Definicion(
        "medios",
        "Medios de pago",
        (r"medios? de pago", r"\bposnet\b", r"mercado ?pago"),
        "Se cobra en efectivo, con POSNET (tarjeta; se carga el número de comprobante) o con Mercado Pago. Cada "
        "medio se declara por separado en el arqueo.",
        extra="tarjeta efectivo transferencia qr",
        situaciones=(r"(pagar|paga|pagan|cobrar|cobro) (con|en) (posnet|mercado pago|efectivo)", r"quiere pagar"),
    ),
    Definicion(
        "modo_oscuro",
        "Modo oscuro",
        (r"modo oscuro", r"\blunita\b"),
        "La lunita del encabezado cambia entre modo claro y oscuro con una animación. Cada puesto recuerda su "
        "elección; en Mi perfil se puede seguir al sistema operativo.",
        extra="tema noche colores",
    ),
    Definicion(
        "comprobante",
        "Comprobantes en PDF",
        (r"comprobante", r"\bpdf\b"),
        "Al cerrar la caja se descarga el comprobante del arqueo para firmar; la gerencia también descarga el "
        "informe mensual de arqueos y el PDF de cada pedido.",
        extra="imprimir firmar documento",
    ),
    Definicion(
        "colores",
        "Colores y modo oscuro",
        (r"\bcolor(es)?\b", r"\bapariencia\b"),
        "El color de marca del motel lo elige la gerencia en Configuración → Apariencia y avisos. Cada puesto puede "
        "pasar a modo oscuro con la lunita del encabezado.",
        roles="conserje",
        extra="color tema diseño",
        situaciones=(r"cambi\w* (el )?color", r"\bcolor del sistema"),
    ),
    Definicion(
        "cambio_habitacion",
        "El cliente quiere cambiarse de habitación",
        (r"cambiar(se)? de habitacion",),
        "Se puede: abrí la habitación ocupada y tocá «Trasladar». El turno sigue igual, con su hora, la tarifa con la "
        "que entró, su cuenta y el QR del cliente. Elegí el motivo: si fue por una falla, la habitación queda en "
        "mantenimiento con el arreglo abierto.",
        "dashboard",
        extra="mudar trasladar otra pieza",
        situaciones=(r"(cambiar|cambiarse|pasar|mudar|trasladar)\w* (de|a otra) habitacion", r"quiere otra habitacion"),
    ),
    Definicion(
        "turno_error",
        "Un turno abierto por error",
        (r"turno (por error|equivocado)",),
        "Un turno abierto no se borra: queda en la historia (RN-RES-01). Si fue un error, avisale a la gerencia y "
        "dejá una novedad explicándolo; la inteligencia marca los turnos de menos de 10 minutos para revisarlos.",
        extra="error equivocacion borrar anular",
        situaciones=(
            r"(abri|cargue|registre) .{0,20}(por error|mal|equivocad)",
            r"(borrar|anular|cancelar) (un |el )?turno",
        ),
    ),
    Definicion(
        "consumo_error",
        "Un consumo cargado por error",
        (r"consumo (por error|equivocado)",),
        "Un consumo cargado no se borra desde la ventanilla. Avisale a la gerencia y dejá una novedad con el detalle "
        "(habitación, artículo y cantidad) para que lo tenga en cuenta.",
        extra="minibar error quitar",
        situaciones=(
            r"(cargue|puse|agregue) .{0,25}(consumo|bebida|articulo).{0,20}(mal|de mas|por error)",
            r"(borrar|quitar|sacar|anular) (un |el )?consumo",
        ),
    ),
    Definicion(
        "descuentos",
        "Descuentos y promociones",
        (r"\bdescuentos?\b", r"\bpromo(cion)?(es)?\b"),
        "El cobro tiene que cubrir exactamente el saldo (RN-EXI-03): no hay descuentos manuales en la ventanilla. "
        "Una promoción se hace con una tarifa especial para ciertos días y horas (lo hace la gerencia); la "
        "inteligencia sugiere cuándo conviene.",
        extra="rebaja oferta cortesia gratis",
        situaciones=(r"\b(descuento|rebaja|cortesia|gratis|regalar)",),
    ),
    Definicion(
        "proxima_libre",
        "La próxima libre",
        (r"proxima libre", r"proxima disponible"),
        "Es la estimación de cuándo queda disponible cada habitación. Mira cuánto lleva el turno, cuánto les faltó a "
        "las estadías de esa categoría que llegaron a ese tiempo, y suma una limpieza típica. Aparece en Habitaciones "
        "cuando quedan dos disponibles o menos. Es una estimación: el cliente puede irse antes o quedarse más.",
        "dashboard",
        extra="estimacion espera cuanto falta se libera",
    ),
    Definicion(
        "cliente_perdido",
        "Un cliente perdido",
        (r"clientes? perdidos?",),
        "Es el cliente que llegó y se fue sin quedarse: no había lugar, no quiso esperar o le pareció caro. El "
        "conserje lo registra con «Se fue un cliente» en Habitaciones, sin ningún dato de la persona. Así la gerencia "
        "ve la demanda que no se atendió, que de otro modo no queda en ninguna parte.",
        "dashboard",
        extra="demanda perdida rechazado lleno completo",
    ),
    Definicion(
        "gemelo",
        "El gemelo del motel",
        (r"\bgemelo\b", r"simulador del motel"),
        "Es un simulador que repite lo que pasó de verdad: cada llegada de los últimos 30 días, con su duración y lo "
        "que pagó, más los clientes que se fueron. Le cambiás la limpieza, las habitaciones o el precio y te dice "
        "cuántos turnos, clientes perdidos e ingresos daría, sin tocar nada del sistema. Compara dos corridas del "
        "mismo modelo y dice cuánto del pasado real reproduce. No descuenta costos, y el efecto del precio es un "
        "supuesto.",
        "inteligencia",
        GERENCIA,
        extra="simular probar escenario que pasaria cambio",
    ),
    Definicion(
        "huella",
        "La huella de un comprobante",
        (
            r"\bhuellas?( de un comprobante)?\b",
            r"comprobantes? verificables?",
            r"cadena de (comprobantes|arqueos|huellas)",
        ),
        "Es un código que sale de los datos del arqueo, de sus cobros y de la huella del arqueo anterior. Si alguien "
        "cambia un importe directamente en la base, la huella deja de coincidir; y si la recalcula, se corta la cadena "
        "con el siguiente. Va impresa en el comprobante firmado, así el papel también sirve de testigo. Se verifica en "
        "Control de caja.",
        "gerencia",
        GERENCIA,
        extra="integridad alterado sello hash",
    ),
    Definicion(
        "ticket_cliente",
        "El ticket con QR del cliente",
        (r"ticket (con qr|del cliente|para el cliente)", r"\bqr del cliente\b", r"pedidos? del cliente"),
        "Es un ticket que se le da al cliente al entrar. Con el QR ve en su celular su tiempo y su cuenta, pide del "
        "minibar, avisa que se queda más o pide la cuenta, sin llamar y sin dar datos personales. Lo que pide llega a "
        "la ventanilla: quien atiende lo entrega y recién ahí se carga a la cuenta. El enlace vale mientras dura el "
        "turno.",
        "dashboard",
        extra="celular escanear codigo pedir habitacion",
    ),
    Definicion(
        "calificacion",
        "La calificación del cliente",
        (r"calificacion(es)? (del|de los) clientes?", r"\bque es (la|una) calificacion\b", r"\bopiniones?\b"),
        "Al irse, el cliente puede poner de 1 a 5 y marcar lo que falló, desde el QR y hasta una hora después del "
        "cobro. Es anónima: no guarda datos de la persona ni texto libre, y la gerencia solo ve totales por "
        "habitación.",
        "inteligencia",
        extra="puntaje estrellas queja cliente anonima",
    ),
    Definicion(
        "limpieza_sin_turno",
        "Una limpieza sin turno",
        (r"limpiezas? sin (un )?turno",),
        "Es una habitación que pasó a limpieza a mano, sin que se haya cobrado un turno antes. Puede ser un repaso de "
        "rutina o una estadía que no se registró: por eso la inteligencia las muestra y dice quién las marcó, pero no "
        "alcanza para sacar conclusiones. Conviene cruzarlas con las novedades y con el stock del minibar.",
        "inteligencia",
        GERENCIA,
        extra="fantasma registro manual rotacion",
    ),
)

# Sinónimos: se reemplazan antes de interpretar la pregunta.
SINONIMOS = {
    "pieza": "habitacion",
    "piezas": "habitaciones",
    "cuarto": "habitacion",
    "cuartos": "habitaciones",
    "hab": "habitacion",
    "habitaciónes": "habitaciones",
    "guita": "plata",
    "dinero": "plata",
    "mosca": "plata",
    "recaudamos": "facturamos",
    "ganamos": "facturamos",
    "vendimos": "vendimos",
    "laburante": "conserje",
    "empleado": "conserje",
    "empleados": "conserjes",
    "recepcionista": "conserje",
    "encargado": "gerencia",
    "jefe": "gerencia",
    "contrasena": "clave",
    "password": "clave",
    "pass": "clave",
    "boleta": "comprobante",
    "factura": "comprobante",
    "tarjeta": "posnet",
    "debito": "posnet",
    "credito": "posnet",
    "mp": "mercado pago",
    "heladera": "minibar",
    "frigobar": "minibar",
    "tele": "tv",
    "turnito": "turno",
    "finde": "fin de semana",
}

PALABRAS_VACIAS = set(
    "a al algo algun alguna como con cual cuales cuando de del donde el ella en es esa ese esta este hay la las le lo "
    "los me mi mis muy no nos o para pero por que se si sin sobre su sus te tengo tiene tu un una uno unos y ya yo "
    "puedo podes quiero necesito hacer hace saber decime dime explica explicame".split()
)

# Vocabulario del dominio para corregir errores de tipeo (además de las palabras del conocimiento).
VOCABULARIO_BASE = set(
    "facturamos facturacion ingresos turnos turno habitacion habitaciones ocupacion ocupadas ocupada libres libre "
    "disponibles limpieza mantenimiento sobreturno faltantes faltante sobrantes arqueo arqueos guardia guardias "
    "conserje conserjes gerencia categoria categorias tarifa tarifas estadia reponer reposicion articulos articulo "
    "stock pronostico manana semana pasada anterior ayer anteayer octubre noviembre diciembre septiembre agosto "
    "promedio ticket cobrar cobrado cobro cierre cerrar caja efectivo posnet mercado minibar consumo consumos "
    "novedades novedad pedido pedidos proveedor inventario configuracion actividad inteligencia patente "
    "comprobante tolerancia fraccion pernocte cuanto cuantos cuantas cuales vence vencimiento excedidas sabados "
    "domingos viernes lunes martes miercoles jueves facturo cobramos vendimos cerveza agua gaseosa chocolate "
    # Palabras de conversación que no hay que «corregir» hacia términos del sistema.
    "libera libere liberan liberen liberar liberara desocupa esperar espera habilita registra escribi "
    "cargale cargame agregale agregame sumale sumame anotame anotale poneme pasame dejame liberame abrime ocupame "
    "cobrale cerrale cliente perdido mot "
    "toalla toallas sabana sabanas ropa lavanderia arreglo arreglos falla fallas traslado trasladar traslada "
    "trasladame "
    "traspaso recuento conteo mudar muda mudame "
    "especial especiales franja franjas noche noches tarde madrugada mediodia siesta sabado domingo miercoles rige "
    "gracias hola buenas buenos genial perfecto listo barbaro necesito quiero podes puedes sabes ayuda ayudame favor "
    "porfa tardes noches dias entonces bueno claro cliente clientes quejo quedarse momento ahora mismo pagar pagan "
    "cobrar abrir cerrar dejar poner sacar cambiar agregar quiere quieren puede tiene tienen hacer llego llegaron "
    "falta faltan armar exportar descargar recibir equivoque "
    # Palabras comunes del castellano que se parecen a términos del sistema («estado» no es «estadía»).
    "estado estados estoy estamos estaba ventana ventanilla sistema cosas todos todas misma porque cuando donde "
    "quien cuanto cuanta mucho mejor primero primera ultimo ultima siempre nunca tambien despues antes ayudar entrar "
    "salir sesion turnos dentro afuera arriba abajo pantalla boton menu opcion opciones nuevo nueva".split()
)


def _sin_tildes(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[a-zñ0-9]+", _sin_tildes(texto.lower()))


def _raiz(palabra: str) -> str:
    """Raíz simple para comparar formas de una misma palabra (cobro, cobrar, cobrado → cobr)."""
    return palabra[:4] if len(palabra) >= 5 else palabra


def _textos_de(entrada) -> tuple[str, str, str]:
    """(título, claves, cuerpo) de un tema o una definición, para indexar."""
    if isinstance(entrada, Definicion):
        return entrada.termino, entrada.extra, entrada.texto
    return entrada.titulo, " ".join(re.sub(r"[^a-z ]", " ", c) for c in entrada.claves), " ".join(entrada.pasos)


_VOCABULARIO: set[str] | None = None


def vocabulario(entradas) -> set[str]:
    global _VOCABULARIO
    if _VOCABULARIO is None:
        palabras = set(VOCABULARIO_BASE)
        for entrada in entradas:
            for parte in _textos_de(entrada):
                palabras.update(p for p in _palabras(parte) if len(p) >= 5)
        _VOCABULARIO = palabras
    return _VOCABULARIO


def corregir(texto: str, entradas, propias: set[str] | None = None) -> str:
    """Aplica sinónimos y corrige palabras mal escritas con la más parecida del vocabulario del sistema. `propias` son
    palabras del motel (categorías, artículos, nombres) que no se tocan y también sirven de referencia."""
    palabras = texto.split()
    salida = []
    vocab = vocabulario(entradas) | (propias or set())
    for palabra in palabras:
        if palabra in SINONIMOS:
            salida.append(SINONIMOS[palabra])
            continue
        if len(palabra) >= 6 and palabra.isalpha() and palabra not in vocab:
            # Un error de tipeo casi nunca cambia la primera letra ni el largo en más de dos.
            candidatas = [v for v in vocab if v[:1] == palabra[:1] and abs(len(v) - len(palabra)) <= 2]
            parecida = difflib.get_close_matches(palabra, candidatas, n=1, cutoff=0.8)
            if parecida:
                salida.append(parecida[0])
                continue
        salida.append(palabra)
    return " ".join(salida)


def buscar(texto: str, entradas, es_gerencia: bool, cantidad: int = 3) -> list[tuple[float, object]]:
    """Las entradas más parecidas a la pregunta: el título pesa triple, las claves doble y el cuerpo simple."""
    consulta = {_raiz(p) for p in _palabras(texto) if p not in PALABRAS_VACIAS and len(p) > 2}
    if not consulta:
        return []
    puntajes = []
    for entrada in entradas:
        rol = getattr(entrada, "roles", TODOS)
        if rol == GERENCIA and not es_gerencia or rol == "conserje" and es_gerencia:
            continue
        titulo, claves, cuerpo = (
            {_raiz(p) for p in _palabras(parte) if p not in PALABRAS_VACIAS and len(p) > 2}
            for parte in _textos_de(entrada)
        )
        puntos = sum(3 if r in titulo else 2 if r in claves else 1 if r in cuerpo else 0 for r in consulta)
        if puntos:
            puntajes.append((puntos / (len(consulta) + 2), entrada))
    puntajes.sort(key=lambda p: -p[0])
    return puntajes[:cantidad]


PREGUNTA_DEFINICION = re.compile(
    r"^(que (es|son|significa|quiere decir)|para que (sirve|sirven|esta)|como funciona|explica(me)?|definicion de|"
    r"que onda con)\b"
)


def definicion(texto: str, es_gerencia: bool) -> Definicion | None:
    """La definición que pide una pregunta del tipo «¿qué es…?» (con su patrón o, si no, la más parecida)."""
    if not PREGUNTA_DEFINICION.search(texto):
        return None
    resto = PREGUNTA_DEFINICION.sub("", texto).strip()
    candidatas = [d for d in DEFINICIONES if d.roles == TODOS or (d.roles == GERENCIA) == es_gerencia]
    # La coincidencia más larga: «limpieza sin turno» es más precisa que «turno».
    elegida, largo = None, 0
    for d in candidatas:
        for patron in d.patrones:
            coincidencia = re.search(patron, resto)
            if coincidencia and len(coincidencia.group(0)) > largo:
                elegida, largo = d, len(coincidencia.group(0))
    if elegida is not None:
        return elegida
    mejores = buscar(resto, candidatas, es_gerencia, 1)
    return mejores[0][1] if mejores and mejores[0][0] >= 0.5 else None


def situacion(texto: str, es_gerencia: bool) -> Definicion | None:
    """La definición que corresponde a una situación descrita («me equivoqué en el arqueo»), aunque no se pregunte
    «¿qué es…?». Las de rol «conserje» solo se le dan al conserje (la gerencia tiene el tema con los pasos)."""
    for d in DEFINICIONES:
        if d.roles == GERENCIA and not es_gerencia or d.roles == "conserje" and es_gerencia:
            continue
        if any(re.search(p, texto) for p in d.situaciones):
            return d
    return None
