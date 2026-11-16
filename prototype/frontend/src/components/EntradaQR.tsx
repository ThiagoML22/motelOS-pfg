import React, { useEffect, useMemo, useState } from 'react';
import { BellRing, Check, Cookie, CupSoda, Heart, type LucideIcon, Package, RotateCw, ShieldCheck, X } from 'lucide-react';
import { EntradaQR as Entrada } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatMoney, formatRoomNumber } from '../utils/format';
import { aplicarMarca } from '../utils/marca';
import Mot from './Mot';
import VistaCliente from './VistaCliente';

const ICONO_CATEGORIA: Record<string, LucideIcon> = { bebidas: CupSoda, snacks: Cookie, 'cuidado personal': Heart };
const iconoDe = (categoria: string | null): LucideIcon => ICONO_CATEGORIA[(categoria ?? '').toLowerCase()] ?? Package;

const FONDO = 'cielo relative min-h-screen overflow-x-hidden px-4 pb-10 pt-6 text-white';

type Carta = Extract<Entrada, { estado: 'libre' }>;

// Lo que ve quien escanea el QR fijo sin estar vinculado: la carta, igual con la habitación libre u ocupada (no dice
// si hay alguien). Si está en la habitación y no ve su estadía, avisa a la ventanilla sin hablar con nadie.
const CartaHabitacion: React.FC<{ carta: Carta; qr: string }> = ({ carta, qr }) => {
  const [aviso, setAviso] = useState<'nada' | 'enviando' | 'listo'>('nada');
  const [error, setError] = useState<string | null>(null);
  const rubros = useMemo(() => {
    const grupos = new Map<string, Carta['articulos']>();
    for (const a of carta.articulos) {
      const rubro = a.categoria ?? 'Otros';
      grupos.set(rubro, [...(grupos.get(rubro) ?? []), a]);
    }
    return [...grupos.entries()];
  }, [carta.articulos]);

  const avisar = async () => {
    setAviso('enviando');
    setError(null);
    try {
      await api.avisarSinEstadia(qr);
      setAviso('listo');
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo avisar. Probá de nuevo.'));
      setAviso('nada');
    }
  };

  return (
    <main className={FONDO}>
      <div className="mx-auto max-w-md space-y-3">
        <header className="animate-fade-in text-center">
          <p className="text-xs uppercase tracking-[0.2em] text-white/50">{carta.motel}</p>
          <h1 className="mt-1 text-lg font-semibold">
            {formatRoomNumber(carta.numero)}
            {carta.categoria && <span className="font-normal text-white/60"> · {carta.categoria}</span>}
          </h1>
        </header>

        <div className="flex animate-fade-in flex-col items-center pt-1">
          <p className="max-w-xs animate-pop-in rounded-2xl bg-white/10 px-4 py-3 text-center text-sm leading-relaxed">
            {carta.bienvenida ?? '¡Hola! Soy Mot. Con este código ves tu tiempo y tu cuenta, y pedís sin llamar.'}
          </p>
          <Mot estado="saludando" className="mt-3 h-28 w-24" />
        </div>

        {rubros.length > 0 && (
          <section className="animate-tarjeta-in rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur">
            <h2 className="mb-2 text-xs font-medium uppercase tracking-wider text-white/50">La carta</h2>
            <div className="space-y-3">
              {rubros.map(([rubro, articulos]) => {
                const Icono = iconoDe(rubro);
                return (
                  <div key={rubro}>
                    <h3 className="mb-1 flex items-center gap-1.5 text-sm font-medium text-white/80">
                      <Icono className="h-4 w-4" aria-hidden="true" />
                      {rubro}
                    </h3>
                    <ul className="space-y-1 text-sm">
                      {articulos.map((a) => (
                        <li key={a.descripcion} className="flex justify-between gap-3">
                          <span className="text-white/70">{a.descripcion}</span>
                          <span className="tabular-nums">{formatMoney(a.precio)}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        <section className="animate-tarjeta-in rounded-2xl border border-white/10 bg-white/[0.06] p-4 text-center backdrop-blur" style={{ animationDelay: '60ms' }}>
          {aviso === 'listo' ? (
            <div className="animate-pop-in" role="status">
              <p className="flex items-center justify-center gap-2 text-sm font-medium">
                <Check className="h-4 w-4 text-emerald-300" aria-hidden="true" />
                Listo, avisamos a la ventanilla.
              </p>
              <p className="mt-1 text-xs text-white/60">En un momento volvé a escanear el código.</p>
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="press mt-3 inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-slate-900"
              >
                <RotateCw className="h-4 w-4" aria-hidden="true" />
                Escanear de nuevo
              </button>
            </div>
          ) : (
            <>
              <p className="text-sm text-white/80">¿Estás en esta habitación y no ves tu estadía?</p>
              <button
                type="button"
                disabled={aviso === 'enviando'}
                onClick={() => void avisar()}
                className="press mt-2 inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-2.5 text-sm font-medium disabled:opacity-60"
              >
                <BellRing className="h-4 w-4" aria-hidden="true" />
                {aviso === 'enviando' ? 'Avisando…' : 'Avisar a la ventanilla'}
              </button>
              {error && <p className="mt-2 text-xs text-rose-300">{error}</p>}
              <p className="mt-2 text-[11px] text-white/40">Sin llamar ni hablar con nadie.</p>
            </>
          )}
        </section>

        <p className="flex items-start justify-center gap-1.5 px-2 pt-1 text-center text-xs text-white/40">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          Sin cuenta ni datos personales.
        </p>
      </div>
    </main>
  );
};

// Una sola petición por carga de página: dos a la vez llegarían sin cookie y el celular podría quedar con la marca
// equivocada (React, en desarrollo, monta dos veces).
const enCurso = new Map<string, Promise<Entrada>>();
const unaVez = (clave: string, pedir: () => Promise<Entrada>): Promise<Entrada> => {
  if (!enCurso.has(clave)) enCurso.set(clave, pedir());
  return enCurso.get(clave)!;
};

// El QR fijo de la habitación (?habitacion=) o el QR para sumar otro celular (?sumar=), migración 020. Si el celular
// queda vinculado, la página pasa a ser la de su estadía (?cliente=): recargarla no vuelve a pasar por el QR.
const EntradaQR: React.FC<{ qr?: string; invitacion?: string }> = ({ qr, invitacion }) => {
  const [entrada, setEntrada] = useState<Entrada | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = 'dark';
    document.title = 'Tu estadía';
    let vigente = true;
    unaVez(qr ? `qr:${qr}` : `sumar:${invitacion}`, () => (qr ? api.entrarConQR(qr) : api.sumarCelular(invitacion ?? '')))
      .then((datos) => {
        if (!vigente) return;
        if (datos.estado === 'libre') aplicarMarca(datos.color_marca);
        else window.history.replaceState(null, '', `?cliente=${encodeURIComponent(datos.token)}`);
        setEntrada(datos);
      })
      .catch((err) => {
        if (vigente) setError(getErrorMessage(err, 'No se pudo abrir. Probá de nuevo.'));
      });
    return () => {
      vigente = false;
    };
  }, [qr, invitacion]);

  if (entrada && entrada.estado !== 'libre') return <VistaCliente token={entrada.token} />;
  if (entrada && qr) return <CartaHabitacion carta={entrada} qr={qr} />;
  if (error) {
    return (
      <main className={`${FONDO} grid place-items-center text-center`}>
        <div className="w-full max-w-sm animate-pop-in">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-white/10">
            <X className="h-7 w-7" aria-hidden="true" />
          </span>
          <h1 className="mt-4 text-xl font-semibold">{invitacion ? 'No te pudimos sumar' : 'Este código no es válido'}</h1>
          <p className="mt-1 text-sm text-white/60">{error}</p>
        </div>
      </main>
    );
  }
  return (
    <main className={`${FONDO} grid place-items-center`}>
      <p className="animate-pulse text-sm text-white/60">Abriendo tu estadía…</p>
    </main>
  );
};

export default EntradaQR;
