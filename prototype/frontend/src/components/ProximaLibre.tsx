import React, { useEffect, useRef, useState } from 'react';
import { Check, Hourglass, PenLine, UserRoundX } from 'lucide-react';
import { Categoria, MotivoPerdida, ProximaLibre } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatRoomNumber } from '../utils/format';
import { inputClass } from './ui/Field';
import { useToast } from './ui/Toast';

const MOTIVOS: { motivo: MotivoPerdida; etiqueta: string }[] = [
  { motivo: 'SIN_LUGAR', etiqueta: 'No había lugar' },
  { motivo: 'ESPERA', etiqueta: 'No quiso esperar' },
  { motivo: 'PRECIO', etiqueta: 'Le pareció caro' },
];
const LARGO_DETALLE = 80;

// «Se fue un cliente»: dos toques (por qué se fue y, si se sabe, qué buscaba) y no guarda ningún dato de la persona. Con
// «Otro» se escriben unas palabras; el servidor las pasa por el filtro de groserías.
export const BotonClientePerdido: React.FC<{ categorias: Categoria[]; destacado?: boolean }> = ({ categorias, destacado = false }) => {
  const { toast } = useToast();
  const [abierto, setAbierto] = useState(false);
  const [categoria, setCategoria] = useState<number | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [otro, setOtro] = useState<string | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false);
    };
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setAbierto(false);
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', escape);
    };
  }, [abierto]);

  useEffect(() => {
    if (!abierto) setOtro(null);
  }, [abierto]);

  const registrar = async (motivo: MotivoPerdida, detalle?: string) => {
    setEnviando(true);
    try {
      const { en_la_guardia: cantidad } = await api.registrarClientePerdido(motivo, categoria, detalle);
      toast(`Registrado. ${cantidad === 1 ? 'Es el primero' : `Van ${cantidad}`} en esta guardia.`, 'success');
      setAbierto(false);
      setCategoria(null);
      setOtro(null);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo registrar.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div ref={contenedor} className="relative print:hidden">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        aria-haspopup="dialog"
        className={`press flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-sm ${
          destacado
            ? 'border-warn/50 bg-surface font-medium text-warn hover:bg-warn-soft'
            : 'border-line-strong bg-surface text-muted hover:text-ink'
        }`}
      >
        <UserRoundX className="h-4 w-4" aria-hidden="true" />
        Se fue un cliente
      </button>
      {abierto && (
        <div
          role="dialog"
          aria-label="Registrar un cliente que se fue"
          className="fixed inset-x-2 top-[3.75rem] z-30 origin-top-right animate-pop-in rounded-lg border border-line bg-surface p-3 shadow-panel sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-72"
        >
          {categorias.length > 1 && (
            <>
              <p className="text-xs font-medium text-muted">¿Qué buscaba? (opcional)</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {categorias.map((c) => {
                  const activa = categoria === c.id;
                  return (
                    <button
                      key={c.id}
                      type="button"
                      aria-pressed={activa}
                      onClick={() => setCategoria(activa ? null : c.id)}
                      className={`press flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                        activa ? 'font-medium' : 'border-line-strong text-muted hover:text-ink'
                      }`}
                      style={activa ? { borderColor: c.color, color: c.color, backgroundColor: `${c.color}14` } : undefined}
                    >
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: c.color }} aria-hidden="true" />
                      {c.nombre}
                    </button>
                  );
                })}
              </div>
            </>
          )}
          <p className={`text-xs font-medium text-muted ${categorias.length > 1 ? 'mt-3' : ''}`}>¿Por qué se fue?</p>
          <div className="mt-1.5 space-y-1">
            {MOTIVOS.map(({ motivo, etiqueta }) => (
              <button
                key={motivo}
                type="button"
                disabled={enviando}
                onClick={() => void registrar(motivo)}
                className="press group flex w-full items-center justify-between rounded-md border border-line px-3 py-2 text-left text-sm text-ink hover:border-accent hover:bg-accent-soft disabled:opacity-50 max-sm:h-11"
              >
                {etiqueta}
                <Check className="h-4 w-4 text-accent opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
              </button>
            ))}
            {otro === null ? (
              <button
                type="button"
                disabled={enviando}
                onClick={() => setOtro('')}
                className="press flex w-full items-center gap-2 rounded-md border border-dashed border-line-strong px-3 py-2 text-left text-sm text-muted hover:border-accent hover:text-ink disabled:opacity-50 max-sm:h-11"
              >
                <PenLine className="h-4 w-4" aria-hidden="true" />
                Otro motivo…
              </button>
            ) : (
              <form
                className="rounded-md border border-accent/60 p-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (otro.trim()) void registrar('OTRO', otro.trim());
                }}
              >
                <label htmlFor="detalle-perdido" className="text-xs font-medium text-muted">
                  Otro motivo: ¿por qué se fue?
                </label>
                <input
                  id="detalle-perdido"
                  autoFocus
                  autoComplete="off"
                  maxLength={LARGO_DETALLE}
                  placeholder="Ej.: venía con mascota"
                  className={`${inputClass} mt-1 h-10 w-full text-sm`}
                  value={otro}
                  onChange={(e) => setOtro(e.target.value)}
                />
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] tabular-nums text-subtle">
                    {otro.length}/{LARGO_DETALLE}
                  </span>
                  <div className="flex gap-1.5">
                    <button
                      type="button"
                      onClick={() => setOtro(null)}
                      className="press h-8 rounded-md px-2.5 text-sm text-muted hover:text-ink"
                    >
                      Volver
                    </button>
                    <button
                      type="submit"
                      disabled={enviando || !otro.trim()}
                      className="press h-8 rounded-md bg-accent px-3 text-sm font-medium text-accent-fg hover:bg-accent-hover disabled:opacity-40"
                    >
                      Registrar
                    </button>
                  </div>
                </div>
              </form>
            )}
          </div>
          <p className="mt-2 text-[11px] text-subtle">No se guarda ningún dato del cliente.</p>
        </div>
      )}
    </div>
  );
};

const CADA_MS = 30000;

interface AvisoProximaLibreProps {
  // Cambia con el estado de las habitaciones: la estimación se pide de nuevo al momento.
  firma: string;
  onAbrir: (habitacionId: number) => void;
}

// Con dos disponibles o menos, cuándo se libera la próxima (lo que se le contesta a quien espera en la ventanilla). Es una
// sola línea: no le quita lugar a las habitaciones; las que siguen, al pasar el mouse.
export const AvisoProximaLibre: React.FC<AvisoProximaLibreProps> = ({ firma, onAbrir }) => {
  const [datos, setDatos] = useState<ProximaLibre | null>(null);

  useEffect(() => {
    let vigente = true;
    const cargar = async () => {
      try {
        const nuevos = await api.getProximaLibre();
        if (vigente) setDatos(nuevos);
      } catch {
        // la estimación se actualiza en el próximo intento
      }
    };
    void cargar();
    const intervalo = setInterval(() => void cargar(), CADA_MS);
    return () => {
      vigente = false;
      clearInterval(intervalo);
    };
  }, [firma]);

  if (!datos) return null;
  const [primera, ...resto] = datos.proximas;
  const lleno = datos.disponibles === 0;
  const siguientes = resto
    .slice(0, 4)
    .map((p) => `${formatRoomNumber(p.numero)} (${p.categoria}): ${p.minutos} min`)
    .join(' · ');
  return (
    <section
      aria-label="Próxima habitación disponible"
      title={siguientes ? `Después: ${siguientes}` : undefined}
      className={`flex h-8 min-w-0 animate-pop-in items-center gap-2 rounded-md border px-2.5 text-sm ${
        lleno ? 'border-warn/40 bg-warn-soft' : 'border-line bg-surface'
      }`}
    >
      <Hourglass className={`h-4 w-4 shrink-0 ${lleno ? 'animate-reloj text-warn' : 'text-accent'}`} aria-hidden="true" />
      <span className="shrink-0 font-medium text-ink">
        {lleno ? 'Sin lugar' : datos.disponibles === 1 ? 'Queda 1' : `Quedan ${datos.disponibles}`}
      </span>
      {primera && (
        <span className="min-w-0 truncate text-muted">
          · Próxima:{' '}
          <button
            type="button"
            onClick={() => onAbrir(primera.habitacion_id)}
            className="font-medium text-ink underline decoration-line-strong underline-offset-2 hover:decoration-accent"
          >
            {formatRoomNumber(primera.numero)}
          </button>{' '}
          en <span className="font-semibold tabular-nums text-ink">{primera.minutos} min</span>{' '}
          <span className="tabular-nums text-subtle">
            ({primera.minimo}–{primera.maximo})
          </span>
        </span>
      )}
    </section>
  );
};
