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
