import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ArrowRight, Bot, Send, X } from 'lucide-react';
import { AccionAsistente, RespuestaAsistente } from '../types';
import { api, getErrorMessage } from '../services/api';
import Button from './ui/Button';

// Asistente de todo el personal: ayuda para usar el sistema y el estado de la ventanilla, y para la gerencia además
// el análisis de los datos del motel; todo calculado en su servidor. La conversación vive en un contexto: la misma se
// ve en el costado de Inteligencia y en el botón flotante de cualquier pantalla, y la paleta (Ctrl+K) le manda preguntas.

const SUGERENCIAS: Record<'gerencia' | 'conserje', string[]> = {
  gerencia: [
    '¿Cuánto facturamos la semana pasada?',
    '¿Cuántos turnos esperamos mañana?',
    '¿Qué categoría deja más plata?',
    '¿Quién tuvo más faltantes en los últimos 30 días?',
    '¿Cómo cambio una tarifa?',
    '¿Qué habitaciones están libres?',
  ],
  conserje: [
    '¿Cómo abro un turno?',
    '¿Qué habitaciones están libres?',
    '¿Cuál vence primero?',
    '¿Cómo cierro la caja?',
    '¿Cuánto sale la VIP?',
    'Se cortó la conexión, ¿qué hago?',
  ],
};

const SALUDO = {
  gerencia:
    'Hola. Te ayudo a usar el sistema y a entender los datos del motel: ingresos, turnos, ocupación, horarios, categorías, caja, stock o lo que se espera para mañana.',
  conserje:
    'Hola. Te ayudo a usar el sistema («¿cómo cobro un turno?») y te digo cómo está la ventanilla («¿qué habitaciones están libres?», «¿cuánto debe la 5?»).',
};

interface Mensaje {
  de: 'usuario' | 'asistente';
  texto: string;
  respuesta?: RespuestaAsistente;
}

interface Conversacion {
  mensajes: Mensaje[];
  pensando: boolean;
  sugeridas: string[];
  esGerencia: boolean;
  preguntar: (texto: string) => Promise<void>;
  // La ventanilla registra cómo ejecutar los botones que propone el asistente (ir a una pantalla, abrir una habitación).
  registrarAcciones: (manejador: (accion: AccionAsistente) => void) => void;
  ejecutar: (accion: AccionAsistente) => void;
}

const ContextoAsistente = createContext<Conversacion | null>(null);

export const useAsistente = (): Conversacion => {
  const contexto = useContext(ContextoAsistente);
  if (!contexto) throw new Error('useAsistente fuera de AsistenteProvider');
  return contexto;
};

export const AsistenteProvider: React.FC<{ esGerencia: boolean; children: React.ReactNode }> = ({ esGerencia, children }) => {
  const perfil = esGerencia ? 'gerencia' : 'conserje';
  const [mensajes, setMensajes] = useState<Mensaje[]>([{ de: 'asistente', texto: SALUDO[perfil] }]);
  const [pensando, setPensando] = useState(false);
  const [sugeridas, setSugeridas] = useState(SUGERENCIAS[perfil]);
  const ocupado = useRef(false);
  const manejador = useRef<((accion: AccionAsistente) => void) | null>(null);
  const registrarAcciones = useCallback((fn: (accion: AccionAsistente) => void) => {
    manejador.current = fn;
  }, []);
  const ejecutar = useCallback((accion: AccionAsistente) => manejador.current?.(accion), []);

  const preguntar = useCallback(async (texto: string) => {
    const limpia = texto.trim();
    if (!limpia || ocupado.current) return;
    ocupado.current = true;
    setMensajes((m) => [...m, { de: 'usuario', texto: limpia }]);
    setPensando(true);
    try {
      const respuesta = await api.preguntar(limpia);
      setMensajes((m) => [...m, { de: 'asistente', texto: respuesta.respuesta, respuesta }]);
      if (respuesta.sugerencias.length) setSugeridas(respuesta.sugerencias);
    } catch (err) {
      setMensajes((m) => [...m, { de: 'asistente', texto: getErrorMessage(err, 'No pude responder ahora. Probá de nuevo.') }]);
    } finally {
      ocupado.current = false;
      setPensando(false);
    }
  }, []);

  return (
    <ContextoAsistente.Provider value={{ mensajes, pensando, sugeridas, esGerencia, preguntar, registrarAcciones, ejecutar }}>
      {children}
    </ContextoAsistente.Provider>
  );
};

interface ChatAsistenteProps {
  className?: string;
  onCerrar?: () => void;
}

export const ChatAsistente: React.FC<ChatAsistenteProps> = ({ className = 'h-[min(78vh,46rem)]', onCerrar }) => {
  const { mensajes, pensando, sugeridas, esGerencia, preguntar, ejecutar } = useAsistente();
  const [texto, setTexto] = useState('');
  const lista = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLInputElement>(null);

  useEffect(() => {
    lista.current?.scrollTo({ top: lista.current.scrollHeight, behavior: 'smooth' });
  }, [mensajes, pensando]);

  useEffect(() => {
    if (onCerrar) entrada.current?.focus();
  }, [onCerrar]);

  const enviar = (consulta: string) => {
    if (!consulta.trim() || pensando) return;
    setTexto('');
    void preguntar(consulta);
  };

  return (
    <section className={`flex flex-col overflow-hidden rounded-lg border border-line bg-surface ${className}`} aria-label="Asistente">
      <header className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-accent text-accent-fg">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-ink">Asistente</p>
          <p className="text-xs text-muted">
            {esGerencia ? 'Ayuda y datos del motel, sin internet' : 'Te ayuda a usar el sistema, sin internet'}
          </p>
        </div>
        {onCerrar && (
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar el asistente"
            className="press hit rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </header>
      <div ref={lista} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
        {mensajes.map((m, i) => (
          <div key={i} className={`flex ${m.de === 'usuario' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[92%] rounded-lg px-3 py-2 text-sm ${
                m.de === 'usuario' ? 'rounded-br-sm bg-accent text-accent-fg' : 'rounded-bl-sm bg-surface-2 text-ink'
              }`}
            >
              <p className="whitespace-pre-line">{m.texto}</p>
              {m.respuesta?.pasos && m.respuesta.pasos.length > 0 && (
                <ol className="mt-2 space-y-1.5">
                  {m.respuesta.pasos.map((paso, j) => (
                    <li key={j} className="flex gap-2">
                      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-accent text-[11px] font-semibold text-accent-fg">
                        {j + 1}
                      </span>
                      <span>{paso}</span>
                    </li>
                  ))}
                </ol>
              )}
              {m.respuesta?.acciones && m.respuesta.acciones.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {m.respuesta.acciones.map((accion) => (
                    <button
                      key={accion.etiqueta}
                      type="button"
                      onClick={() => ejecutar(accion)}
                      className="press inline-flex items-center gap-1 rounded-md border border-accent/40 bg-surface px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent-soft"
                    >
                      {accion.etiqueta}
                      <ArrowRight className="h-3 w-3" aria-hidden="true" />
                    </button>
                  ))}
                </div>
              )}
              {m.respuesta?.tabla && m.respuesta.tabla.filas.length > 0 && (
                <div className="mt-2 overflow-x-auto rounded border border-line bg-surface">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-line text-subtle">
                        {m.respuesta.tabla.columnas.map((c) => (
                          <th key={c} className="px-2 py-1 font-medium">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {m.respuesta.tabla.filas.slice(0, 8).map((fila, j) => (
                        <tr key={j} className="border-b border-line last:border-0">
                          {fila.map((celda, k) => (
                            <td key={k} className="px-2 py-1">
                              {celda}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {(m.respuesta?.periodo || m.respuesta?.detalle) && (
                <p className="mt-1.5 text-[11px] text-muted">
                  {m.respuesta.periodo && <>Período: {m.respuesta.periodo}. </>}
                  {m.respuesta.detalle}
                </p>
              )}
            </div>
          </div>
        ))}
        {pensando && (
          <div className="flex justify-start">
            <div className="flex gap-1 rounded-lg rounded-bl-sm bg-surface-2 px-3 py-3" aria-label="Pensando">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="border-t border-line px-3 py-3">
        <div className="sin-barra mb-2 flex gap-1.5 overflow-x-auto pb-1">
          {sugeridas.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => enviar(s)}
              className="press shrink-0 rounded-full border border-line-strong bg-surface px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-accent"
            >
              {s}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            enviar(texto);
          }}
          className="flex gap-2"
        >
          <input
            ref={entrada}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            maxLength={300}
            placeholder="Escribí tu pregunta…"
            aria-label="Pregunta para el asistente"
            className="min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-subtle focus:border-accent focus:ring-1 focus:ring-accent focus-visible:outline-none"
          />
          <Button type="submit" disabled={!texto.trim() || pensando} aria-label="Enviar pregunta">
            <Send className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
      </div>
    </section>
  );
};

interface AsistenteFlotanteProps {
  abierto: boolean;
  onCambiar: (abierto: boolean) => void;
  // En Inteligencia, con pantalla ancha, el asistente ya está en el costado: el botón se oculta.
  ocultarEnPantallaAncha: boolean;
}

// Botón redondo abajo a la derecha que abre el asistente desde cualquier pantalla, para todo el personal.
export const AsistenteFlotante: React.FC<AsistenteFlotanteProps> = ({ abierto, onCambiar, ocultarEnPantallaAncha }) => {
  const { pensando } = useAsistente();
  return (
    <div className={`print:hidden ${ocultarEnPantallaAncha ? 'xl:hidden' : ''}`}>
      {abierto && (
        <div className="fixed inset-x-3 bottom-24 z-40 animate-pop-in sm:inset-x-auto sm:right-6 sm:w-[24rem]">
          <ChatAsistente className="h-[min(70vh,40rem)] shadow-panel" onCerrar={() => onCambiar(false)} />
        </div>
      )}
      <button
        type="button"
        onClick={() => onCambiar(!abierto)}
        aria-expanded={abierto}
        aria-label={abierto ? 'Cerrar el asistente' : 'Abrir el asistente'}
        title="Asistente"
        className="press fixed bottom-6 right-6 z-40 flex h-14 items-center gap-2 rounded-full bg-accent px-5 text-sm font-medium text-accent-fg shadow-panel hover:bg-accent-hover"
      >
        {abierto ? <X className="h-5 w-5" aria-hidden="true" /> : <Bot className="h-5 w-5" aria-hidden="true" />}
        <span className="hidden sm:inline">{abierto ? 'Cerrar' : pensando ? 'Pensando…' : 'Asistente'}</span>
      </button>
    </div>
  );
};
