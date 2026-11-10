import React, { useCallback, useEffect, useState } from 'react';
import { Minus, PackageCheck, Plus, Shirt, ShoppingBag, Trash2, Truck } from 'lucide-react';
import { MovimientoRopaHecho, Prenda, TipoMovimientoRopa } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import { PRENDAS } from './RecuentoRopa';
import Button from './ui/Button';
import { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

const TIPOS: { value: TipoMovimientoRopa; label: string; detalle: string; signo: 1 | -1; icon: React.ElementType }[] = [
  { value: 'LAVANDERIA_SALE', label: 'Sale a la lavandería', detalle: 'Se la llevan a lavar', signo: -1, icon: Truck },
  { value: 'LAVANDERIA_VUELVE', label: 'Vuelve de la lavandería', detalle: 'La traen lavada', signo: 1, icon: PackageCheck },
  { value: 'COMPRA', label: 'Compra', detalle: 'Entra ropa nueva', signo: 1, icon: ShoppingBag },
  { value: 'BAJA', label: 'Baja por rotura', detalle: 'Se descarta', signo: -1, icon: Trash2 },
];

const RAPIDAS = [5, 10, 20];

const claseOpcion = (elegida: boolean): string =>
  `press rounded-md border text-left text-sm ${
    elegida ? 'border-accent bg-accent-soft text-accent' : 'border-line-strong bg-surface text-ink hover:border-accent/50'
  }`;

const Titulo: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">{children}</h3>
);

export const FilaMovimiento: React.FC<{ movimiento: MovimientoRopaHecho; conQuien?: boolean }> = ({ movimiento: m, conQuien }) => (
  <li className="flex flex-wrap items-baseline justify-between gap-x-4 py-2 text-sm">
    <span className="text-ink">
      <span className={`inline-block w-10 font-semibold tabular-nums ${m.signo > 0 ? 'text-libre' : 'text-ink'}`}>
        {m.signo > 0 ? '+' : '−'}
        {m.cantidad}
      </span>
      {m.prenda.toLowerCase()}
      <span className="text-muted">
        {' '}
        · {m.tipo}
        {conQuien ? ` · ${m.operador}` : ''}
      </span>
    </span>
    <span className="text-xs text-muted">{formatDateTime(m.creado_en)}</span>
  </li>
);

// La ropa que entra o sale del motel se anota: así en el próximo recuento no aparece como faltante.
const MovimientoRopa: React.FC = () => {
  const { toast } = useToast();
  const [abierto, setAbierto] = useState(false);
  const [prenda, setPrenda] = useState<Prenda>('TOALLAS');
  const [tipo, setTipo] = useState<TipoMovimientoRopa>('LAVANDERIA_SALE');
  const [cantidad, setCantidad] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [anotados, setAnotados] = useState<MovimientoRopaHecho[] | null>(null);
  const valor = /^\d{1,6}$/.test(cantidad) ? parseInt(cantidad, 10) : 0;
  const elegido = TIPOS.find((t) => t.value === tipo) ?? TIPOS[0];
  const nombre = (PRENDAS.find((p) => p.prenda === prenda)?.label ?? '').toLowerCase();

  const cargar = useCallback(async () => {
    try {
      setAnotados(await api.getMovimientosRopa());
    } catch {
      setAnotados([]);
    }
  }, []);

  useEffect(() => {
    if (abierto) void cargar();
  }, [abierto, cargar]);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (valor < 1) return;
    setEnviando(true);
    try {
      await api.movimientoRopa({ prenda, tipo, cantidad: valor });
      toast(`Anotado: ${elegido.signo > 0 ? '+' : '−'}${valor} ${nombre}.`, 'success');
      // La lavandería suele llevarse toallas y sábanas juntas: el diálogo queda abierto para anotar lo que sigue.
      setCantidad('');
      await cargar();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo registrar el movimiento.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <>
      <Button variant="secondary" onClick={() => setAbierto(true)}>
        <Shirt className="h-4 w-4" aria-hidden="true" />
        Movimiento de ropa
      </Button>
      {abierto && (
        <Modal
          title="Movimiento de ropa"
          subtitle="Anote lo que entra o sale del motel: así no figura como faltante en el recuento."
          onClose={() => !enviando && setAbierto(false)}
          footer={
            <div className="flex justify-end gap-3">
              <Button variant="secondary" disabled={enviando} onClick={() => setAbierto(false)}>
                Cerrar
              </Button>
              <Button type="submit" form="form-movimiento-ropa" disabled={enviando || valor < 1}>
                {valor > 0 ? `Anotar ${elegido.signo > 0 ? '+' : '−'}${valor} ${nombre}` : 'Anotar'}
              </Button>
            </div>
          }
        >
          <form id="form-movimiento-ropa" onSubmit={(e) => void enviar(e)} className="space-y-5">
            <div>
              <Titulo>Qué pasó</Titulo>
              <div role="radiogroup" aria-label="Qué pasó" className="grid grid-cols-2 gap-2">
                {TIPOS.map(({ value, label, detalle, signo, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={tipo === value}
                    onClick={() => setTipo(value)}
                    className={`${claseOpcion(tipo === value)} flex items-start gap-2.5 px-3 py-2.5`}
                  >
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="min-w-0">
                      <span className="block font-medium leading-tight">{label}</span>
                      <span className="mt-0.5 block text-xs text-muted">
                        {detalle} · {signo > 0 ? 'suma' : 'resta'}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <Titulo>De qué</Titulo>
                <div role="radiogroup" aria-label="De qué" className="grid grid-cols-2 gap-2">
                  {PRENDAS.map(({ prenda: valorPrenda, label, icon: Icon }) => (
                    <button
                      key={valorPrenda}
                      type="button"
                      role="radio"
                      aria-checked={prenda === valorPrenda}
                      onClick={() => setPrenda(valorPrenda)}
                      className={`${claseOpcion(prenda === valorPrenda)} flex h-11 items-center justify-center gap-2 px-2 font-medium`}
                    >
                      <Icon className="h-4 w-4" aria-hidden="true" />
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <Titulo>Cuántas</Titulo>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-label="Una menos"
                    disabled={valor < 1}
                    onClick={() => setCantidad(String(Math.max(valor - 1, 0) || ''))}
                    className="press hit flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-line-strong text-muted hover:text-ink disabled:opacity-40"
                  >
                    <Minus className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <input
                    id="cantidad-movimiento"
                    aria-label="Cantidad"
                    data-autofocus
                    inputMode="numeric"
                    autoComplete="off"
                    placeholder="0"
                    className={`${inputClass} h-11 min-w-0 flex-1 px-2 text-center text-lg font-semibold tabular-nums`}
                    value={cantidad}
                    onChange={(e) => setCantidad(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  />
                  <button
                    type="button"
                    aria-label="Una más"
                    onClick={() => setCantidad(String(valor + 1))}
                    className="press hit flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-line-strong text-muted hover:text-ink"
                  >
                    <Plus className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
                <div className="mt-2 flex gap-1.5">
                  {RAPIDAS.map((n) => (
                    <button
                      key={n}
                      type="button"
                      onClick={() => setCantidad(String(n))}
                      className="press rounded-full border border-line px-2.5 py-0.5 text-xs tabular-nums text-muted hover:border-line-strong hover:text-ink"
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {valor > 0 && (
              <p role="status" className="rounded-md bg-surface-2 px-3 py-2 text-sm text-ink">
                {elegido.signo > 0 ? 'Entran' : 'Salen'} {valor} {nombre}: el próximo recuento debería dar {valor}{' '}
                {elegido.signo > 0 ? 'más' : 'menos'}.
              </p>
            )}
          </form>

          <div className="mt-6 border-t border-line pt-4">
            <Titulo>Anotado en esta guardia</Titulo>
            {anotados === null ? (
              <p className="text-sm text-muted">Cargando…</p>
            ) : anotados.length === 0 ? (
              <p className="text-sm text-muted">Todavía no anotó nada en esta guardia.</p>
            ) : (
              <ul className="divide-y divide-line">
                {anotados.map((m) => (
                  <FilaMovimiento key={m.id} movimiento={m} />
                ))}
              </ul>
            )}
          </div>
        </Modal>
      )}
    </>
  );
};

export default MovimientoRopa;
