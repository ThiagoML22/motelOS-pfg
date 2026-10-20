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
}

export interface TurnoResumen extends Turno {
  minutos_transcurridos: number;
  total_pagado: number;
  saldo_pendiente: number;
  consumos: Consumo[];
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
  turno_activo?: Turno | null;
}

// --- Sesión y caja (prototipo v2) ---

export type Rol = 'OPERADOR' | 'ADMINISTRADOR';

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

export interface Sesion {
  operador: Operador;
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

export interface MetricasCaja {
  desde?: string | null;
  hasta?: string | null;
  general: MetricaCaja;
  por_operador: MetricaCaja[];
}
