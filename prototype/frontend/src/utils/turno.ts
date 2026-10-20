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
