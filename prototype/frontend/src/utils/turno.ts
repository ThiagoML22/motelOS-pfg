import { Turno } from '../types';
import { parseUtc } from './format';

// RN-DER-01: estadía base por defecto. Desde la migración 008 cada categoría de habitación tiene la suya y el turno la
// trae (estadia_base_min); esta constante queda para los turnos sin ese dato. La liquidación (tarifa, sobreturno y
// total) es responsabilidad del backend: acá solo se señala visualmente el exceso.
export const ESTADIA_BASE_MIN = 120;

// Minutos antes del fin de la estadía base en que la tarjeta avisa que el turno está por vencer.
export const AVISO_POR_VENCER_MIN = 10;

export type FaseEstadia = 'normal' | 'por_vencer' | 'excedido';

export const faseEstadia = (transcurridoMs: number, baseMin: number = ESTADIA_BASE_MIN): FaseEstadia => {
  if (transcurridoMs > baseMin * 60000) return 'excedido';
  return transcurridoMs > (baseMin - AVISO_POR_VENCER_MIN) * 60000 ? 'por_vencer' : 'normal';
};

export const minutosRestantes = (transcurridoMs: number, baseMin: number = ESTADIA_BASE_MIN): number =>
  Math.max(0, Math.ceil((baseMin * 60000 - transcurridoMs) / 60000));

export const minutosExcedidos = (transcurridoMs: number, baseMin: number = ESTADIA_BASE_MIN): number =>
  Math.max(0, Math.ceil((transcurridoMs - baseMin * 60000) / 60000));

export const elapsedMs = (turno: Pick<Turno, 'hora_inicio'>, now: number): number =>
  Math.max(0, now - parseUtc(turno.hora_inicio).getTime());

// "2 h", "2 h 30 min", "45 min".
export const formatMinutos = (minutos: number): string => {
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  if (h && m) return `${h} h ${m} min`;
  return h ? `${h} h` : `${m} min`;
};

export interface ParametrosTarifa {
  tarifa_base: number;
  estadia_base_min: number;
  fraccion_min: number;
  tarifa_fraccion: number;
  tolerancia_min?: number;
  tope?: number | null;
}

// Misma cuenta que billing_service.calcular_sobreturno del backend, para el simulador del panel de configuración.
export const simularEstadia = (t: ParametrosTarifa, minutos: number): number => {
  const tolerancia = t.tolerancia_min ?? 0;
  if (minutos <= t.estadia_base_min + tolerancia) return t.tarifa_base;
  const fracciones = Math.ceil((minutos - t.estadia_base_min) / t.fraccion_min);
  let sobreturno = fracciones * t.tarifa_fraccion;
  if (t.tope != null) sobreturno = Math.min(sobreturno, Math.max(t.tope - t.tarifa_base, 0));
  return t.tarifa_base + sobreturno;
};
