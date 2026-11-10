import React, { useEffect, useMemo, useRef, useState } from 'react';
import { FlaskConical, Minus, Plus, RotateCcw, TrendingDown, TrendingUp } from 'lucide-react';
import { EscenarioGemelo, ResultadoGemelo } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatMoney } from '../utils/format';
import { Cifra } from './ui/Carga';
import { useToast } from './ui/Toast';

type Cuando = NonNullable<EscenarioGemelo['precio_cuando']>;

interface Controles {
  limpieza: number | null;
  habitaciones: Record<number, number>;
  precio: number;
  cuando: Cuando;
}

const INICIALES: Controles = { limpieza: null, habitaciones: {}, precio: 0, cuando: 'siempre' };
const ESPERA_MS = 250;

const CUANDO: { valor: Cuando; etiqueta: string }[] = [
  { valor: 'siempre', etiqueta: 'Siempre' },
  { valor: 'pico', etiqueta: 'Horas pico' },
  { valor: 'floja', etiqueta: 'Horas flojas' },
];

const Regla: React.FC<{
  etiqueta: string;
  valor: string;
  min: number;
  max: number;
  paso: number;
  actual: number;
  onCambiar: (valor: number) => void;
}> = ({ etiqueta, valor, min, max, paso, actual, onCambiar }) => (
  <label className="block">
    <span className="flex items-baseline justify-between gap-2 text-sm">
      <span className="text-ink">{etiqueta}</span>
      <span className="font-semibold tabular-nums text-ink">{valor}</span>
    </span>
    <input
      type="range"
      min={min}
      max={max}
      step={paso}
      value={actual}
      onChange={(e) => onCambiar(Number(e.target.value))}
      className="mt-1 h-2 w-full cursor-pointer accent-[rgb(var(--accent))]"
    />
  </label>
);

// Una cifra de hoy contra la del cambio. `bueno` dice si subir es bueno (los clientes perdidos, al revés).
const Comparacion: React.FC<{ etiqueta: string; hoy: number; nuevo: number; formato: (v: number) => string; bueno?: 'sube' | 'baja' }> = ({
  etiqueta,
  hoy,
  nuevo,
  formato,
  bueno = 'sube',
}) => {
  const diferencia = nuevo - hoy;
  const mejora = bueno === 'sube' ? diferencia > 0 : diferencia < 0;
  const Icono = diferencia > 0 ? TrendingUp : TrendingDown;
  return (
    <div className="bg-surface px-3 py-2.5">
      <p className="text-xs text-muted">{etiqueta}</p>
      <p className="mt-0.5 text-lg font-semibold text-ink">
        <Cifra valor={nuevo} formato={formato} duracion={350} />
      </p>
      <p className={`flex items-center gap-1 text-xs tabular-nums ${diferencia === 0 ? 'text-subtle' : mejora ? 'text-libre' : 'text-danger'}`}>
        {diferencia !== 0 && <Icono className="h-3 w-3" aria-hidden="true" />}
        {diferencia === 0 ? 'igual que hoy' : `${diferencia > 0 ? '+' : '−'}${formato(Math.abs(diferencia))}`}
      </p>
    </div>
  );
};

// El gemelo del motel: probar un cambio sobre lo que pasó de verdad antes de hacerlo. No cambia nada del sistema.
const GemeloMotel: React.FC = () => {
  const { toast } = useToast();
  const [controles, setControles] = useState<Controles>(INICIALES);
  const [datos, setDatos] = useState<ResultadoGemelo | null>(null);
  const [calculando, setCalculando] = useState(false);
  const pedido = useRef(0);

  useEffect(() => {
    const numero = ++pedido.current;
    setCalculando(true);
    const espera = setTimeout(async () => {
      try {
        const resultado = await api.probarEscenario({
          limpieza_min: controles.limpieza,
          habitaciones: controles.habitaciones,
          precio_pct: controles.precio,
          precio_cuando: controles.cuando,
        });
        // Si mientras tanto se movió algo, esta respuesta ya no sirve.
        if (numero === pedido.current) setDatos(resultado);
      } catch (err) {
        toast(getErrorMessage(err, 'No se pudo calcular el escenario.'), 'error');
      } finally {
        if (numero === pedido.current) setCalculando(false);
      }
    }, ESPERA_MS);
    return () => clearTimeout(espera);
  }, [controles, toast]);

  const limpiezaActual = datos?.limpieza_actual ?? 25;
  const limpieza = controles.limpieza ?? limpiezaActual;
  const hayCambios = controles.limpieza !== null || controles.precio !== 0 || Object.values(controles.habitaciones).some(Boolean);
  const horas = datos?.por_hora ?? [];
  const maximo = useMemo(() => Math.max(1, ...horas.flatMap((h) => [h.base, h.escenario])), [horas]);

  const cambiarHabitaciones = (categoria: number, cambio: number) =>
    setControles((c) => ({ ...c, habitaciones: { ...c.habitaciones, [categoria]: (c.habitaciones[categoria] ?? 0) + cambio } }));

  // Ejemplos para empezar: el cambio más barato de cada tipo.
  const categoriaMayor = datos?.categorias[datos.categorias.length - 1];
  const ejemplos: { etiqueta: string; aplicar: () => void }[] = [
    { etiqueta: 'Limpieza 5 min más rápida', aplicar: () => setControles({ ...INICIALES, limpieza: Math.max(limpiezaActual - 5, 5) }) },
    ...(categoriaMayor
      ? [
          {
            etiqueta: `Una ${categoriaMayor.nombre} más`,
            aplicar: () => setControles({ ...INICIALES, habitaciones: { [categoriaMayor.categoria_id]: 1 } }),
          },
        ]
      : []),
    { etiqueta: 'Horas pico +10%', aplicar: () => setControles({ ...INICIALES, precio: 10, cuando: 'pico' }) },
  ];

  const titulo = (
    <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
      <FlaskConical className="h-4 w-4 text-muted" aria-hidden="true" />
      Gemelo del motel
    </h2>
  );

  if (datos && !datos.disponible) {
    return (
      <section className="rounded-lg border border-line bg-surface p-4 sm:p-5">
        {titulo}
        <p className="mt-2 text-sm text-muted">{datos.conclusion}</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-line bg-surface p-4 sm:p-5" aria-label="Gemelo del motel">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        {titulo}
        <p className="text-xs text-muted">Repite los últimos {datos?.dias ?? 30} días con otras condiciones · no cambia nada del sistema</p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {ejemplos.map((e) => (
              <button
                key={e.etiqueta}
                type="button"
                onClick={e.aplicar}
                className="press rounded-full border border-line-strong bg-surface px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-accent"
              >
                {e.etiqueta}
              </button>
            ))}
          </div>

          <Regla
            etiqueta="Limpieza"
            valor={`${limpieza} min`}
            min={5}
            max={Math.max(45, limpiezaActual + 15)}
            paso={1}
            actual={limpieza}
            onCambiar={(v) => setControles((c) => ({ ...c, limpieza: v === limpiezaActual ? null : v }))}
          />

          <div>
            <p className="text-sm text-ink">Habitaciones</p>
            <ul className="mt-1 space-y-1">
              {datos?.categorias.map((c) => {
                const cambio = controles.habitaciones[c.categoria_id] ?? 0;
                return (
                  <li key={c.categoria_id} className="flex items-center gap-2 text-sm">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.color }} aria-hidden="true" />
                    <span className="min-w-0 flex-1 truncate text-muted">{c.nombre}</span>
                    <button
                      type="button"
                      onClick={() => cambiarHabitaciones(c.categoria_id, -1)}
                      disabled={c.actuales + cambio <= 0}
                      aria-label={`Una ${c.nombre} menos`}
                      className="press hit grid h-6 w-6 place-items-center rounded border border-line-strong text-muted hover:text-ink disabled:opacity-40"
                    >
                      <Minus className="h-3 w-3" aria-hidden="true" />
                    </button>
                    <span className={`w-6 text-center tabular-nums ${cambio ? 'font-semibold text-accent' : 'text-ink'}`}>{c.actuales + cambio}</span>
                    <button
                      type="button"
                      onClick={() => cambiarHabitaciones(c.categoria_id, 1)}
                      disabled={cambio >= 10}
                      aria-label={`Una ${c.nombre} más`}
                      className="press hit grid h-6 w-6 place-items-center rounded border border-line-strong text-muted hover:text-ink disabled:opacity-40"
                    >
                      <Plus className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div>
            <Regla
              etiqueta="Precio"
              valor={`${controles.precio > 0 ? '+' : ''}${controles.precio}%`}
              min={-30}
              max={30}
              paso={5}
              actual={controles.precio}
              onCambiar={(v) => setControles((c) => ({ ...c, precio: v }))}
            />
            <div role="group" aria-label="Cuándo se aplica el cambio de precio" className="mt-1.5 flex gap-1">
              {CUANDO.map(({ valor, etiqueta }) => (
                <button
                  key={valor}
                  type="button"
                  aria-pressed={controles.cuando === valor}
                  onClick={() => setControles((c) => ({ ...c, cuando: valor }))}
                  className={`press flex-1 rounded border px-1.5 py-1 text-xs ${
                    controles.cuando === valor ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong text-muted hover:text-ink'
                  }`}
                >
                  {etiqueta}
                </button>
              ))}
            </div>
          </div>

          {hayCambios && (
            <button type="button" onClick={() => setControles(INICIALES)} className="press inline-flex items-center gap-1.5 text-xs font-medium text-accent hover:underline">
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Volver a las condiciones de hoy
            </button>
          )}
        </div>

        <div className={`min-w-0 transition-opacity duration-200 ${calculando ? 'opacity-70' : ''}`} aria-live="polite">
          {datos?.base && datos.escenario && datos.diferencia ? (
            <>
              <p className="rounded-md bg-accent-soft px-3 py-2 text-sm font-medium text-ink">{datos.conclusion}</p>
              <div className="mt-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-4">
                <Comparacion etiqueta="Turnos" hoy={datos.base.turnos} nuevo={datos.escenario.turnos} formato={(v) => String(Math.round(v))} />
                <Comparacion etiqueta="Clientes perdidos" hoy={datos.base.perdidos} nuevo={datos.escenario.perdidos} formato={(v) => String(Math.round(v))} bueno="baja" />
                <Comparacion etiqueta="Ingresos" hoy={datos.base.ingresos} nuevo={datos.escenario.ingresos} formato={(v) => formatMoney(Math.round(v))} />
                <Comparacion etiqueta="Ocupación" hoy={datos.base.ocupacion} nuevo={datos.escenario.ocupacion} formato={(v) => `${Math.round(v * 100)}%`} />
              </div>

              <div className="mt-3">
                <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted">
                  <span>Clientes perdidos por hora</span>
                  <span className="flex items-center gap-3">
                    <span className="flex items-center gap-1">
                      <span className="h-2 w-2 rounded-sm bg-viz-1/30" aria-hidden="true" />
                      Hoy
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-2 w-2 rounded-sm bg-viz-1" aria-hidden="true" />
                      Con el cambio
                    </span>
                  </span>
                </div>
                <div className="flex h-20 items-end gap-[3px]" role="img" aria-label="Clientes perdidos por hora, hoy y con el cambio">
                  {horas.map((h) => (
                    <div key={h.hora} className="relative h-full flex-1" title={`${h.etiqueta}: ${h.base} hoy, ${h.escenario} con el cambio`}>
                      <span className="absolute inset-x-0 bottom-0 rounded-t-sm bg-viz-1/30 transition-[height] duration-300" style={{ height: `${(h.base / maximo) * 100}%` }} />
                      <span className="absolute inset-x-[18%] bottom-0 rounded-t-sm bg-viz-1 transition-[height] duration-300" style={{ height: `${(h.escenario / maximo) * 100}%` }} />
                    </div>
                  ))}
                </div>
                <div className="mt-1 flex gap-[3px] text-[10px] tabular-nums text-subtle">
                  {horas.map((h) => (
                    <span key={h.hora} className="flex-1 text-center">
                      {h.hora % 3 === 0 ? h.hora : ''}
                    </span>
                  ))}
                </div>
              </div>

              <details className="mt-2 text-xs text-muted">
                <summary className="cursor-pointer select-none">
                  Con las condiciones de hoy el modelo reproduce el{' '}
                  <span className="font-medium text-ink">{Math.round((datos.calibracion?.coincidencia ?? 0) * 100)}%</span> de los turnos reales. Qué supone
                </summary>
                <ul className="mt-1.5 list-disc space-y-0.5 pl-4">
                  {datos.supuestos?.map((s) => <li key={s}>{s}</li>)}
                </ul>
              </details>
            </>
          ) : (
            <p className="py-10 text-center text-sm text-muted">Calculando…</p>
          )}
        </div>
      </div>
    </section>
  );
};

export default GemeloMotel;
