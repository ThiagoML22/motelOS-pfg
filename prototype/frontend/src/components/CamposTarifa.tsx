import React from 'react';
import { TarifaDatos } from '../types';
import { formatMoney } from '../utils/format';
import { formatMinutos, simularEstadia } from '../utils/turno';
import Field, { inputClass } from './ui/Field';

const campo = `${inputClass} h-11`;
const numero = (valor: string): number => Number(valor.replace(',', '.'));

export type Ejecutar = (accion: () => Promise<unknown>, exito: string, error: string) => Promise<boolean>;

// Una línea legible de la tarifa: "2 h por $ 8.000 · cada 30 min, $ 2.500".
export const resumenTarifa = (t: TarifaDatos): string =>
  `${formatMinutos(t.estadia_base_min)} por ${formatMoney(t.tarifa_base)} · cada ${formatMinutos(t.fraccion_min)}, ${formatMoney(t.tarifa_fraccion)}`;

// --- Formulario de tarifa con simulador ----------------------------------------------------------------------------

export interface TarifaForm {
  tarifa_base: string;
  estadia_base_min: string;
  fraccion_min: string;
  tarifa_fraccion: string;
  tolerancia_min: string;
  tope: string;
}

export const tarifaFormDe = (t?: TarifaDatos | null): TarifaForm => ({
  tarifa_base: String(t?.tarifa_base ?? ''),
  estadia_base_min: String(t?.estadia_base_min ?? 120),
  fraccion_min: String(t?.fraccion_min ?? 30),
  tarifa_fraccion: String(t?.tarifa_fraccion ?? ''),
  tolerancia_min: String(t?.tolerancia_min ?? 0),
  tope: t?.tope ? String(t.tope) : '',
});

export const tarifaDatosDe = (f: TarifaForm): TarifaDatos => ({
  tarifa_base: numero(f.tarifa_base),
  estadia_base_min: numero(f.estadia_base_min),
  fraccion_min: numero(f.fraccion_min),
  tarifa_fraccion: numero(f.tarifa_fraccion),
  tolerancia_min: numero(f.tolerancia_min || '0'),
  tope: f.tope.trim() ? numero(f.tope) : null,
});

export const tarifaValida = (t: TarifaDatos): boolean =>
  t.tarifa_base > 0 &&
  t.estadia_base_min > 0 &&
  t.fraccion_min > 0 &&
  t.tarifa_fraccion >= 0 &&
  t.tolerancia_min >= 0 &&
  (t.tope == null || t.tope >= t.tarifa_base);

const Atajos: React.FC<{ valores: number[]; actual: string; onElegir: (v: string) => void; etiqueta: (v: number) => string }> = ({
  valores,
  actual,
  onElegir,
  etiqueta,
}) => (
  <div className="mt-1.5 flex flex-wrap gap-1">
    {valores.map((v) => (
      <button
        key={v}
        type="button"
        onClick={() => onElegir(String(v))}
        className={`press rounded-full border px-2 py-0.5 text-xs ${
          actual === String(v) ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-ink'
        }`}
      >
        {etiqueta(v)}
      </button>
    ))}
  </div>
);

export const CamposTarifa: React.FC<{ form: TarifaForm; onChange: (f: TarifaForm) => void; prefijo: string }> = ({
  form,
  onChange,
  prefijo,
}) => {
  const set = (k: keyof TarifaForm) => (e: React.ChangeEvent<HTMLInputElement>) => onChange({ ...form, [k]: e.target.value });
  const datos = tarifaDatosDe(form);
  const valida = tarifaValida(datos);
  const base = datos.estadia_base_min || 120;
  // Duraciones de ejemplo alrededor de la estadía base, hasta medio día.
  const muestras = Array.from(
    new Set([60, base, base + (datos.fraccion_min || 30), base + 60, base + 120, 360, 720].filter((m) => m > 0)),
  ).sort((a, b) => a - b);
  const montos = muestras.map((m) => (valida ? simularEstadia(datos, m) : 0));
  const maximo = Math.max(...montos, 1);

  return (
    <div className="grid gap-5 md:grid-cols-[1fr_17rem]">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Field label="Duración del turno (min)" htmlFor={`${prefijo}_base_min`}>
              <input id={`${prefijo}_base_min`} inputMode="numeric" required className={campo} value={form.estadia_base_min} onChange={set('estadia_base_min')} />
            </Field>
            <Atajos valores={[60, 90, 120, 180, 240]} actual={form.estadia_base_min} etiqueta={formatMinutos} onElegir={(v) => onChange({ ...form, estadia_base_min: v })} />
          </div>
          <Field label="Precio del turno ($)" htmlFor={`${prefijo}_base`}>
            <input id={`${prefijo}_base`} inputMode="decimal" required className={campo} value={form.tarifa_base} onChange={set('tarifa_base')} />
          </Field>
          <div>
            <Field label="Se cobra extra cada (min)" htmlFor={`${prefijo}_fraccion_min`}>
              <input id={`${prefijo}_fraccion_min`} inputMode="numeric" required className={campo} value={form.fraccion_min} onChange={set('fraccion_min')} />
            </Field>
            <Atajos valores={[15, 30, 60]} actual={form.fraccion_min} etiqueta={formatMinutos} onElegir={(v) => onChange({ ...form, fraccion_min: v })} />
          </div>
          <Field label="Monto de cada extra ($)" htmlFor={`${prefijo}_fraccion`}>
            <input id={`${prefijo}_fraccion`} inputMode="decimal" required className={campo} value={form.tarifa_fraccion} onChange={set('tarifa_fraccion')} />
          </Field>
          <Field label="Tolerancia (min)" htmlFor={`${prefijo}_tolerancia`} hint="Gracia antes del primer extra. El catálogo fija 0.">
            <input id={`${prefijo}_tolerancia`} inputMode="numeric" className={campo} value={form.tolerancia_min} onChange={set('tolerancia_min')} />
          </Field>
          <Field label="Tope de la estadía ($)" htmlFor={`${prefijo}_tope`} hint="Opcional: precio máximo (por ejemplo, pernocte).">
            <input id={`${prefijo}_tope`} inputMode="decimal" placeholder="Sin tope" className={campo} value={form.tope} onChange={set('tope')} />
          </Field>
        </div>
        {!valida && (form.tarifa_base || form.tarifa_fraccion) && (
          <p className="text-xs text-danger">Revise los valores: precios mayores que cero y el tope no menor que el precio del turno.</p>
        )}
      </div>

      <div className="rounded-md border border-line bg-surface-2 p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">Simulador: el cliente paga</p>
        <ul className="space-y-1.5" aria-live="polite">
          {muestras.map((m, i) => (
            <li key={m} className="text-xs">
              <div className="flex justify-between gap-2">
                <span className="text-muted">{formatMinutos(m)}</span>
                <span className="font-medium tabular-nums text-ink">{valida ? formatMoney(montos[i]) : '—'}</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full bg-line">
                <div
                  className={`h-1.5 rounded-full transition-all duration-300 ${m <= base ? 'bg-libre' : 'bg-accent'}`}
                  style={{ width: `${(montos[i] / maximo) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] leading-snug text-subtle">Misma cuenta que hace el servidor al cobrar (sin consumos).</p>
      </div>
    </div>
  );
};
