import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { ArrowRight, Bot, Check, RotateCcw, Send, X } from 'lucide-react';
import { AccionAsistente, ConfirmacionAsistente, RespuestaAsistente } from '../types';
import { api, getErrorMessage } from '../services/api';
import Button from './ui/Button';

// Asistente de todo el personal: ayuda para usar el sistema y el estado de la ventanilla, y para la gerencia además
// el análisis de los datos del motel; todo calculado en su servidor. La conversación vive en un contexto: la misma se
// ve en el costado de Inteligencia y en el botón flotante de cualquier pantalla, y la paleta (Ctrl+K) le manda preguntas.

// La primera sugerencia explica la sección abierta (el servidor sabe en qué pantalla se pregunta).
const SUGERENCIAS: Record<'gerencia' | 'conserje', string[]> = {
  gerencia: [
    '¿Qué puedo hacer en esta pantalla?',
    '¿Cuánto facturamos la semana pasada?',
    '¿Cuántos turnos esperamos mañana?',
    '¿Qué categoría deja más plata?',
    '¿Quién tuvo más faltantes en los últimos 30 días?',
    '¿Cómo cambio una tarifa?',
    '¿Qué habitaciones están libres?',
  ],
  conserje: [
    '¿Qué puedo hacer en esta pantalla?',
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
    'Hola. Te ayudo a usar el sistema y a entender los datos del motel: ingresos, turnos, ocupación, horarios, categorías, caja, stock o lo que se espera para mañana. También hago lo que me pidas, con tu confirmación: «pasá la 7 a mantenimiento».',
  conserje:
    'Hola. Te ayudo a usar el sistema («¿cómo cobro un turno?»), te digo cómo está la ventanilla («¿qué habitaciones están libres?») y hago lo que me pidas, con tu confirmación: «cargale dos aguas a la 5», «pasá la 7 a limpieza».',
};

interface Mensaje {
  de: 'usuario' | 'asistente';
  texto: string;
  respuesta?: RespuestaAsistente;
  // La respuesta recién llegada se escribe de a poco (las anteriores ya están completas).
  nuevo?: boolean;
  // Qué pasó con la orden que propuso el asistente.
  orden?: 'pendiente' | 'enviando' | 'hecha' | 'cancelada' | 'fallida';
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
  reiniciar: () => void;
  preguntasHechas: string[];
  // La ventanilla se entera de lo que cambió una orden confirmada.
  registrarCambios: (manejador: () => void) => void;
  confirmar: (indice: number) => void;
  cancelar: (indice: number) => void;
  // La ventanilla avisa qué sección está abierta: viaja con cada pregunta y se nombra en el campo de texto.
  fijarPantalla: (vista: string, titulo: string) => void;
  tituloPantalla: string | null;
}

// Escribe el texto de a poco (unos 600 ms en total), como si el asistente lo estuviera redactando. Sin animaciones
// (prefers-reduced-motion) aparece completo.
const TextoAnimado: React.FC<{ texto: string; animar: boolean }> = ({ texto, animar }) => {
  const [visible, setVisible] = useState(animar ? 0 : texto.length);
  useEffect(() => {
    if (!animar || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setVisible(texto.length);
      return;
    }
    let cuadro = 0;
    const inicio = performance.now();
    const duracion = Math.min(900, 250 + texto.length * 3);
    const paso = (ahora: number) => {
      const avance = Math.min(1, (ahora - inicio) / duracion);
      setVisible(Math.ceil(texto.length * avance));
      if (avance < 1) cuadro = requestAnimationFrame(paso);
    };
    cuadro = requestAnimationFrame(paso);
    // Respaldo: si la pestaña está en segundo plano el navegador pausa los cuadros; el texto aparece completo igual.
    const seguro = setTimeout(() => setVisible(texto.length), duracion + 150);
    return () => {
      cancelAnimationFrame(cuadro);
      clearTimeout(seguro);
    };
  }, [texto, animar]);
  return (
    <>
      {texto.slice(0, visible)}
      {visible < texto.length && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-accent/60 align-middle" />}
    </>
  );
};

// Confirmar es hacer lo mismo que los botones de la pantalla: las reglas y la autoría son las de siempre.
const ejecutarOrden = async (c: ConfirmacionAsistente) => {
  if (c.tipo === 'estado') await api.updateHabitacionEstado(c.habitacion_id as number, c.estado as string);
  else if (c.tipo === 'consumo') await api.addConsumo(c.turno_id as string, c.articulo_id as number, c.cantidad as number);
  else if (c.tipo === 'novedad') await api.crearNovedad({ texto: c.texto as string, importante: Boolean(c.importante), habitacion_id: c.habitacion_id ?? null });
  else if (c.tipo === 'cliente_perdido') await api.registrarClientePerdido(c.motivo ?? 'SIN_LUGAR', c.categoria_id ?? null);
  else
    await api.createTurno({
      habitacion_id: c.habitacion_id as number,
      tipo_cliente: c.tipo_cliente ?? 'Auto',
      identificador_vehicular: c.patente ?? undefined,
      tarifa_id: c.tarifa_id ?? undefined,
    });
};

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
  // La última pregunta y su intención viajan con la siguiente: así el servidor entiende «¿y la semana pasada?».
  const ultima = useRef<{ pregunta: string; intencion: string } | null>(null);
  const pantalla = useRef<string | undefined>(undefined);
  const alCambiar = useRef<(() => void) | null>(null);
  const registrarCambios = useCallback((fn: () => void) => {
    alCambiar.current = fn;
  }, []);
  // La orden que espera confirmación: también se puede contestar escribiendo «sí» o «no».
  const ordenPendiente = useRef<{ indice: number; confirmacion: ConfirmacionAsistente } | null>(null);

  const marcarOrden = useCallback((indice: number, orden: Mensaje['orden']) => {
    setMensajes((m) => m.map((mensaje, i) => (i === indice ? { ...mensaje, orden } : mensaje)));
  }, []);

  const confirmar = useCallback(
    async (indice: number) => {
      const pendiente = ordenPendiente.current;
      if (!pendiente || pendiente.indice !== indice) return;
      ordenPendiente.current = null;
      marcarOrden(indice, 'enviando');
      try {
        await ejecutarOrden(pendiente.confirmacion);
        marcarOrden(indice, 'hecha');
        setMensajes((m) => [...m, { de: 'asistente', texto: pendiente.confirmacion.hecho, nuevo: true }]);
        alCambiar.current?.();
      } catch (err) {
        marcarOrden(indice, 'fallida');
        setMensajes((m) => [...m, { de: 'asistente', texto: getErrorMessage(err, 'No se pudo hacer.') }]);
      }
    },
    [marcarOrden],
  );

  const cancelar = useCallback(
    (indice: number) => {
      if (ordenPendiente.current?.indice === indice) ordenPendiente.current = null;
      marcarOrden(indice, 'cancelada');
    },
    [marcarOrden],
  );
  const [tituloPantalla, setTituloPantalla] = useState<string | null>(null);
  const fijarPantalla = useCallback((vista: string, titulo: string) => {
    pantalla.current = vista;
    setTituloPantalla(titulo);
  }, []);

  const preguntar = useCallback(async (texto: string) => {
    const limpia = texto.trim();
    if (!limpia || ocupado.current) return;
    const pendiente = ordenPendiente.current;
    if (pendiente && /^(s[ií]|dale|ok|confirmo|confirmar|hacelo)\b/i.test(limpia)) {
      setMensajes((m) => [...m, { de: 'usuario', texto: limpia }]);
      void confirmar(pendiente.indice);
      return;
    }
    if (pendiente && /^(no|cancela|cancelar|cancelá|dejalo|dejá)\b/i.test(limpia)) {
      setMensajes((m) => [...m, { de: 'usuario', texto: limpia }]);
      cancelar(pendiente.indice);
      return;
    }
    // Otra pregunta deja de lado la orden que esperaba.
    if (pendiente) cancelar(pendiente.indice);
    ocupado.current = true;
    setMensajes((m) => [...m, { de: 'usuario', texto: limpia }]);
    setPensando(true);
    try {
      const respuesta = await api.preguntar(limpia, ultima.current?.pregunta, ultima.current?.intencion, pantalla.current);
      ultima.current = { pregunta: limpia, intencion: respuesta.intencion };
      setMensajes((m) => {
        const confirmacion = respuesta.confirmacion;
        if (confirmacion) ordenPendiente.current = { indice: m.length, confirmacion };
        return [...m, { de: 'asistente', texto: respuesta.respuesta, respuesta, nuevo: true, orden: confirmacion ? 'pendiente' : undefined }];
      });
      if (respuesta.sugerencias.length) setSugeridas(respuesta.sugerencias);
    } catch (err) {
      setMensajes((m) => [...m, { de: 'asistente', texto: getErrorMessage(err, 'No pude responder ahora. Probá de nuevo.') }]);
    } finally {
      ocupado.current = false;
      setPensando(false);
    }
  }, [confirmar, cancelar]);

  const reiniciar = useCallback(() => {
    ultima.current = null;
    ordenPendiente.current = null;
    setMensajes([{ de: 'asistente', texto: SALUDO[perfil] }]);
    setSugeridas(SUGERENCIAS[perfil]);
  }, [perfil]);

  const preguntasHechas = mensajes.filter((m) => m.de === 'usuario').map((m) => m.texto);

  return (
    <ContextoAsistente.Provider
      value={{
        mensajes,
        pensando,
        sugeridas,
        esGerencia,
        preguntar,
        registrarAcciones,
        ejecutar,
        reiniciar,
        preguntasHechas,
        registrarCambios,
        confirmar,
        cancelar,
        fijarPantalla,
        tituloPantalla,
      }}
    >
      {children}
    </ContextoAsistente.Provider>
  );
};

interface ChatAsistenteProps {
  className?: string;
  onCerrar?: () => void;
}

export const ChatAsistente: React.FC<ChatAsistenteProps> = ({ className = 'h-[min(78vh,46rem)]', onCerrar }) => {
  const { mensajes, pensando, sugeridas, esGerencia, preguntar, ejecutar, reiniciar, preguntasHechas, tituloPantalla, confirmar, cancelar } = useAsistente();
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
        {mensajes.length > 1 && (
          <button
            type="button"
            onClick={reiniciar}
            aria-label="Empezar una conversación nueva"
            title="Empezar de nuevo"
            className="press hit rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
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
          <div key={i} className={`flex animate-pop-in ${m.de === 'usuario' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[92%] rounded-lg px-3 py-2 text-sm ${
                m.de === 'usuario' ? 'origin-bottom-right rounded-br-sm bg-accent text-accent-fg' : 'origin-bottom-left rounded-bl-sm bg-surface-2 text-ink'
              }`}
            >
              <p className="whitespace-pre-line">
                {m.de === 'asistente' ? <TextoAnimado texto={m.texto} animar={Boolean(m.nuevo) && i === mensajes.length - 1} /> : m.texto}
              </p>
              {m.respuesta?.pasos && m.respuesta.pasos.length > 0 && (
                <ol className="mt-2 space-y-1.5 animate-fade-in">
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
              {m.respuesta?.confirmacion && (
                <div className="mt-2 animate-fade-in rounded-md border border-accent/40 bg-surface px-3 py-2">
                  <p className="font-medium text-ink">{m.respuesta.confirmacion.titulo}</p>
                  {m.orden === 'pendiente' && (
                    <div className="mt-2 flex gap-1.5">
                      <button
                        type="button"
                        onClick={() => confirmar(i)}
                        className="press inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-xs font-medium text-accent-fg hover:bg-accent-hover"
                      >
                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        Confirmar
                      </button>
                      <button
                        type="button"
                        onClick={() => cancelar(i)}
                        className="press rounded-md border border-line-strong px-2.5 py-1 text-xs text-muted hover:text-ink"
                      >
                        Cancelar
                      </button>
                    </div>
                  )}
                  {m.orden === 'enviando' && <p className="mt-1 text-xs text-muted">Haciéndolo…</p>}
                  {m.orden === 'hecha' && <p className="mt-1 flex items-center gap-1 text-xs text-libre"><Check className="h-3 w-3" aria-hidden="true" /> Hecho</p>}
                  {m.orden === 'cancelada' && <p className="mt-1 text-xs text-muted">Cancelado: no se hizo nada.</p>}
                  {m.orden === 'fallida' && <p className="mt-1 text-xs text-danger">No se pudo hacer.</p>}
                </div>
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
            onKeyDown={(e) => {
              // ↑ con el campo vacío trae la última pregunta, para corregirla o repetirla.
              if (e.key === 'ArrowUp' && !texto && preguntasHechas.length) {
                e.preventDefault();
                setTexto(preguntasHechas[preguntasHechas.length - 1]);
              }
            }}
            maxLength={300}
            placeholder={tituloPantalla ? `Preguntá sobre ${tituloPantalla}…` : 'Escribí tu pregunta…'}
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
        className={`press fixed bottom-6 right-6 z-40 flex h-14 items-center gap-2 rounded-full bg-accent px-5 text-sm font-medium text-accent-fg shadow-panel transition-transform hover:-translate-y-0.5 hover:bg-accent-hover ${
          abierto ? '' : 'animate-llamado'
        }`}
      >
        {abierto ? <X className="h-5 w-5" aria-hidden="true" /> : <Bot className="h-5 w-5" aria-hidden="true" />}
        <span className="hidden sm:inline">{abierto ? 'Cerrar' : pensando ? 'Pensando…' : 'Asistente'}</span>
      </button>
    </div>
  );
};
