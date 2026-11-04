export type RoomStatus = 'Libre' | 'Ocupada' | 'En Limpieza' | 'Mantenimiento';
export type TipoCliente = 'Auto' | 'Moto' | 'Peaton';
export type MedioPago = 'EFECTIVO' | 'POSNET' | 'MERCADO_PAGO';

export interface Habitacion {
  id: number;
  numero: number;
  estado: RoomStatus;
}

export interface Turno {
  id: string;
  habitacion_id: number;
  identificador_vehicular?: string | null;
  tipo_cliente: TipoCliente;
  hora_inicio: string;
  hora_fin?: string | null;
  estado: string;
  tarifa_base: number;
  total_sobreturno: number;
  total_consumos: number;
  total_general: number;
  abierto_por?: string | null;
  // Estadía base de la tarifa del turno (depende de la categoría de la habitación).
  estadia_base_min?: number | null;
}

export interface TurnoCreate {
  habitacion_id: number;
  identificador_vehicular?: string;
  tipo_cliente: TipoCliente;
  // La tarifa que se le mostró a quien atiende: si justo cambió, el servidor no abre el turno.
  tarifa_id?: number;
}

export interface Consumo {
  id: string;
  articulo_id: number;
  cantidad: number;
  precio_unitario: number;
  subtotal: number;
}

export interface Articulo {
  id: number;
  codigo: string;
  descripcion: string;
  precio_unitario: number;
  stock_actual: number;
  categoria?: string | null;
  // RF-11: la ventanilla solo recibe artículos activos; el panel de configuración los ve todos.
  activo?: boolean;
}

export interface TarifaDelTurno {
  categoria?: string | null;
  color?: string | null;
  franja?: string | null;
  tarifa_base: number;
  estadia_base_min: number;
  fraccion_min: number;
  tarifa_fraccion: number;
  tolerancia_min: number;
  tope?: number | null;
}

export interface TurnoResumen extends Turno {
  minutos_transcurridos: number;
  total_pagado: number;
  saldo_pendiente: number;
  consumos: Consumo[];
  tarifa?: TarifaDelTurno | null;
}

export interface PagoItem {
  medio_pago: MedioPago;
  monto: number;
  comprobante_referencia?: string;
}

export interface ConstanciaCobro {
  turno_id: string;
  habitacion_numero: number;
  hora_inicio: string;
  hora_fin: string;
  tarifa_base: number;
  total_sobreturno: number;
  total_consumos: number;
  total_general: number;
  total_pagado: number;
  saldo_pendiente: number;
  pagos: PagoItem[];
}

export interface HabitacionConDetalles extends Habitacion {
  categoria_id?: number | null;
  turno_activo?: Turno | null;
}

// --- Sesión y caja (prototipo v2) ---

// PLATAFORMA: el equipo que da de alta establecimientos (multiinquilino); no opera ningún motel.
export type Rol = 'OPERADOR' | 'ADMINISTRADOR' | 'PLATAFORMA';

export interface Operador {
  id: number;
  usuario: string;
  nombre_visible: string;
  rol: Rol;
}

export interface OperadorEstado extends Operador {
  activo: boolean;
  ultimo_acceso?: string | null;
  bloqueado_hasta?: string | null;
}

// La guardia abierta en la ventanilla. Nunca trae importes (RN-RES-03).
export interface Guardia {
  id: number;
  franja: '06:00' | '14:00' | '22:00';
  estado: 'Abierta' | 'Cerrada';
  abierta_en: string;
  cerrada_en?: string | null;
  operador_id: number;
  operador_nombre: string;
  fondo_inicial: number;
  es_propia: boolean;
}

export interface EstablecimientoPublico {
  id: number;
  codigo: string;
  nombre: string;
  // Apariencia y avisos (migración 009).
  color_marca?: string | null;
  eslogan?: string | null;
  aviso_por_vencer_min?: number;
  alertas_sonoras?: boolean;
}

// Lo que el ingreso muestra al reconocer el código de un motel.
export interface MarcaPublica {
  codigo: string;
  nombre: string;
  color_marca: string | null;
  eslogan: string | null;
}

// Novedades de guardia (migración 009).
export interface Novedad {
  id: number;
  texto: string;
  importante: boolean;
  creado_en: string;
  operador_id: number;
  operador_nombre: string;
  guardia_id: number | null;
  franja: string | null;
  habitacion_id: number | null;
  habitacion_numero: number | null;
}

export interface Sesion {
  operador: Operador;
  // Nulo para la plataforma.
  establecimiento: EstablecimientoPublico | null;
  guardia: Guardia | null;
}

export interface DeclaracionCaja {
  efectivo: number;
  posnet: number;
  mercado_pago: number;
}

export type CategoriaArqueo = 'Correcto' | 'Faltante' | 'Sobrante';

export interface Arqueo {
  id: number;
  guardia_id: number;
  franja: string;
  abierta_en: string;
  cerrada_en?: string | null;
  operador_id: number;
  operador_nombre: string;
  declarado_efectivo: number;
  declarado_posnet: number;
  declarado_mercado_pago: number;
  total_declarado: number;
  sistema_efectivo: number;
  sistema_posnet: number;
  sistema_mercado_pago: number;
  total_sistema: number;
  fondo_inicial: number;
  diferencia: number;
  categoria: CategoriaArqueo;
  confirmado_en: string;
  // Cierre supervisado: lo confirmó la gerencia porque el conserje dejó la guardia abierta.
  supervisado: boolean;
  confirmado_por_nombre?: string | null;
  observacion?: string | null;
}

export interface PagoDetalle {
  registrado_en: string;
  habitacion_numero: number;
  medio_pago: MedioPago;
  monto: number;
  comprobante_referencia?: string | null;
}

export interface ArqueoDetalle extends Arqueo {
  pagos: PagoDetalle[];
  huella?: string | null;
  codigo?: string | null;
  secuencia?: number | null;
}

export interface MetricaCaja {
  operador_id?: number | null;
  operador_nombre?: string | null;
  arqueos: number;
  correctos: number;
  faltantes: number;
  sobrantes: number;
  total_faltante: number;
  total_sobrante: number;
  tdc: number;
}

// --- Panel de configuración de la gerencia (RF-11, prototipo v3) ---

export interface TarifaDatos {
  tarifa_base: number;
  estadia_base_min: number;
  fraccion_min: number;
  tarifa_fraccion: number;
  // Minutos de gracia antes de la primera fracción y precio máximo de la estadía (pernocte). Migración 008.
  tolerancia_min: number;
  tope?: number | null;
  categoria_id?: number;
}

export interface Tarifa extends TarifaDatos {
  id: number;
  nombre: string;
  categoria_id: number;
  vigente: boolean;
  vigente_desde: string;
  franja_id?: number | null;
  franja?: string | null;
}

// Tarifa especial (migración 014): cuándo rige y con qué tarifa. `dias` es una máscara: lunes = 1 ... domingo = 64.
export interface Franja {
  id: number;
  categoria_id: number;
  nombre: string;
  dias: number;
  desde: string;
  hasta: string;
  regla: string;
  tarifa?: Tarifa | null;
}

export interface FranjaAlta {
  categoria_id: number;
  nombre: string;
  dias: number;
  desde: string;
  hasta: string;
  tarifa: TarifaDatos;
}

export type FranjaCambio = Partial<Omit<FranjaAlta, 'categoria_id'>>;

// Lo que tomaría un turno abierto ahora y cuándo deja de regir.
export interface TarifaAhora extends Tarifa {
  cambia_en?: string | null;
  cambia_a?: string | null;
  cambia_a_precio?: number | null;
}

// Categoría de habitación (Simple, Especial, VIP...) con su tarifa general, la que rige ahora y las especiales.
export interface Categoria {
  id: number;
  nombre: string;
  descripcion?: string | null;
  color: string;
  orden: number;
  activa: boolean;
  habitaciones: number;
  tarifa?: Tarifa | null;
  tarifa_ahora?: TarifaAhora | null;
  franjas?: Franja[];
}

export interface CategoriaDatos {
  nombre?: string;
  descripcion?: string | null;
  color?: string;
  orden?: number;
  activa?: boolean;
}

export interface CategoriaAlta {
  nombre: string;
  descripcion?: string | null;
  color: string;
  orden: number;
  tarifa: TarifaDatos;
}

export interface Perfil {
  id: number;
  usuario: string;
  nombre_visible: string;
  rol: Rol;
  establecimiento_nombre?: string | null;
  establecimiento_codigo?: string | null;
  creado_en: string;
  ultimo_acceso?: string | null;
  guardias_30_dias: number;
  turnos_30_dias: number;
  arqueos_30_dias: number;
}

export interface FondoCambio {
  fondo_cambio: number;
  actualizado_en?: string | null;
}

export interface HabitacionConfiguracion {
  id: number;
  numero: number;
  estado: RoomStatus;
  activa: boolean;
  categoria_id: number;
}

export interface ArticuloCambios {
  descripcion?: string;
  categoria?: string | null;
  precio_unitario?: number;
  stock_actual?: number;
  activo?: boolean;
}

export interface ConserjeAlta {
  usuario: string;
  nombre_visible: string;
  clave: string;
}

// Turnos cobrados (en guardias ya arqueadas), ingresos y ocupación de una categoría de habitación.
export interface ResumenCategoria {
  categoria_id: number;
  nombre: string;
  color: string;
  turnos: number;
  ingresos: number;
  consumos: number;
  minutos_promedio: number;
  ticket_promedio: number;
  habitaciones: number;
  ocupadas: number;
}

export interface MetricasCaja {
  desde?: string | null;
  hasta?: string | null;
  general: MetricaCaja;
  por_operador: MetricaCaja[];
}

// --- Multiinquilino y registro de actividad (demostración del Sprint 4) ---

export interface Establecimiento extends EstablecimientoPublico {
  domicilio?: string | null;
  telefono?: string | null;
  leyenda_comprobante?: string | null;
  wifi_nombre?: string | null;
  wifi_clave?: string | null;
  bienvenida?: string | null;
  activo: boolean;
  creado_en: string;
}

export interface EstablecimientoDatos {
  nombre?: string;
  domicilio?: string | null;
  telefono?: string | null;
  leyenda_comprobante?: string | null;
  color_marca?: string | null;
  eslogan?: string | null;
  aviso_por_vencer_min?: number;
  alertas_sonoras?: boolean;
  wifi_nombre?: string | null;
  wifi_clave?: string | null;
  bienvenida?: string | null;
}

export interface EstablecimientoResumen extends Establecimiento {
  habitaciones: number;
  ocupadas: number;
  usuarios: number;
  turnos_ultimas_24h: number;
  cobrado_ultimas_24h: number;
  guardia_abierta: boolean;
  categorias: number;
}

export interface EstablecimientoAlta {
  codigo: string;
  nombre: string;
  domicilio?: string;
  telefono?: string;
  habitaciones: number;
  tarifa_base: number;
  estadia_base_min: number;
  fraccion_min: number;
  tarifa_fraccion: number;
  fondo_cambio: number;
  gerente_usuario: string;
  gerente_nombre: string;
  gerente_clave: string;
}

export type CategoriaActividad =
  | 'INVENTARIO'
  | 'TARIFA'
  | 'CAJA'
  | 'HABITACION'
  | 'PERSONAL'
  | 'ESTABLECIMIENTO'
  | 'PERFIL';

export interface Actividad {
  id: number;
  creado_en: string;
  categoria: CategoriaActividad;
  accion: string;
  descripcion: string;
  operador_id: number;
  operador_nombre: string;
  guardia_id?: number | null;
  articulo_id?: number | null;
  cantidad?: number | null;
  valor_anterior?: string | null;
  valor_nuevo?: string | null;
  requiere_revision: boolean;
  revisado_en?: string | null;
  revisado_por_nombre?: string | null;
}

// --- Inteligencia local de la gerencia (services/inteligencia.py) -----------------------------------------------

export type Severidad = 'alta' | 'media' | 'info';

export interface AlertaIA {
  tipo: string;
  severidad: Severidad;
  titulo: string;
  detalle: string;
  sugerencia: string | null;
  evidencia: { etiqueta: string; valor: string }[];
}

export interface HoraPronostico {
  hora: string;
  etiqueta: string;
  llegadas: number;
  minimo: number;
  maximo: number;
  ocupacion: number;
  ocupacion_pct: number;
}

export interface Saturacion {
  categoria_id: number;
  categoria: string;
  color: string;
  desde: string;
  hasta: string;
  habitaciones: number;
}

export interface Pronostico {
  horas: HoraPronostico[];
  total: number;
  minimo: number;
  maximo: number;
  saturacion: Saturacion[];
  precision: { error_medio: number; dias: number } | null;
  tendencia: number;
  pico: HoraPronostico | null;
}

export interface MapaDemanda {
  dias: string[];
  valores: number[][];
  maximo: number;
  semanas: number;
  pico: { dia: string; hora: number; llegadas: number };
  dia_mas_fuerte: string;
  dia_mas_flojo: string;
  por_dia: number[];
}

export interface DiaSerie {
  fecha: string;
  dia: string;
  turnos: number;
  ingresos: number;
}

export interface ParametrosTarifa {
  tarifa_base: number;
  estadia_base_min: number;
  fraccion_min: number;
  tarifa_fraccion: number;
  tolerancia_min: number;
  tope: number | null;
}

export interface SugerenciaTarifa {
  categoria_id: number;
  categoria: string;
  color: string;
  habitaciones: number;
  turnos: number;
  ocupacion_pico: number | null;
  ocupacion_valle: number | null;
  ocupacion_total: number | null;
  con_sobreturno: number;
  accion: 'subir' | 'bajar' | 'estadia' | 'mantener';
  titulo: string;
  explicacion: string;
  impacto_mensual: number | null;
  supuesto: string | null;
  actual: ParametrosTarifa;
  propuesta: ParametrosTarifa | null;
  // La propuesta puede ser sobre una tarifa especial que ya existe o una nueva para crear.
  franja_id: number | null;
  franja_nombre: string | null;
  franja_nueva: { nombre: string; dias: number; desde: string; hasta: string; regla: string } | null;
  rendimiento: { franja: string; turnos: number; ingresos: number }[];
}

export interface Reposicion {
  articulo_id: number;
  codigo: string;
  descripcion: string;
  stock: number;
  vendidas_28d: number;
  por_dia: number;
  dias_restantes: number | null;
  agota_el: string | null;
  sugerido: number;
  urgencia: 'alta' | 'media' | 'baja' | 'sin_movimiento';
}

export interface Indicadores {
  ocupadas_ahora: number;
  habitaciones: number;
  turnos_7d: number;
  turnos_7d_variacion: number | null;
  ingresos_7d: number;
  ingresos_7d_variacion: number | null;
  ticket_7d: number;
  ocupacion_7d: number | null;
  tdc_30d: number | null;
  arqueos_30d: number;
}

export interface Tablero {
  generado_en: string;
  corte: string;
  guardia_abierta: boolean;
  indicadores: Indicadores;
  resumen: { titular: string; puntos: { icono: string; texto: string }[] };
  alertas: AlertaIA[];
  pronostico: Pronostico;
  demanda: MapaDemanda;
  serie: DiaSerie[];
  sugerencias: SugerenciaTarifa[];
  reposicion: Reposicion[];
  medios_de_pago: { medio: string; etiqueta: string; monto: number; parte: number }[];
  mas_vendidos: { articulo_id: number; descripcion: string; unidades: number; importe: number }[];
  clientes_perdidos: ClientesPerdidos;
  rotacion: Rotacion;
  opiniones: Opiniones;
}

// Lo que dicen los clientes (migración 015): solo totales, nunca una opinión suelta.
export interface Opiniones {
  dias: number;
  cantidad: number;
  promedio: number | null;
  parte: number;
  puntajes: { puntaje: number; cantidad: number }[];
  problemas: { problema: string; cantidad: number }[];
  habitaciones: { habitacion_id: number; numero: number; promedio: number; cantidad: number; problema: string | null; problema_veces: number }[];
}

// Gemelo del motel: repetir las llegadas reales con otras condiciones. No cambia nada.
export interface EscenarioGemelo {
  limpieza_min?: number | null;
  habitaciones?: Record<number, number>;
  precio_pct?: number;
  precio_cuando?: 'siempre' | 'pico' | 'floja';
}

export interface FotoGemelo {
  turnos: number;
  perdidos: number;
  ingresos: number;
  ocupacion: number;
}

export interface ResultadoGemelo {
  disponible: boolean;
  dias: number;
  limpieza_actual: number;
  categorias: { categoria_id: number; nombre: string; color: string; actuales: number; cambio: number }[];
  base?: FotoGemelo;
  escenario?: FotoGemelo;
  diferencia?: { turnos: number; perdidos: number; ingresos: number; ingresos_por_mes: number };
  por_hora?: { hora: number; etiqueta: string; base: number; escenario: number }[];
  calibracion?: { turnos_reales: number; turnos_modelo: number; coincidencia: number | null; ticket: number };
  conclusion: string;
  supuestos?: string[];
}

// Comprobantes verificables (migración 012).
export interface IntegridadComprobantes {
  total: number;
  integros: number;
  alterados: {
    secuencia: number;
    arqueo_id: number;
    codigo: string;
    motivo: string;
    operador_nombre: string;
    confirmado_en: string | null;
  }[];
  sin_sello: number;
  ultimo_codigo: string | null;
  verificado_en: string;
}

export interface VerificacionComprobante {
  encontrado: boolean;
  coincide: boolean;
  detalle: string;
  arqueo_id?: number;
  secuencia?: number;
  codigo?: string;
  operador_nombre?: string;
  franja?: string | null;
  confirmado_en?: string;
  total_declarado?: number;
  diferencia?: number;
  categoria?: string;
}

// Clientes que se fueron sin quedarse (migración 011).
export type MotivoPerdida = 'SIN_LUGAR' | 'ESPERA' | 'PRECIO';

export interface ClientesPerdidos {
  dias: number;
  total: number;
  parte: number;
  valor_estimado: number;
  motivos: { motivo: MotivoPerdida; etiqueta: string; cantidad: number; parte: number }[];
  categorias: { categoria_id: number; categoria: string; color: string; cantidad: number }[];
  horas: { hora: number; etiqueta: string; cantidad: number }[];
  franja: { dia: string; desde: number; hasta: number; cantidad: number; parte: number } | null;
  esperados_24h: number;
}

export interface Rotacion {
  dias: number;
  cantidad: number;
  mediana: number | null;
  p90: number | null;
  por_franja: { franja: string; mediana: number; cantidad: number }[];
  mas_lentas: { numero: number; mediana: number; cantidad: number }[];
  sin_turno: number;
}

// Cuándo quedaría disponible cada habitación, con la duración real de las estadías y de la limpieza.
export interface HabitacionProxima {
  habitacion_id: number;
  numero: number;
  estado: RoomStatus;
  categoria_id: number;
  categoria: string;
  color: string;
  minutos: number;
  minimo: number;
  maximo: number;
}

export interface ProximaLibre {
  disponibles: number;
  habitaciones: number;
  limpieza_min: number;
  proximas: HabitacionProxima[];
  categorias: {
    categoria_id: number;
    categoria: string;
    color: string;
    disponibles: number;
    habitaciones: number;
    proxima_min: number | null;
  }[];
}

// Las 24 horas de cada habitación. No lleva patentes ni importes.
export interface TramoHabitacion {
  tipo: 'ocupada' | 'limpieza' | 'mantenimiento';
  desde: string;
  hasta: string;
  en_curso: boolean;
  minutos: number;
}

export interface LineaDeTiempoDatos {
  desde: string;
  hasta: string;
  ahora: string;
  habitaciones: {
    habitacion_id: number;
    numero: number;
    estado: RoomStatus;
    categoria: string;
    color: string;
    tramos: TramoHabitacion[];
  }[];
  resumen: { turnos: number; ocupacion: number | null; limpieza_min: number | null; turnos_por_habitacion: number };
}

// Botón que propone el asistente: ir a una pantalla o abrir una habitación.
export interface AccionAsistente {
  etiqueta: string;
  vista: string | null;
  habitacion_id: number | null;
}

export interface RespuestaAsistente {
  respuesta: string;
  intencion: string;
  periodo: string | null;
  detalle: string | null;
  tabla: { columnas: string[]; filas: (string | number)[][] } | null;
  sugerencias: string[];
  // Ayuda para usar el sistema (services/ayuda.py): pasos a seguir y botones para ir.
  pasos?: string[];
  acciones?: AccionAsistente[];
  // Una orden lista para confirmar: el asistente nunca la ejecuta por su cuenta.
  confirmacion?: ConfirmacionAsistente | null;
}

export interface ConfirmacionAsistente {
  tipo: 'estado' | 'abrir_turno' | 'consumo' | 'novedad' | 'cliente_perdido';
  titulo: string;
  hecho: string;
  habitacion_id?: number | null;
  estado?: string;
  tipo_cliente?: TipoCliente;
  patente?: string | null;
  turno_id?: string;
  articulo_id?: number;
  cantidad?: number;
  texto?: string;
  importante?: boolean;
  motivo?: MotivoPerdida;
  categoria_id?: number | null;
  tarifa_id?: number | null;
}

// Un pedido o aviso, como lo ve el cliente. Las líneas de un carrito comparten `lote` (migración 015).
export interface PedidoEstadia {
  id: number;
  tipo: string;
  descripcion: string;
  cantidad: number | null;
  estado: string;
  lote: string | null;
}

// El cliente en su habitación (migraciones 013 y 015): lo que ve con el QR de su ticket.
export interface EstadiaCliente {
  activa: boolean;
  motel: string;
  color_marca: string | null;
  numero?: number;
  categoria?: string | null;
  franja?: string | null;
  bienvenida?: string | null;
  hora_inicio?: string;
  ahora?: string;
  estadia_base_min?: number;
  tarifa_base?: number;
  total_sobreturno?: number;
  total_consumos?: number;
  total?: number;
  proximo_cargo?: { minutos: number; monto: number } | null;
  opciones_tiempo?: { minutos: number; etiqueta: string; suma: number; hasta: string }[];
  medios_pago?: { medio: string; etiqueta: string }[];
  mot?: { id: string; pregunta: string; respuesta: string }[];
  calificada?: boolean;
  puede_calificar?: boolean;
  problemas?: { valor: number; etiqueta: string }[];
  consumos?: { descripcion: string; cantidad: number; subtotal: number }[];
  articulos?: { id: number; descripcion: string; precio: number; categoria: string | null }[];
  avisos?: { tipo: string; descripcion: string }[];
  pedidos?: PedidoEstadia[];
}

// Un pedido del cliente que espera en la ventanilla.
export interface PedidoVentanilla {
  id: number;
  turno_id: string;
  habitacion_id: number;
  numero: number;
  tipo: string;
  descripcion: string;
  cantidad: number | null;
  estado: string;
  lote: string | null;
  medio_pago: MedioPago | null;
  subtotal: number | null;
  creado_en: string;
}

export interface TicketCliente {
  direccion: string;
  qr: string;
  numero: number;
  hora_inicio: string;
}

// Pedidos de reposición a proveedores (migración 010).
export interface PedidoItem {
  articulo_id: number;
  codigo: string;
  descripcion: string;
  cantidad: number;
  recibida: number | null;
  stock_actual: number;
}

export interface Pedido {
  id: number;
  creado_en: string;
  creado_por_nombre: string;
  proveedor: string | null;
  nota: string | null;
  estado: 'Pendiente' | 'Recibido' | 'Anulado';
  cerrado_en: string | null;
  cerrado_por_nombre: string | null;
  items: PedidoItem[];
}

export interface SugeridoPedido {
  articulo_id: number;
  codigo: string;
  descripcion: string;
  stock: number;
  por_dia: number;
  dias_restantes: number | null;
  sugerido: number;
}

// Arqueos de un mes (por el día en que se abrió cada guardia).
export interface ResumenMes {
  mes: string;
  desde: string;
  hasta: string;
  arqueos: number;
  correctos: number;
  faltantes: number;
  sobrantes: number;
  total_faltante: number;
  total_sobrante: number;
  tdc: number;
}
