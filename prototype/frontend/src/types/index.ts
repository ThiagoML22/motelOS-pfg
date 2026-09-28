export type RoomStatus = 'Libre' | 'Ocupada' | 'En Limpieza' | 'Mantenimiento';
export type TipoCliente = 'Auto' | 'Moto' | 'Peaton';

export interface Habitacion {
  id: number;
  numero: number;
  estado: RoomStatus;
}

export interface Turno {
  id?: string;
  habitacion_id: number;
  identificador_vehicular: string;
  tipo_cliente: TipoCliente;
  hora_inicio?: string;
  hora_fin?: string;
  estado?: string;
  consumo_total?: number;
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
  categoria: string;
}

export interface TurnoResumen extends Turno {
  minutos_transcurridos: number;
  tarifa_base: number;
  total_sobreturno: number;
  total_consumos: number;
  total_general: number;
  consumos: Consumo[];
}

export interface HabitacionConDetalles extends Habitacion {
  turno_activo?: TurnoResumen;
  tiempo_transcurrido?: string; 
  excede_tiempo?: boolean;
}
