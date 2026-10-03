import { RoomStatus } from '../../types';
import { FaseEstadia } from '../../utils/turno';

interface EstadoMeta {
  label: string;
  hint: string;
  dot: string;
  text: string;
  bar: string;
}

export const ESTADOS_ORDEN: RoomStatus[] = ['Libre', 'Ocupada', 'En Limpieza', 'Mantenimiento'];

// Codificación cromática de RF-01: Libre = verde, Ocupada = rojo, Limpieza = amarillo.
export const ESTADO_META: Record<RoomStatus, EstadoMeta> = {
  Libre: { label: 'Disponible', hint: 'Lista para ocupar', dot: 'bg-libre', text: 'text-libre', bar: 'border-l-libre' },
  Ocupada: { label: 'Ocupada', hint: '', dot: 'bg-ocupada', text: 'text-ocupada', bar: 'border-l-ocupada' },
  'En Limpieza': {
    label: 'Limpieza',
    hint: 'Pendiente de liberación',
    dot: 'bg-limpieza',
    text: 'text-limpieza',
    bar: 'border-l-limpieza',
  },
  Mantenimiento: {
    label: 'Mantenimiento',
    hint: 'Fuera de servicio',
    dot: 'bg-mant',
    text: 'text-mant',
    bar: 'border-l-mant',
  },
};

export const FASE_META: Record<FaseEstadia, { text: string }> = {
  normal: { text: 'text-ink' },
  excedido: { text: 'text-danger' },
};
