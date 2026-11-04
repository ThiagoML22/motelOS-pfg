import React, { useEffect, useRef, useState } from 'react';
import { Check, Hourglass, UserRoundX } from 'lucide-react';
import { Categoria, MotivoPerdida, ProximaLibre } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatRoomNumber } from '../utils/format';
import { useToast } from './ui/Toast';

const MOTIVOS: { motivo: MotivoPerdida; etiqueta: string }[] = [
  { motivo: 'SIN_LUGAR', etiqueta: 'No había lugar' },
  { motivo: 'ESPERA', etiqueta: 'No quiso esperar' },
  { motivo: 'PRECIO', etiqueta: 'Le pareció caro' },
];

// «Se fue un cliente»: dos toques (por qué se fue y, si se sabe, qué buscaba) y no guarda ningún dato de la persona.
export const BotonClientePerdido: React.FC<{ categorias: Categoria[]; destacado?: boolean }> = ({ categorias, destacado = false }) => {
  const { toast } = useToast();
  const [abierto, setAbierto] = useState(false);
  const [categoria, setCategoria] = useState<number | null>(null);
  const [enviando, setEnviando] = useState(false);
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

  const registrar = async (motivo: MotivoPerdida) => {
    setEnviando(true);
    try {
      const { en_la_guardia: cantidad } = await api.registrarClientePerdido(motivo, categoria);
      toast(`Registrado. ${cantidad === 1 ? 'Es el primero' : `Van ${cantidad}`} en esta guardia.`, 'success');
      setAbierto(false);
      setCategoria(null);
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
          className="absolute right-0 top-full z-30 mt-2 w-72 origin-top-right animate-pop-in rounded-lg border border-line bg-surface p-3 shadow-panel"
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
                className="press group flex w-full items-center justify-between rounded-md border border-line px-3 py-2 text-left text-sm text-ink hover:border-accent hover:bg-accent-soft disabled:opacity-50"
              >
                {etiqueta}
                <Check className="h-4 w-4 text-accent opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
              </button>
            ))}
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
  categorias: Categoria[];
  // Solo quien atiende registra clientes perdidos.
  puedeRegistrar: boolean;
  onAbrir: (habitacionId: number) => void;
}

// Con dos disponibles o menos, cuándo se libera la próxima (lo que se le contesta a quien espera en la ventanilla).
export const AvisoProximaLibre: React.FC<AvisoProximaLibreProps> = ({ firma, categorias, puedeRegistrar, onAbrir }) => {
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
  return (
    <section
      aria-label="Próxima habitación disponible"
      className={`mb-4 flex animate-pop-in flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border px-4 py-3 ${
        lleno ? 'border-warn/40 bg-warn-soft' : 'border-line bg-surface'
      }`}
    >
      <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${lleno ? 'bg-warn/15 text-warn' : 'bg-accent-soft text-accent'}`}>
        <Hourglass className={`h-4 w-4 ${lleno ? 'animate-reloj' : ''}`} aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">
          {lleno ? 'Sin habitaciones disponibles' : `${datos.disponibles === 1 ? 'Queda 1 disponible' : `Quedan ${datos.disponibles} disponibles`}`}
        </p>
        {primera ? (
          <p className="text-sm text-muted">
            La próxima sería la{' '}
            <button type="button" onClick={() => onAbrir(primera.habitacion_id)} className="font-medium text-ink underline decoration-line-strong underline-offset-2 hover:decoration-accent">
              {formatRoomNumber(primera.numero)}
            </button>{' '}
            ({primera.categoria}) en unos <span className="font-semibold tabular-nums text-ink">{primera.minutos} min</span>{' '}
            <span className="tabular-nums text-subtle">
              · entre {primera.minimo} y {primera.maximo}
            </span>
          </p>
        ) : (
          <p className="text-sm text-muted">No hay turnos en curso para estimar.</p>
        )}
      </div>
      {resto.length > 0 && (
        <ul className="hidden items-center gap-1.5 lg:flex" aria-label="Las que siguen">
          {resto.slice(0, 3).map((p, i) => (
            <li key={p.habitacion_id} className="animate-tarjeta-in" style={{ animationDelay: `${(i + 1) * 60}ms` }}>
              <button
                type="button"
                onClick={() => onAbrir(p.habitacion_id)}
                title={`${p.categoria}: entre ${p.minimo} y ${p.maximo} min`}
                className="press flex items-center gap-1.5 rounded-full border border-line-strong bg-surface px-2.5 py-1 text-xs text-muted hover:text-ink"
              >
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} aria-hidden="true" />
                {p.numero} · <span className="tabular-nums">{p.minutos} min</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {puedeRegistrar && <BotonClientePerdido categorias={categorias} destacado={lleno} />}
    </section>
  );
};
