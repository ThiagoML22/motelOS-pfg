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
}

// Categoría de habitación (Simple, Especial, VIP...) con su tarifa vigente.
export interface Categoria {
  id: number;
  nombre: string;
  descripcion?: string | null;
  color: string;
  orden: number;
  activa: boolean;
  habitaciones: number;
  tarifa?: Tarifa | null;
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
  activo: boolean;
  creado_en: string;
}

export interface EstablecimientoDatos {
  nombre?: string;
  domicilio?: string | null;
  telefono?: string | null;
  leyenda_comprobante?: string | null;
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
