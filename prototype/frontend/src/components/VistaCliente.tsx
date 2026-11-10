import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  BedDouble,
  BellRing,
  Check,
  Clock,
  Cookie,
  CreditCard,
  CupSoda,
  HandCoins,
  Heart,
  type LucideIcon,
  Minus,
  Package,
  Phone,
  Plus,
  Receipt,
  ShieldCheck,
  ShoppingBag,
  Star,
  Timer,
  Wallet,
  Wifi,
  X,
} from 'lucide-react';
import { EstadiaCliente, PedidoEstadia } from '../types';
import { api, getErrorMessage } from '../services/api';
import { useDialog } from '../hooks/useDialog';
import { formatDuration, formatMoney, formatRoomNumber } from '../utils/format';
import { aplicarMarca } from '../utils/marca';
import Mot, { EstadoMot } from './Mot';

const REFRESCO_MS = 10000;
// Desde cuántos minutos antes del final se le ofrece quedarse más.
const AVISO_FINAL_MIN = 20;

type Pestana = 'estadia' | 'pedir' | 'mot';
type Hoja = 'carrito' | 'tiempo' | 'cuenta';

const AVISOS: Record<string, { etiqueta: string; icono: LucideIcon; listo: string }> = {
  TOALLAS: { etiqueta: 'Necesito toallas', icono: BedDouble, listo: 'Ya te las llevan.' },
  LLAMAR: { etiqueta: 'Que me llamen', icono: Phone, listo: 'Enseguida te llaman.' },
};

const ICONO_MEDIO: Record<string, LucideIcon> = { EFECTIVO: HandCoins, POSNET: CreditCard, MERCADO_PAGO: Wallet };

const ICONO_CATEGORIA: Record<string, LucideIcon> = { bebidas: CupSoda, snacks: Cookie, 'cuidado personal': Heart };
const iconoDe = (categoria: string | null): LucideIcon => ICONO_CATEGORIA[(categoria ?? '').toLowerCase()] ?? Package;

const PASOS = ['Recibido', 'En camino', 'Entregado'];

const hora = (iso: string) => new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

// Un carrito son varias líneas con el mismo lote: el cliente lo ve como un solo pedido.
const agrupar = (pedidos: PedidoEstadia[]): PedidoEstadia[][] => {
  const grupos = new Map<string, PedidoEstadia[]>();
  for (const p of pedidos) {
    const clave = p.lote ?? `p${p.id}`;
    grupos.set(clave, [...(grupos.get(clave) ?? []), p]);
  }
  return [...grupos.values()];
};

const pasoDe = (lineas: PedidoEstadia[]): number => {
  if (lineas.some((l) => l.estado === 'Pendiente')) return 0;
  return lineas.some((l) => l.estado === 'En camino') ? 1 : 2;
};

const Tarjeta: React.FC<{ titulo?: string; children: React.ReactNode; retraso?: number }> = ({ titulo, children, retraso = 0 }) => (
  <section className="animate-tarjeta-in rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur" style={{ animationDelay: `${retraso}ms` }}>
    {titulo && <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-white/50">{titulo}</h2>}
    {children}
  </section>
);

// El tiempo de la estadía base como un anillo que se completa; pasada la base, cambia de color.
const Anillo: React.FC<{ parte: number; excedido: boolean; children: React.ReactNode }> = ({ parte, excedido, children }) => {
  const radio = 96;
  const largo = 2 * Math.PI * radio;
  return (
    <div className="relative mx-auto grid h-56 w-56 place-items-center">
      <svg viewBox="0 0 220 220" className="absolute inset-0 -rotate-90" aria-hidden="true">
        <circle cx="110" cy="110" r={radio} fill="none" stroke="rgb(255 255 255 / 0.1)" strokeWidth="10" />
        <circle
          cx="110"
          cy="110"
          r={radio}
          fill="none"
          stroke={excedido ? '#fb7185' : 'rgb(var(--accent-claro, 147 197 253))'}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={largo}
          strokeDashoffset={largo * (1 - Math.min(parte, 1))}
          className="transition-[stroke-dashoffset] duration-1000 ease-linear"
        />
      </svg>
      <div className="text-center">{children}</div>
    </div>
  );
};

// Una hoja que sube desde abajo: en el celular se alcanza con el pulgar.
const HojaInferior: React.FC<{ titulo: string; onCerrar: () => void; children: React.ReactNode }> = ({ titulo, onCerrar, children }) => {
  const idTitulo = useId();
  const ref = useDialog<HTMLDivElement>(onCerrar);
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center">
      <div className="absolute inset-0 animate-fade-in bg-black/60" onClick={onCerrar} aria-hidden="true" />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
        className="hoja-entrar relative max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-3xl border-t border-white/10 bg-[#101829] p-5 pb-7 text-white focus:outline-none"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 id={idTitulo} className="text-lg font-semibold">
            {titulo}
          </h2>
          <button type="button" onClick={onCerrar} aria-label="Cerrar" className="press grid h-10 w-10 place-items-center rounded-full bg-white/10">
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
};

// De 1 a 5 y, si no estuvo bien, qué falló. Sin texto libre y sin nada que diga quién es.
const Calificar: React.FC<{ token: string; problemas: { valor: number; etiqueta: string }[]; onListo: () => void }> = ({ token, problemas, onListo }) => {
  const [puntaje, setPuntaje] = useState(0);
  const [marcados, setMarcados] = useState(0);
  const [enviando, setEnviando] = useState(false);
  const [hecho, setHecho] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enviar = async () => {
    setEnviando(true);
    setError(null);
    try {
      await api.calificarEstadia(token, puntaje, puntaje <= 3 ? marcados : 0);
      setHecho(true);
      onListo();
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo enviar. Probá de nuevo.'));
    } finally {
      setEnviando(false);
    }
  };

  if (hecho) {
    return (
      <p className="flex animate-pop-in items-center justify-center gap-2 py-2 text-sm font-medium">
        <Check className="h-4 w-4 text-emerald-300" aria-hidden="true" />
        ¡Gracias por contarnos!
      </p>
    );
  }
  return (
    <div>
      <p className="text-center text-sm text-white/80">¿Cómo estuvo todo?</p>
      <div role="radiogroup" aria-label="Puntaje de la estadía" className="mt-2 flex justify-center gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={puntaje === n}
            aria-label={`${n} de 5`}
            onClick={() => setPuntaje(n)}
            className="press grid h-11 w-11 place-items-center rounded-full"
          >
            <Star className={`h-7 w-7 transition ${n <= puntaje ? 'fill-amber-300 text-amber-300' : 'text-white/30'}`} aria-hidden="true" />
          </button>
        ))}
      </div>
      {puntaje > 0 && puntaje <= 3 && (
        <div className="mt-3 animate-fade-in">
          <p className="mb-1.5 text-center text-xs text-white/60">¿Qué falló?</p>
          <div className="flex flex-wrap justify-center gap-1.5">
            {problemas.map((p) => {
              const activo = Boolean(marcados & p.valor);
              return (
                <button
                  key={p.valor}
                  type="button"
                  aria-pressed={activo}
                  onClick={() => setMarcados(marcados ^ p.valor)}
                  className={`press rounded-full border px-3 py-1.5 text-xs ${activo ? 'border-rose-300 bg-rose-300/20 text-rose-100' : 'border-white/15 text-white/70'}`}
                >
                  {p.etiqueta}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {error && <p className="mt-2 text-center text-xs text-rose-300">{error}</p>}
      {puntaje > 0 && (
        <button type="button" disabled={enviando} onClick={() => void enviar()} className="press mt-3 w-full animate-fade-in rounded-xl bg-white py-3 text-sm font-semibold text-slate-900 disabled:opacity-60">
          {enviando ? 'Enviando…' : 'Enviar'}
        </button>
      )}
      <p className="mt-2 text-center text-[11px] text-white/40">Es anónimo: nadie sabe quién lo marcó.</p>
    </div>
  );
};

// Mot en la página del cliente: contesta con botones, sin texto libre, con los datos de su estadía.
const PestanaMot: React.FC<{ datos: EstadiaCliente; onAvisar: (tipo: string) => void }> = ({ datos, onAvisar }) => {
  const [elegida, setElegida] = useState<string | null>(null);
  const [estado, setEstado] = useState<EstadoMot>('saludando');
  const fin = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const preguntas = datos.mot ?? [];
  const respuesta = preguntas.find((p) => p.id === elegida);

  const moverseUnRato = useCallback((nuevo: EstadoMot, duracion: number) => {
    clearTimeout(fin.current);
    setEstado(nuevo);
    fin.current = setTimeout(() => setEstado('reposo'), duracion);
  }, []);

  useEffect(() => {
    moverseUnRato('saludando', 2200);
    return () => clearTimeout(fin.current);
  }, [moverseUnRato]);

  const preguntar = (id: string) => {
    setElegida(id);
    moverseUnRato('hablando', 1500);
  };

  return (
    <div className="space-y-3">
      <div className="flex animate-fade-in flex-col items-center pt-2">
        <p key={elegida ?? 'hola'} className="max-w-xs animate-pop-in rounded-2xl bg-white/10 px-4 py-3 text-center text-sm leading-relaxed" aria-live="polite">
          {respuesta?.respuesta ?? datos.bienvenida ?? '¡Hola! Soy Mot. Tocá una pregunta y te cuento.'}
        </p>
        <Mot estado={estado} className="mt-3 h-36 w-28" />
      </div>
      <Tarjeta titulo="Preguntale a Mot">
        <div className="flex flex-wrap gap-2">
          {preguntas.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => preguntar(p.id)}
              aria-pressed={elegida === p.id}
              className={`press flex items-center gap-1.5 rounded-full border px-3 py-2 text-sm ${elegida === p.id ? 'border-white bg-white text-slate-900' : 'border-white/15 bg-white/5 text-white/85'}`}
            >
              {p.id === 'wifi' && <Wifi className="h-4 w-4" aria-hidden="true" />}
              {p.pregunta}
            </button>
          ))}
        </div>
      </Tarjeta>
      <Tarjeta titulo="Avisar sin llamar">
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(AVISOS).map(([tipo, { etiqueta, icono: Icono }]) => (
            <button
              key={tipo}
              type="button"
              onClick={() => onAvisar(tipo)}
              className="press flex flex-col items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-2 py-3 text-center text-xs text-white/80 hover:bg-white/10"
            >
              <Icono className="h-5 w-5" aria-hidden="true" />
              {etiqueta}
            </button>
          ))}
        </div>
      </Tarjeta>
    </div>
  );
};

// Lo que ve el cliente con el QR de su ticket, en su celular: sin cuenta y sin datos personales. No es parte de la
// aplicación del personal: no pide sesión y el enlace deja de funcionar cuando se cierra el turno.
const VistaCliente: React.FC<{ token: string }> = ({ token }) => {
  const [datos, setDatos] = useState<EstadiaCliente | null>(null);
  const [invalido, setInvalido] = useState(false);
  const [pestana, setPestana] = useState<Pestana>('estadia');
  const [hoja, setHoja] = useState<Hoja | null>(null);
  const [rubro, setRubro] = useState<string | null>(null);
  const [elegidos, setElegidos] = useState<Record<number, number>>({});
  const [medio, setMedio] = useState('EFECTIVO');
  const [enviando, setEnviando] = useState(false);
  const [mensaje, setMensaje] = useState<{ texto: string; error: boolean } | null>(null);
  const [ahora, setAhora] = useState(Date.now());
  // Diferencia con el reloj del servidor: el del celular puede estar corrido.
  const desfase = useRef(0);
  const estadosVistos = useRef<Map<number, string> | null>(null);

  const cargar = useCallback(async () => {
    try {
      const nuevos = await api.getEstadiaCliente(token);
      if (nuevos.ahora) desfase.current = new Date(nuevos.ahora).getTime() - Date.now();
      // Lo que cambió desde la última vez se avisa: el cliente no tiene que estar mirando la lista.
      const vistos = estadosVistos.current;
      if (vistos) {
        const cambios = (nuevos.pedidos ?? []).filter((p) => p.tipo === 'ARTICULO' && vistos.has(p.id) && vistos.get(p.id) !== p.estado);
        if (cambios.some((p) => p.estado === 'Rechazado')) setMensaje({ texto: 'Eso no está disponible ahora. No se te cobra.', error: true });
        else if (cambios.some((p) => p.estado === 'Atendido')) setMensaje({ texto: 'Pedido entregado. ¡Que lo disfrutes!', error: false });
        else if (cambios.some((p) => p.estado === 'En camino')) setMensaje({ texto: 'Tu pedido ya va en camino.', error: false });
      }
      estadosVistos.current = new Map((nuevos.pedidos ?? []).map((p) => [p.id, p.estado]));
      setDatos(nuevos);
      aplicarMarca(nuevos.color_marca);
    } catch {
      setInvalido(true);
    }
  }, [token]);

  useEffect(() => {
    document.documentElement.dataset.theme = 'dark';
    document.title = 'Tu estadía';
    void cargar();
    const refresco = setInterval(() => void cargar(), REFRESCO_MS);
    const reloj = setInterval(() => setAhora(Date.now()), 1000);
    return () => {
      clearInterval(refresco);
      clearInterval(reloj);
    };
  }, [cargar]);

  useEffect(() => {
    if (!mensaje) return;
    const fin = setTimeout(() => setMensaje(null), 4500);
    return () => clearTimeout(fin);
  }, [mensaje]);

  const articulos = useMemo(() => datos?.articulos ?? [], [datos]);
  const seleccion = useMemo(() => articulos.filter((a) => elegidos[a.id]), [articulos, elegidos]);
  const subtotal = seleccion.reduce((suma, a) => suma + a.precio * elegidos[a.id], 0);
  const unidades = seleccion.reduce((suma, a) => suma + elegidos[a.id], 0);
  const rubros = useMemo(() => [...new Set(articulos.map((a) => a.categoria ?? 'Otros'))], [articulos]);
  const visibles = rubro ? articulos.filter((a) => (a.categoria ?? 'Otros') === rubro) : articulos;

  const cambiar = (id: number, cambio: number) =>
    setElegidos((e) => {
      const cantidad = Math.min(Math.max((e[id] ?? 0) + cambio, 0), 5);
      const { [id]: _, ...resto } = e;
      return cantidad ? { ...resto, [id]: cantidad } : resto;
    });

  const pedir = async () => {
    setEnviando(true);
    try {
      await api.pedirCarrito(token, seleccion.map((a) => ({ articulo_id: a.id, cantidad: elegidos[a.id] })));
      setElegidos({});
      setHoja(null);
      setPestana('estadia');
      setMensaje({ texto: 'Listo: te avisamos cuando salga para tu habitación.', error: false });
    } catch (err) {
      setMensaje({ texto: getErrorMessage(err, 'No se pudo hacer el pedido.'), error: true });
    } finally {
      setEnviando(false);
      void cargar();
    }
  };

  const avisar = async (pedido: { tipo: string; minutos?: number; medio_pago?: string }, listo: string) => {
    setEnviando(true);
    try {
      await api.pedirCliente(token, pedido);
      setHoja(null);
      setMensaje({ texto: listo, error: false });
    } catch (err) {
      setMensaje({ texto: getErrorMessage(err, 'No se pudo avisar.'), error: true });
    } finally {
      setEnviando(false);
      void cargar();
    }
  };

  const fondo = 'cielo relative min-h-screen overflow-x-hidden px-4 pb-44 pt-6 text-white';

  if (invalido || (datos && !datos.activa)) {
    return (
      <main className={`${fondo} grid place-items-center pb-6 text-center`}>
        <div className="w-full max-w-sm animate-pop-in">
          {invalido ? (
            <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-white/10">
              <X className="h-7 w-7" aria-hidden="true" />
            </span>
          ) : (
            <Mot estado="saludando" className="mx-auto h-36 w-28" />
          )}
          <h1 className="mt-4 text-xl font-semibold">{invalido ? 'Este código no es válido' : '¡Gracias por venir!'}</h1>
          <p className="mt-1 text-sm text-white/60">{invalido ? 'Pedí tu ticket en la ventanilla.' : 'Tu estadía terminó y este enlace ya no se usa.'}</p>
          {datos?.puede_calificar && (
            <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.06] p-4">
              <Calificar token={token} problemas={datos.problemas ?? []} onListo={() => undefined} />
            </div>
          )}
        </div>
      </main>
    );
  }
  if (!datos) {
    return (
      <main className={`${fondo} grid place-items-center`}>
        <p className="animate-pulse text-sm text-white/60">Cargando tu estadía…</p>
      </main>
    );
  }

  const inicio = new Date(datos.hora_inicio as string).getTime();
  const transcurrido = ahora + desfase.current - inicio;
  const baseMs = (datos.estadia_base_min ?? 120) * 60000;
  const excedido = transcurrido > baseMs;
  const restanMin = Math.ceil((baseMs - transcurrido) / 60000);
  const pedidos = datos.pedidos ?? [];
  const delMinibar = agrupar(pedidos.filter((p) => p.tipo === 'ARTICULO'));
  const avisos = pedidos.filter((p) => p.tipo !== 'ARTICULO');
  const pidioLaCuenta = avisos.some((p) => p.tipo === 'SALIDA' && p.estado !== 'Rechazado');
  const avisoDeTiempo = avisos.find((p) => p.tipo === 'TIEMPO' && p.estado !== 'Rechazado');

  return (
    <main className={fondo}>
      <div className="mx-auto max-w-md space-y-3">
        <header className="animate-fade-in text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-white/50">{datos.motel}</p>
          <h1 className="mt-1 text-lg font-semibold">
            {formatRoomNumber(datos.numero as number)}
            {datos.categoria && <span className="font-normal text-white/60"> · {datos.categoria}</span>}
          </h1>
        </header>

        {pestana === 'estadia' && (
          <div key="estadia" className="animate-fade-in space-y-3">
            <div className="animate-pop-in py-1">
              <Anillo parte={transcurrido / baseMs} excedido={excedido}>
                <p className="font-mono text-4xl font-semibold tabular-nums">{formatDuration(transcurrido)}</p>
                <p className={`mt-1 flex items-center justify-center gap-1 text-sm ${excedido ? 'text-rose-300' : 'text-white/60'}`}>
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {excedido ? 'Pasaste la estadía base' : `Quedan ${restanMin} min de estadía`}
                </p>
              </Anillo>
            </div>

            {!pidioLaCuenta && !avisoDeTiempo && (excedido || restanMin <= AVISO_FINAL_MIN) && (
              <button type="button" onClick={() => setHoja('tiempo')} className="press flex w-full animate-pop-in items-center gap-3 rounded-2xl bg-amber-300/15 px-4 py-3 text-left">
                <Timer className="h-5 w-5 shrink-0 text-amber-200" aria-hidden="true" />
                <span className="min-w-0 flex-1 text-sm">
                  <span className="block font-medium text-amber-100">{excedido ? 'Ya estás en tiempo extra' : `Te quedan ${restanMin} min`}</span>
                  <span className="text-amber-100/70">Mirá cuánto sale quedarte más</span>
                </span>
              </button>
            )}

            <div className="grid grid-cols-2 gap-2">
              <button type="button" onClick={() => setHoja('tiempo')} className="press flex items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-3 text-sm font-medium hover:bg-white/10">
                <Timer className="h-4 w-4" aria-hidden="true" />
                Quedarme más
              </button>
              <button type="button" onClick={() => setHoja('cuenta')} disabled={pidioLaCuenta} className="press flex items-center justify-center gap-2 rounded-xl bg-white px-3 py-3 text-sm font-semibold text-slate-900 disabled:bg-white/10 disabled:text-white/60">
                <Receipt className="h-4 w-4" aria-hidden="true" />
                {pidioLaCuenta ? 'Cuenta pedida' : 'Pedir la cuenta'}
              </button>
            </div>

            {avisoDeTiempo && <p className="text-center text-xs text-white/60">{avisoDeTiempo.descripcion.replace('Se queda', 'Avisaste que te quedás')}.</p>}

            <Tarjeta titulo="Tu cuenta">
              <dl className="space-y-1 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-white/70">
                    Estadía{datos.franja && <span className="text-white/40"> · {datos.franja}</span>}
                  </dt>
                  <dd className="tabular-nums">{formatMoney(datos.tarifa_base ?? 0)}</dd>
                </div>
                {(datos.total_sobreturno ?? 0) > 0 && (
                  <div className="flex justify-between gap-3">
                    <dt className="text-white/70">Tiempo extra</dt>
                    <dd className="tabular-nums">{formatMoney(datos.total_sobreturno ?? 0)}</dd>
                  </div>
                )}
                {datos.consumos?.map((c, i) => (
                  <div key={i} className="flex justify-between gap-3">
                    <dt className="text-white/70">
                      {c.descripcion} <span className="text-white/40">× {c.cantidad}</span>
                    </dt>
                    <dd className="tabular-nums">{formatMoney(c.subtotal)}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-3 flex items-baseline justify-between border-t border-white/10 pt-3">
                <span className="text-sm text-white/70">Total hasta ahora</span>
                <span className="text-2xl font-semibold tabular-nums">{formatMoney(datos.total ?? 0)}</span>
              </div>
              {datos.proximo_cargo && (
                <p className="mt-1 text-right text-xs text-white/50">
                  En {datos.proximo_cargo.minutos} min se suman {formatMoney(datos.proximo_cargo.monto)}
                </p>
              )}
            </Tarjeta>

            {delMinibar.length > 0 && (
              <Tarjeta titulo="Tus pedidos" retraso={60}>
                <ul className="space-y-3">
                  {delMinibar.map((lineas) => {
                    const todoRechazado = lineas.every((l) => l.estado === 'Rechazado');
                    const paso = pasoDe(lineas);
                    return (
                      <li key={lineas[0].lote ?? lineas[0].id}>
                        <ul className="space-y-0.5 text-sm text-white/85">
                          {lineas.map((l) => (
                            <li key={l.id} className={l.estado === 'Rechazado' ? 'text-white/40 line-through' : ''}>
                              {l.cantidad} × {l.descripcion}
                            </li>
                          ))}
                        </ul>
                        {todoRechazado ? (
                          <p className="mt-1 text-xs text-rose-300">No está disponible ahora. No se te cobra.</p>
                        ) : (
                          <ol className="mt-2 flex items-center" aria-label={`Pedido: ${PASOS[paso]}`}>
                            {PASOS.map((nombre, i) => (
                              <li key={nombre} className={`flex items-center ${i > 0 ? 'flex-1' : ''}`}>
                                {i > 0 && <span className={`mx-1 h-0.5 flex-1 rounded ${i <= paso ? 'bg-emerald-300' : 'bg-white/15'}`} aria-hidden="true" />}
                                <span className={`flex items-center gap-1 text-[11px] ${i === paso ? 'font-semibold text-emerald-200' : i < paso ? 'text-emerald-200/70' : 'text-white/40'}`}>
                                  <span className={`grid h-4 w-4 place-items-center rounded-full ${i <= paso ? 'bg-emerald-300 text-slate-900' : 'bg-white/15'} ${i === paso && paso < 2 ? 'animate-latido' : ''}`} aria-hidden="true">
                                    {i < paso || paso === 2 ? <Check className="h-2.5 w-2.5" /> : null}
                                  </span>
                                  {nombre}
                                </span>
                              </li>
                            ))}
                          </ol>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </Tarjeta>
            )}

            {pidioLaCuenta && (
              <Tarjeta retraso={90}>
                {datos.calificada ? (
                  <p className="flex animate-pop-in items-center justify-center gap-2 py-1 text-sm font-medium">
                    <Check className="h-4 w-4 text-emerald-300" aria-hidden="true" />
                    ¡Gracias por contarnos!
                  </p>
                ) : (
                  <Calificar token={token} problemas={datos.problemas ?? []} onListo={() => void cargar()} />
                )}
              </Tarjeta>
            )}

            <p className="flex items-start justify-center gap-1.5 px-2 pt-1 text-center text-xs text-white/40">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              Sin cuenta ni datos personales. Este enlace deja de funcionar cuando te vas.
            </p>
          </div>
        )}

        {pestana === 'pedir' && (
          <div key="pedir" className="animate-fade-in space-y-3">
            <h2 className="text-center text-sm text-white/70">Te lo llevan a la habitación. Recién ahí se suma a tu cuenta.</h2>
            {rubros.length > 1 && (
              <div className="sin-barra -mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Filtrar por rubro">
                {[null, ...rubros].map((r) => (
                  <button
                    key={r ?? 'todo'}
                    type="button"
                    aria-pressed={rubro === r}
                    onClick={() => setRubro(r)}
                    className={`press shrink-0 rounded-full px-3.5 py-1.5 text-sm ${rubro === r ? 'bg-white font-medium text-slate-900' : 'bg-white/10 text-white/80'}`}
                  >
                    {r ?? 'Todo'}
                  </button>
                ))}
              </div>
            )}
            {articulos.length === 0 ? (
              <Tarjeta>
                <p className="text-center text-sm text-white/60">Ahora no hay nada para pedir.</p>
              </Tarjeta>
            ) : (
              <ul className="grid grid-cols-2 gap-2">
                {visibles.map((a, i) => {
                  const cantidad = elegidos[a.id] ?? 0;
                  const Icono = iconoDe(a.categoria);
                  return (
                    <li key={a.id} className={`flex animate-tarjeta-in flex-col rounded-2xl border p-3 transition ${cantidad ? 'border-white/40 bg-white/10' : 'border-white/10 bg-white/[0.06]'}`} style={{ animationDelay: `${i * 30}ms` }}>
                      <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/10">
                        <Icono className="h-5 w-5 text-white/80" aria-hidden="true" />
                      </span>
                      <p className="mt-2 min-h-[2.5rem] flex-1 text-sm leading-tight">{a.descripcion}</p>
                      <div className="mt-1 flex items-center justify-between gap-1">
                        <span className="text-sm font-semibold tabular-nums">{formatMoney(a.precio)}</span>
                        <span className="flex items-center gap-0.5">
                          {cantidad > 0 && (
                            <>
                              <button type="button" onClick={() => cambiar(a.id, -1)} aria-label={`Quitar ${a.descripcion}`} className="press grid h-9 w-9 place-items-center rounded-full bg-white/10">
                                <Minus className="h-4 w-4" aria-hidden="true" />
                              </button>
                              <span className="w-5 text-center text-sm font-medium tabular-nums">{cantidad}</span>
                            </>
                          )}
                          <button type="button" onClick={() => cambiar(a.id, 1)} disabled={cantidad >= 5} aria-label={`Agregar ${a.descripcion}`} className="press grid h-9 w-9 place-items-center rounded-full bg-white text-slate-900 disabled:opacity-40">
                            <Plus className="h-4 w-4" aria-hidden="true" />
                          </button>
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}

        {pestana === 'mot' && (
          <div key="mot">
            <PestanaMot datos={datos} onAvisar={(tipo) => void avisar({ tipo }, AVISOS[tipo].listo)} />
          </div>
        )}
      </div>

      <div className="fixed inset-x-0 bottom-0 z-20">
        <div className="mx-auto max-w-md space-y-2 px-4 pb-2">
          {mensaje && (
            <p role="status" className={`animate-pop-in rounded-xl px-4 py-2.5 text-center text-sm font-medium ${mensaje.error ? 'bg-rose-500/90' : 'bg-emerald-500/90'}`}>
              {mensaje.texto}
            </p>
          )}
          {unidades > 0 && (
            <button type="button" onClick={() => setHoja('carrito')} className="press flex w-full animate-pop-in items-center justify-between gap-3 rounded-xl bg-white px-4 py-3.5 font-semibold text-slate-900 shadow-panel">
              <span className="flex items-center gap-2">
                <ShoppingBag className="h-4 w-4" aria-hidden="true" />
                Ver pedido ({unidades})
              </span>
              <span className="tabular-nums">{formatMoney(subtotal)}</span>
            </button>
          )}
        </div>
        <nav aria-label="Secciones" className="border-t border-white/10 bg-[#0b1220]/95 backdrop-blur" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
          <div className="mx-auto grid max-w-md grid-cols-3">
            {(
              [
                ['estadia', 'Mi estadía'],
                ['pedir', 'Pedir'],
                ['mot', 'Mot'],
              ] as [Pestana, string][]
            ).map(([id, nombre]) => (
              <button
                key={id}
                type="button"
                aria-current={pestana === id ? 'page' : undefined}
                onClick={() => setPestana(id)}
                className={`press relative flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] ${pestana === id ? 'font-semibold text-white' : 'text-white/55'}`}
              >
                {id === 'estadia' && <Clock className="h-5 w-5" aria-hidden="true" />}
                {id === 'pedir' && <ShoppingBag className="h-5 w-5" aria-hidden="true" />}
                {id === 'mot' && <Mot soloCabeza className="h-5 w-6" />}
                {nombre}
                {id === 'pedir' && unidades > 0 && (
                  <span className="absolute right-[calc(50%-1.4rem)] top-1.5 grid h-4 min-w-4 animate-pop-in place-items-center rounded-full bg-amber-300 px-1 text-[10px] font-bold text-slate-900">
                    {unidades}
                  </span>
                )}
              </button>
            ))}
          </div>
        </nav>
      </div>

      {hoja === 'carrito' && (
        <HojaInferior titulo="Tu pedido" onCerrar={() => setHoja(null)}>
          <ul className="divide-y divide-white/10">
            {seleccion.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm">{a.descripcion}</p>
                  <p className="text-xs tabular-nums text-white/50">{formatMoney(a.precio * elegidos[a.id])}</p>
                </div>
                <span className="flex items-center gap-1">
                  <button type="button" onClick={() => cambiar(a.id, -1)} aria-label={`Quitar ${a.descripcion}`} className="press grid h-9 w-9 place-items-center rounded-full bg-white/10">
                    <Minus className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <span className="w-5 text-center text-sm font-medium tabular-nums">{elegidos[a.id]}</span>
                  <button type="button" onClick={() => cambiar(a.id, 1)} disabled={elegidos[a.id] >= 5} aria-label={`Agregar ${a.descripcion}`} className="press grid h-9 w-9 place-items-center rounded-full bg-white/10 disabled:opacity-40">
                    <Plus className="h-4 w-4" aria-hidden="true" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
          {seleccion.length === 0 && <p className="py-4 text-center text-sm text-white/60">No queda nada en tu pedido.</p>}
          <button
            type="button"
            onClick={() => void pedir()}
            disabled={enviando || seleccion.length === 0}
            className="press mt-3 flex w-full items-center justify-between gap-3 rounded-xl bg-white px-4 py-3.5 font-semibold text-slate-900 disabled:opacity-50"
          >
            <span className="flex items-center gap-2">
              <BellRing className="h-4 w-4" aria-hidden="true" />
              {enviando ? 'Pidiendo…' : 'Pedir a la habitación'}
            </span>
            <span className="tabular-nums">{formatMoney(subtotal)}</span>
          </button>
          <p className="mt-2 text-center text-xs text-white/50">Se suma a tu cuenta cuando te lo entregan.</p>
        </HojaInferior>
      )}

      {hoja === 'tiempo' && (
        <HojaInferior titulo="Quedarme más" onCerrar={() => setHoja(null)}>
          <p className="mb-3 text-sm text-white/70">Elegí cuánto más te quedás. Se cobra por el tiempo real: no hace falta pagar nada ahora.</p>
          <ul className="space-y-2">
            {datos.opciones_tiempo?.map((o) => (
              <li key={o.minutos}>
                <button
                  type="button"
                  disabled={enviando}
                  onClick={() => void avisar({ tipo: 'TIEMPO', minutos: o.minutos }, `Listo: avisamos que te quedás ${o.etiqueta} más.`)}
                  className="press flex w-full items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-left hover:bg-white/10 disabled:opacity-60"
                >
                  <span>
                    <span className="block font-medium">{o.etiqueta} más</span>
                    <span className="text-xs text-white/60">Hasta las {hora(o.hasta)}</span>
                  </span>
                  <span className="text-right font-semibold tabular-nums">{o.suma > 0 ? `+ ${formatMoney(o.suma)}` : 'Sin costo'}</span>
                </button>
              </li>
            ))}
          </ul>
        </HojaInferior>
      )}

      {hoja === 'cuenta' && (
        <HojaInferior titulo="Pedir la cuenta" onCerrar={() => setHoja(null)}>
          <div className="rounded-xl bg-white/5 px-4 py-3 text-center">
            <p className="text-xs text-white/60">Total hasta ahora</p>
            <p className="text-3xl font-semibold tabular-nums">{formatMoney(datos.total ?? 0)}</p>
          </div>
          <p className="mb-2 mt-4 text-sm text-white/70">¿Cómo vas a pagar?</p>
          <div role="radiogroup" aria-label="Cómo vas a pagar" className="grid grid-cols-3 gap-2">
            {datos.medios_pago?.map((m) => {
              const Icono = ICONO_MEDIO[m.medio] ?? Wallet;
              return (
                <button
                  key={m.medio}
                  type="button"
                  role="radio"
                  aria-checked={medio === m.medio}
                  onClick={() => setMedio(m.medio)}
                  className={`press flex flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-xs ${medio === m.medio ? 'border-white bg-white text-slate-900' : 'border-white/15 bg-white/5 text-white/80'}`}
                >
                  <Icono className="h-5 w-5" aria-hidden="true" />
                  {m.etiqueta}
                </button>
              );
            })}
          </div>
          <button
            type="button"
            disabled={enviando}
            onClick={() => void avisar({ tipo: 'SALIDA', medio_pago: medio }, 'Listo: te dejamos la cuenta preparada en la ventanilla.')}
            className="press mt-4 w-full rounded-xl bg-white py-3.5 font-semibold text-slate-900 disabled:opacity-60"
          >
            {enviando ? 'Avisando…' : 'Ya nos vamos'}
          </button>
          <p className="mt-2 text-center text-xs text-white/50">Se paga en la ventanilla, al salir. El total puede cambiar si pasa más tiempo.</p>
        </HojaInferior>
      )}
    </main>
  );
};

export default VistaCliente;
