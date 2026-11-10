import React from 'react';
import { Bath, BedDouble, CheckCircle2, Minus, Plus } from 'lucide-react';
import { ConteoPrenda, Prenda, RopaDejada } from '../types';
import { inputClass } from './ui/Field';

export type FilaRopa = { limpias: string; sucias: string; en_habitaciones: string; total: string };
export type ValoresRopa = Record<Prenda, FilaRopa>;
type Parte = 'limpias' | 'sucias' | 'en_habitaciones';

export const PRENDAS: { prenda: Prenda; label: string; icon: React.ElementType }[] = [
  { prenda: 'TOALLAS', label: 'Toallas', icon: Bath },
  { prenda: 'SABANAS', label: 'Sábanas', icon: BedDouble },
];

// «En uso» son las que están puestas en las habitaciones.
export const PARTES: { campo: Parte; label: string }[] = [
  { campo: 'limpias', label: 'Limpias' },
  { campo: 'sucias', label: 'Sucias' },
  { campo: 'en_habitaciones', label: 'En uso' },
];

const filaVacia = (): FilaRopa => ({ limpias: '', sucias: '', en_habitaciones: '', total: '' });

export const ropaVacia = (): ValoresRopa => ({ TOALLAS: filaVacia(), SABANAS: filaVacia() });

const debia = (p: RopaDejada): number => p.esperado ?? p.total;

// Quien entra arranca con lo que le dejaron: lo confirma o lo corrige. Si la guardia anterior contó todo junto y ahora
// se cuenta por estado, no hay partes que proponer: se cuenta desde cero.
export const ropaDesde = (dejada: RopaDejada[] | null, porEstado: boolean): ValoresRopa => {
  const valores = ropaVacia();
  for (const p of dejada ?? []) {
    if (!porEstado) valores[p.prenda].total = String(debia(p));
    else if (p.limpias !== null && p.sucias !== null && p.en_habitaciones !== null) {
      valores[p.prenda] = { ...filaVacia(), limpias: String(p.limpias), sucias: String(p.sucias), en_habitaciones: String(p.en_habitaciones) };
    }
  }
  return valores;
};

const entero = (texto: string): number | null => (/^\d{1,6}$/.test(texto.trim()) ? parseInt(texto.trim(), 10) : null);

export const totalDe = (fila: FilaRopa, porEstado: boolean): number | null => {
  if (!porEstado) return entero(fila.total);
  const partes = [entero(fila.limpias), entero(fila.sucias), entero(fila.en_habitaciones)];
  return partes.some((p) => p === null) ? null : partes.reduce<number>((suma, p) => suma + (p ?? 0), 0);
};

// Nulo mientras falte un número: «no conté» y «hay cero» no son lo mismo.
export const aConteos = (valores: ValoresRopa, porEstado: boolean): ConteoPrenda[] | null => {
  const conteos: ConteoPrenda[] = [];
  for (const { prenda } of PRENDAS) {
    const fila = valores[prenda];
    if (!porEstado) {
      const total = entero(fila.total);
      if (total === null) return null;
      conteos.push({ prenda, total });
      continue;
    }
    const [limpias, sucias, enHabitaciones] = [entero(fila.limpias), entero(fila.sucias), entero(fila.en_habitaciones)];
    if (limpias === null || sucias === null || enHabitaciones === null) return null;
    conteos.push({ prenda, limpias, sucias, en_habitaciones: enHabitaciones });
  }
  return conteos;
};

export const textoDiferencia = (diferencia: number): string => {
  const una = Math.abs(diferencia) === 1;
  return `${diferencia < 0 ? (una ? 'falta' : 'faltan') : una ? 'sobra' : 'sobran'} ${Math.abs(diferencia)}`;
};

interface RecuentoRopaProps {
  valores: ValoresRopa;
  onCambiar: (valores: ValoresRopa) => void;
  // Cómo cuenta este motel: separado en limpias, sucias y en uso, o todo junto. Lo elige la gerencia.
  porEstado: boolean;
  // Lo que dejó la guardia anterior. En el cierre no viene: se cuenta a ciegas.
  dejada?: RopaDejada[] | null;
  idBase: string;
  disabled?: boolean;
}

const BotonPaso: React.FC<{ etiqueta: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }> = ({
  etiqueta,
  onClick,
  disabled,
  children,
}) => (
  <button
    type="button"
    aria-label={etiqueta}
    onClick={onClick}
    disabled={disabled}
    className="press hit flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-line-strong bg-surface text-muted hover:text-ink disabled:opacity-40 disabled:active:scale-100"
  >
    {children}
  </button>
);

// Se cuenta toda la ropa del motel. Lo que importa para un faltante es el total de cada prenda.
const RecuentoRopa: React.FC<RecuentoRopaProps> = ({ valores, onCambiar, porEstado, dejada, idBase, disabled }) => {
  const cambiar = (prenda: Prenda, campo: keyof FilaRopa, texto: string) =>
    onCambiar({ ...valores, [prenda]: { ...valores[prenda], [campo]: texto.replace(/\D/g, '').slice(0, 6) } });

  const sumar = (prenda: Prenda, paso: number) =>
    cambiar(prenda, 'total', String(Math.max((entero(valores[prenda].total) ?? 0) + paso, 0)));

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {PRENDAS.map(({ prenda, label, icon: Icon }) => {
        const total = totalDe(valores[prenda], porEstado);
        const recibida = dejada?.find((p) => p.prenda === prenda);
        const diferencia = recibida && total !== null ? total - debia(recibida) : null;
        return (
          <div
            key={prenda}
            role="group"
            aria-label={label}
            className={`rounded-lg border p-3 transition-colors ${diferencia ? 'border-warn/50 bg-warn-soft/40' : 'border-line bg-surface-2/60'}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
                {label}
              </span>
              {porEstado && (
                <span className="text-sm text-muted">
                  Total <span className="ml-1 text-lg font-semibold tabular-nums text-ink">{total ?? '—'}</span>
                </span>
              )}
            </div>

            {porEstado ? (
              <div className="mt-2.5 grid grid-cols-3 gap-2">
                {PARTES.map(({ campo, label: parte }) => (
                  <label key={campo} className="block text-xs text-muted">
                    {parte}
                    <input
                      id={`${idBase}-${prenda}-${campo}`}
                      aria-label={`${label}: ${parte.toLowerCase()}`}
                      inputMode="numeric"
                      autoComplete="off"
                      placeholder="0"
                      disabled={disabled}
                      className={`${inputClass} mt-1 h-11 px-2 text-center text-base tabular-nums`}
                      value={valores[prenda][campo]}
                      onChange={(e) => cambiar(prenda, campo, e.target.value)}
                    />
                  </label>
                ))}
              </div>
            ) : (
              <div className="mt-2.5">
                <label htmlFor={`${idBase}-${prenda}-total`} className="text-xs text-muted">
                  Cantidad total
                </label>
                <div className="mt-1 flex items-center gap-2">
                  <BotonPaso etiqueta={`Una menos de ${label.toLowerCase()}`} disabled={disabled || !entero(valores[prenda].total)} onClick={() => sumar(prenda, -1)}>
                    <Minus className="h-4 w-4" aria-hidden="true" />
                  </BotonPaso>
                  <input
                    id={`${idBase}-${prenda}-total`}
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="0"
                    disabled={disabled}
                    className={`${inputClass} h-11 min-w-0 flex-1 px-2 text-center text-lg font-semibold tabular-nums`}
                    value={valores[prenda].total}
                    onChange={(e) => cambiar(prenda, 'total', e.target.value)}
                  />
                  <BotonPaso etiqueta={`Una más de ${label.toLowerCase()}`} disabled={disabled} onClick={() => sumar(prenda, 1)}>
                    <Plus className="h-4 w-4" aria-hidden="true" />
                  </BotonPaso>
                </div>
              </div>
            )}

            {recibida && (
              <p role="status" className={`mt-2.5 flex items-start gap-1.5 text-xs ${diferencia ? 'font-medium text-warn' : 'text-muted'}`}>
                {diferencia === 0 && <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0 text-libre" aria-hidden="true" />}
                <span>
                  {diferencia === null && `Le dejaron ${debia(recibida)}.`}
                  {diferencia === 0 && `Coincide con lo que le dejaron (${debia(recibida)}).`}
                  {!!diferencia &&
                    `Le dejaron ${debia(recibida)} y usted cuenta ${total}: ${textoDiferencia(diferencia)}. La gerencia lo va a ver con su nombre y el de ${recibida.contado_por}.`}
                </span>
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default RecuentoRopa;
