import { Turno } from '../types';
import { parseUtc } from './format';

// RN-DER-01: estadía base de 120 min y tolerancia de 10 min. La liquidación es responsabilidad
// del backend; estas constantes solo sirven para señalar visualmente la fase del cronómetro.
export const ESTADIA_BASE_MIN = 120;
export const TOLERANCIA_MIN = 10;

export type FaseEstadia = 'normal' | 'tolerancia' | 'excedido';

export const faseEstadia = (minutos: number): FaseEstadia => {
  if (minutos < ESTADIA_BASE_MIN) return 'normal';
  if (minutos <= ESTADIA_BASE_MIN + TOLERANCIA_MIN) return 'tolerancia';
  return 'excedido';
};

export const elapsedMs = (turno: Pick<Turno, 'hora_inicio'>, now: number): number =>
  Math.max(0, now - parseUtc(turno.hora_inicio).getTime());

export const elapsedMinutes = (turno: Pick<Turno, 'hora_inicio'>, now: number): number =>
  Math.floor(elapsedMs(turno, now) / 60000);

// Guardias de conserjería: Mañana 06–14, Tarde 14–22, Noche 22–06.
export const guardiaActual = (hour: number): { label: string; range: string } => {
  if (hour >= 6 && hour < 14) return { label: 'Mañana', range: '06:00–14:00' };
  if (hour >= 14 && hour < 22) return { label: 'Tarde', range: '14:00–22:00' };
  return { label: 'Noche', range: '22:00–06:00' };
};
