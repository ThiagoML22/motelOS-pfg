import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BedDouble, BellRing, Check, Clock, DoorOpen, Minus, Phone, Plus, ShieldCheck, X } from 'lucide-react';
import { EstadiaCliente } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDuration, formatMoney, formatRoomNumber } from '../utils/format';
import { aplicarMarca } from '../utils/marca';

const REFRESCO_MS = 15000;

const AVISOS: Record<string, { etiqueta: string; icono: React.ElementType; listo: string }> = {
  TOALLAS: { etiqueta: 'Necesito toallas', icono: BedDouble, listo: 'Ya te las llevan' },
  LLAMAR: { etiqueta: 'Que me llamen', icono: Phone, listo: 'Enseguida te llaman' },
  SALIDA: { etiqueta: 'Ya nos vamos', icono: DoorOpen, listo: 'Avisamos en la ventanilla' },
};

const ESTADO_PEDIDO: Record<string, { etiqueta: string; clase: string }> = {
  Pendiente: { etiqueta: 'En camino', clase: 'bg-amber-300/20 text-amber-200' },
  Atendido: { etiqueta: 'Entregado', clase: 'bg-emerald-300/20 text-emerald-200' },
  Rechazado: { etiqueta: 'No disponible', clase: 'bg-rose-300/20 text-rose-200' },
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

// Lo que ve el cliente con el QR de su ticket, en su celular: sin cuenta y sin datos personales. No es parte de la
// aplicación del personal: no pide sesión y el enlace deja de funcionar cuando se cierra el turno.
const VistaCliente: React.FC<{ token: string }> = ({ token }) => {
  const [datos, setDatos] = useState<EstadiaCliente | null>(null);
  const [invalido, setInvalido] = useState(false);
  const [elegidos, setElegidos] = useState<Record<number, number>>({});
  const [enviando, setEnviando] = useState(false);
  const [mensaje, setMensaje] = useState<{ texto: string; error: boolean } | null>(null);
  const [ahora, setAhora] = useState(Date.now());
  // Diferencia con el reloj del servidor: el del celular puede estar corrido.
  const desfase = useRef(0);

  const cargar = useCallback(async () => {
    try {
      const nuevos = await api.getEstadiaCliente(token);
      if (nuevos.ahora) desfase.current = new Date(nuevos.ahora).getTime() - Date.now();
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

  const seleccion = useMemo(() => (datos?.articulos ?? []).filter((a) => elegidos[a.id]), [datos, elegidos]);
  const subtotal = seleccion.reduce((suma, a) => suma + a.precio * elegidos[a.id], 0);
  const unidades = seleccion.reduce((suma, a) => suma + elegidos[a.id], 0);

  const cambiar = (id: number, cambio: number) =>
    setElegidos((e) => {
      const cantidad = Math.min(Math.max((e[id] ?? 0) + cambio, 0), 5);
      const { [id]: _, ...resto } = e;
      return cantidad ? { ...resto, [id]: cantidad } : resto;
    });

  const pedir = async () => {
    setEnviando(true);
    try {
      for (const articulo of seleccion) {
        await api.pedirCliente(token, { tipo: 'ARTICULO', articulo_id: articulo.id, cantidad: elegidos[articulo.id] });
      }
      setElegidos({});
      setMensaje({ texto: 'Listo: te lo llevan a la habitación.', error: false });
    } catch (err) {
      setMensaje({ texto: getErrorMessage(err, 'No se pudo hacer el pedido.'), error: true });
    } finally {
      setEnviando(false);
      void cargar();
    }
  };

  const avisar = async (tipo: string) => {
    try {
      await api.pedirCliente(token, { tipo });
      setMensaje({ texto: AVISOS[tipo].listo, error: false });
    } catch (err) {
      setMensaje({ texto: getErrorMessage(err, 'No se pudo avisar.'), error: true });
    } finally {
      void cargar();
    }
  };

  const fondo = 'cielo relative min-h-screen overflow-x-hidden px-4 pb-32 pt-6 text-white';

  if (invalido || (datos && !datos.activa)) {
    return (
      <main className={`${fondo} grid place-items-center pb-6 text-center`}>
        <div className="animate-pop-in">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-white/10">
            {invalido ? <X className="h-7 w-7" aria-hidden="true" /> : <Check className="h-7 w-7" aria-hidden="true" />}
          </span>
          <h1 className="mt-4 text-xl font-semibold">{invalido ? 'Este código no es válido' : '¡Gracias por venir!'}</h1>
          <p className="mt-1 text-sm text-white/60">{invalido ? 'Pedí tu ticket en la ventanilla.' : 'Tu estadía terminó y este enlace ya no se usa.'}</p>
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

        <div className="animate-pop-in py-1">
          <Anillo parte={transcurrido / baseMs} excedido={excedido}>
            <p className="font-mono text-4xl font-semibold tabular-nums">{formatDuration(transcurrido)}</p>
            <p className={`mt-1 flex items-center justify-center gap-1 text-sm ${excedido ? 'text-rose-300' : 'text-white/60'}`}>
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              {excedido ? 'Pasaste la estadía base' : `Quedan ${restanMin} min de estadía`}
            </p>
          </Anillo>
        </div>

        <Tarjeta titulo="Tu cuenta">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-white/70">Estadía</dt>
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

        {(datos.pedidos?.length ?? 0) > 0 && (
          <Tarjeta titulo="Tus pedidos" retraso={60}>
            <ul className="space-y-1.5 text-sm">
              {datos.pedidos?.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-white/80">
                    {p.tipo === 'ARTICULO' ? `${p.cantidad} × ${p.descripcion}` : AVISOS[p.tipo]?.etiqueta}
                  </span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${ESTADO_PEDIDO[p.estado]?.clase ?? ''}`}>
                    {ESTADO_PEDIDO[p.estado]?.etiqueta ?? p.estado}
                  </span>
                </li>
              ))}
            </ul>
          </Tarjeta>
        )}

        <Tarjeta titulo="Avisar sin llamar" retraso={120}>
          <div className="grid grid-cols-3 gap-2">
            {Object.entries(AVISOS).map(([tipo, { etiqueta, icono: Icono }]) => (
              <button
                key={tipo}
                type="button"
                onClick={() => void avisar(tipo)}
                className="press flex flex-col items-center gap-1.5 rounded-xl border border-white/10 bg-white/5 px-2 py-3 text-center text-xs text-white/80 hover:bg-white/10"
              >
                <Icono className="h-5 w-5" aria-hidden="true" />
                {etiqueta}
              </button>
            ))}
          </div>
        </Tarjeta>

        {(datos.articulos?.length ?? 0) > 0 && (
          <Tarjeta titulo="Pedir a la habitación" retraso={180}>
            <ul className="divide-y divide-white/10">
              {datos.articulos?.map((a) => {
                const cantidad = elegidos[a.id] ?? 0;
                return (
                  <li key={a.id} className="flex items-center justify-between gap-3 py-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm">{a.descripcion}</p>
                      <p className="text-xs tabular-nums text-white/50">{formatMoney(a.precio)}</p>
                    </div>
                    <div className="flex items-center gap-1">
                      {cantidad > 0 && (
                        <>
                          <button
                            type="button"
                            onClick={() => cambiar(a.id, -1)}
                            aria-label={`Quitar ${a.descripcion}`}
                            className="press grid h-9 w-9 place-items-center rounded-full bg-white/10"
                          >
                            <Minus className="h-4 w-4" aria-hidden="true" />
                          </button>
                          <span className="w-6 text-center text-sm font-medium tabular-nums">{cantidad}</span>
                        </>
                      )}
                      <button
                        type="button"
                        onClick={() => cambiar(a.id, 1)}
                        disabled={cantidad >= 5}
                        aria-label={`Agregar ${a.descripcion}`}
                        className="press grid h-9 w-9 place-items-center rounded-full bg-white/15 disabled:opacity-40"
                      >
                        <Plus className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Tarjeta>
        )}

        <p className="flex items-start justify-center gap-1.5 px-2 pt-1 text-center text-xs text-white/40">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Sin cuenta ni datos personales. Este enlace deja de funcionar cuando te vas.
        </p>
      </div>

      {(unidades > 0 || mensaje) && (
        <div className="fixed inset-x-0 bottom-0 z-20 mx-auto max-w-md space-y-2 p-4">
          {mensaje && (
            <p role="status" className={`animate-pop-in rounded-xl px-4 py-2.5 text-center text-sm font-medium ${mensaje.error ? 'bg-rose-500/90' : 'bg-emerald-500/90'}`}>
              {mensaje.texto}
            </p>
          )}
          {unidades > 0 && (
            <button
              type="button"
              onClick={() => void pedir()}
              disabled={enviando}
              className="press flex w-full animate-pop-in items-center justify-between gap-3 rounded-xl bg-white px-4 py-3.5 font-semibold text-slate-900 shadow-panel disabled:opacity-60"
            >
              <span className="flex items-center gap-2">
                <BellRing className="h-4 w-4" aria-hidden="true" />
                {enviando ? 'Pidiendo…' : `Pedir ${unidades}`}
              </span>
              <span className="tabular-nums">{formatMoney(subtotal)}</span>
            </button>
          )}
        </div>
      )}
    </main>
  );
};

export default VistaCliente;
