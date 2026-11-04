import React from 'react';
import { ConteoPrenda, Prenda, RopaDejada } from '../types';
import { inputClass } from './ui/Field';

export type FilaRopa = { limpias: string; sucias: string; en_habitaciones: string };
export type ValoresRopa = Record<Prenda, FilaRopa>;

const PRENDAS: { prenda: Prenda; label: string }[] = [
  { prenda: 'TOALLAS', label: 'Toallas' },
  { prenda: 'SABANAS', label: 'Sábanas' },
];

const COLUMNAS: { campo: keyof FilaRopa; label: string }[] = [
  { campo: 'limpias', label: 'Limpias' },
  { campo: 'sucias', label: 'Sucias' },
  { campo: 'en_habitaciones', label: 'En habitaciones' },
];

const filaVacia = (): FilaRopa => ({ limpias: '', sucias: '', en_habitaciones: '' });

export const ropaVacia = (): ValoresRopa => ({ TOALLAS: filaVacia(), SABANAS: filaVacia() });

// Quien entra arranca con lo que le dejaron: lo confirma o lo corrige.
export const ropaDesde = (dejada: RopaDejada[] | null): ValoresRopa => {
  const valores = ropaVacia();
  for (const p of dejada ?? []) {
    valores[p.prenda] = {
      limpias: String(p.limpias),
      sucias: String(p.sucias),
      en_habitaciones: String(p.en_habitaciones),
    };
  }
  return valores;
};

const entero = (texto: string): number | null => (/^\d{1,6}$/.test(texto.trim()) ? parseInt(texto.trim(), 10) : null);

const totalDe = (fila: FilaRopa): number | null => {
  const partes = [entero(fila.limpias), entero(fila.sucias), entero(fila.en_habitaciones)];
  return partes.some((p) => p === null) ? null : partes.reduce<number>((suma, p) => suma + (p ?? 0), 0);
};

// Nulo mientras falte un número: «no conté» y «hay cero» no son lo mismo.
export const aConteos = (valores: ValoresRopa): ConteoPrenda[] | null => {
  const conteos: ConteoPrenda[] = [];
  for (const { prenda } of PRENDAS) {
    const fila = valores[prenda];
    const [limpias, sucias, enHabitaciones] = [entero(fila.limpias), entero(fila.sucias), entero(fila.en_habitaciones)];
    if (limpias === null || sucias === null || enHabitaciones === null) return null;
    conteos.push({ prenda, limpias, sucias, en_habitaciones: enHabitaciones });
  }
  return conteos;
};

export const textoDiferencia = (diferencia: number): string =>
  `${diferencia < 0 ? 'faltan' : 'sobran'} ${Math.abs(diferencia)}`;

interface RecuentoRopaProps {
  valores: ValoresRopa;
  onCambiar: (valores: ValoresRopa) => void;
  // Lo que dejó la guardia anterior. En el cierre no viene: se cuenta a ciegas.
  dejada?: RopaDejada[] | null;
  idBase: string;
  disabled?: boolean;
}

// Se cuenta toda la ropa del motel. Las tres columnas se suman: lo que importa para un faltante es el total.
const RecuentoRopa: React.FC<RecuentoRopaProps> = ({ valores, onCambiar, dejada, idBase, disabled }) => {
  const cambiar = (prenda: Prenda, campo: keyof FilaRopa, texto: string) =>
    onCambiar({ ...valores, [prenda]: { ...valores[prenda], [campo]: texto } });

  return (
    <div>
      <div className="grid grid-cols-[minmax(3.5rem,1fr)_repeat(3,minmax(0,4.75rem))_2.5rem] items-end gap-x-2 gap-y-2 text-sm">
        <span />
        {COLUMNAS.map(({ campo, label }) => (
          <span key={campo} className="text-xs leading-tight text-muted">
            {label}
          </span>
        ))}
        <span className="text-right text-xs text-muted">Total</span>

        {PRENDAS.map(({ prenda, label }) => {
          const total = totalDe(valores[prenda]);
          return (
            <React.Fragment key={prenda}>
              <span className="self-center font-medium text-ink">{label}</span>
              {COLUMNAS.map(({ campo, label: columna }) => (
                <input
                  key={campo}
                  id={`${idBase}-${prenda}-${campo}`}
                  aria-label={`${label}: ${columna.toLowerCase()}`}
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="0"
                  disabled={disabled}
                  className={`${inputClass} h-10 px-2 text-center tabular-nums`}
                  value={valores[prenda][campo]}
                  onChange={(e) => cambiar(prenda, campo, e.target.value)}
                />
              ))}
              <span className="self-center text-right font-semibold tabular-nums text-ink">{total ?? '—'}</span>
            </React.Fragment>
          );
        })}
      </div>

      {dejada?.map((p) => {
        const total = totalDe(valores[p.prenda]);
        const debia = p.esperado ?? p.total;
        const diferencia = total === null ? 0 : total - debia;
        return (
          diferencia !== 0 && (
            <p key={p.prenda} role="status" className="mt-2 text-sm text-warn">
              {p.etiqueta}: debería haber {debia} y usted cuenta {total} ({textoDiferencia(diferencia)}). La gerencia va a
              ver la diferencia con su nombre y el de {p.contado_por}.
            </p>
          )
        );
      })}
    </div>
  );
};

export default RecuentoRopa;
