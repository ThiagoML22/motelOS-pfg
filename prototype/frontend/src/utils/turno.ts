import { Turno } from '../types';
import { parseUtc } from './format';

// RN-DER-01: estadía base de 120 minutos. La liquidación (tarifa, sobreturno y total) es
// responsabilidad del backend; esta constante solo sirve para señalar visualmente el exceso.
export const ESTADIA_BASE_MIN = 120;

export type FaseEstadia = 'normal' | 'excedido';

export const faseEstadia = (transcurridoMs: number): FaseEstadia =>
  transcurridoMs > ESTADIA_BASE_MIN * 60000 ? 'excedido' : 'normal';

export const minutosExcedidos = (transcurridoMs: number): number =>
  Math.max(0, Math.ceil((transcurridoMs - ESTADIA_BASE_MIN * 60000) / 60000));

export const elapsedMs = (turno: Pick<Turno, 'hora_inicio'>, now: number): number =>
  Math.max(0, now - parseUtc(turno.hora_inicio).getTime());

// Guardias de conserjería: Mañana 06–14, Tarde 14–22, Noche 22–06.
export const guardiaActual = (hour: number): { label: string; range: string } => {
  if (hour >= 6 && hour < 14) return { label: 'Mañana', range: '06:00–14:00' };
  if (hour >= 14 && hour < 22) return { label: 'Tarde', range: '14:00–22:00' };
  return { label: 'Noche', range: '22:00–06:00' };
};
