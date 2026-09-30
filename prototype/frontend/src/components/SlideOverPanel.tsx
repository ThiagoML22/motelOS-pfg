import React, { useCallback, useEffect, useState } from 'react';
import { Banknote, Bike, Car, CreditCard, Footprints, Minus, Plus, Receipt } from 'lucide-react';
import { Articulo, HabitacionConDetalles, MedioPago, TipoCliente, TurnoResumen } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDuration, formatMoney, formatRoomNumber } from '../utils/format';
import { ESTADIA_BASE_MIN, TOLERANCIA_MIN, elapsedMinutes, elapsedMs, faseEstadia } from '../utils/turno';
import Button from './ui/Button';
import Drawer from './ui/Drawer';
import Field, { inputClass } from './ui/Field';
import { FASE_META } from './ui/status';
import { useToast } from './ui/Toast';

interface SlideOverPanelProps {
  room: HabitacionConDetalles;
  now: number;
  onClose: () => void;
  onAperturaTurno: (patente: string | undefined, tipoCliente: TipoCliente) => Promise<void>;
  onRefreshRooms: () => Promise<void>;
  initialAddProduct?: boolean;
}

type Vista = 'cuenta' | 'productos' | 'cobro';

const TIPOS: { value: TipoCliente; label: string; icon: React.ElementType }[] = [
  { value: 'Auto', label: 'Auto', icon: Car },
  { value: 'Moto', label: 'Moto', icon: Bike },
  { value: 'Peaton', label: 'Peatón', icon: Footprints },
];

const MEDIOS: { value: MedioPago; label: string; icon: React.ElementType }[] = [
  { value: 'EFECTIVO', label: 'Efectivo', icon: Banknote },
  { value: 'POSNET', label: 'Posnet', icon: CreditCard },
  { value: 'MERCADO_PAGO', label: 'Mercado Pago', icon: Receipt },
];

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">{children}</h3>
);

const SlideOverPanel: React.FC<SlideOverPanelProps> = ({
  room,
  now,
  onClose,
  onAperturaTurno,
  onRefreshRooms,
  initialAddProduct = false,
}) => {
  const { toast } = useToast();
  const turnoId = room.turno_activo?.id;
  const isOcupada = room.estado === 'Ocupada';

  const [patente, setPatente] = useState('');
  const [tipoCliente, setTipoCliente] = useState<TipoCliente>('Auto');

  const [vista, setVista] = useState<Vista>(initialAddProduct ? 'productos' : 'cuenta');
  const [resumen, setResumen] = useState<TurnoResumen | null>(null);
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [cargando, setCargando] = useState(false);

  const [medioPago, setMedioPago] = useState<MedioPago>('EFECTIVO');
  const [comprobante, setComprobante] = useState('');
  const [errorComprobante, setErrorComprobante] = useState('');
  const [enviando, setEnviando] = useState(false);

  const loadData = useCallback(
    async (id: string) => {
      try {
        const [res, arts] = await Promise.all([api.getResumen(id), api.getArticulos()]);
        setResumen(res);
        setArticulos(arts);
      } catch (e) {
        toast(getErrorMessage(e, 'No se pudo cargar la cuenta del turno.'), 'error');
      }
    },
    [toast],
  );

  useEffect(() => {
    if (!isOcupada || !turnoId) return;
    setCargando(true);
    void loadData(turnoId).finally(() => setCargando(false));
  }, [isOcupada, turnoId, loadData]);

  const changeQty = (art: Articulo, delta: number) => {
    const next = (quantities[art.id] ?? 0) + delta;
    if (next >= 0 && next <= art.stock_actual) setQuantities({ ...quantities, [art.id]: next });
  };

  const seleccion = articulos.filter((a) => (quantities[a.id] ?? 0) > 0);
  const subtotalSeleccion = seleccion.reduce((sum, a) => sum + a.precio_unitario * (quantities[a.id] ?? 0), 0);

  const guardarConsumos = async () => {
    if (!resumen || seleccion.length === 0) return;
    setEnviando(true);
    try {
      for (const art of seleccion) {
        await api.addConsumo(resumen.id, art.id, quantities[art.id]);
      }
      toast('Productos agregados a la cuenta.', 'success');
      setQuantities({});
      await onRefreshRooms();
      if (initialAddProduct) {
        onClose();
      } else {
        setVista('cuenta');
        await loadData(resumen.id);
      }
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudieron agregar los productos.'), 'error');
      await loadData(resumen.id);
    } finally {
      setEnviando(false);
    }
  };

  const cobrar = async () => {
    if (!resumen) return;
    if (medioPago !== 'EFECTIVO' && !comprobante.trim()) {
      setErrorComprobante('Ingrese el número de comprobante.');
      return;
    }
    setEnviando(true);
    try {
      // El total crece con el tiempo: se vuelve a consultar antes de cobrar para no liquidar un monto viejo.
      const actual = await api.getResumen(resumen.id);
      if (actual.total_general !== resumen.total_general) {
        setResumen(actual);
        toast(`El total cambió a ${formatMoney(actual.total_general)}. Revise el monto y confirme nuevamente.`, 'info');
        return;
      }
      await api.cerrarTurno(resumen.id, actual.total_general, medioPago, comprobante.trim());
      toast(`Cobro de ${formatMoney(actual.total_general)} registrado. ${formatRoomNumber(room.numero)} pasa a limpieza.`, 'success');
      await onRefreshRooms();
      onClose();
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo registrar el cobro.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  const accionSimple = async (accion: () => Promise<unknown>, ok: string, fallo: string) => {
    setEnviando(true);
    try {
      await accion();
      toast(ok, 'success');
      await onRefreshRooms();
      onClose();
    } catch (e) {
      toast(getErrorMessage(e, fallo), 'error');
    } finally {
      setEnviando(false);
    }
  };

  const titulo = formatRoomNumber(room.numero);
  let subtitulo = 'Apertura de turno';
  if (isOcupada) subtitulo = vista === 'productos' ? 'Agregar productos' : vista === 'cobro' ? 'Cobro y cierre' : 'Cuenta del turno';
  if (room.estado === 'En Limpieza') subtitulo = 'En limpieza';
  if (room.estado === 'Mantenimiento') subtitulo = 'En mantenimiento';

  let body: React.ReactNode = null;
  let footer: React.ReactNode = null;

  if (room.estado === 'Libre') {
    body = (
      <form
        id="form-apertura"
        onSubmit={(e) => {
          e.preventDefault();
          void onAperturaTurno(tipoCliente === 'Peaton' ? undefined : patente.trim() || undefined, tipoCliente);
        }}
        className="space-y-6"
      >
        <div>
          <SectionTitle>Tipo de cliente</SectionTitle>
          <div role="radiogroup" aria-label="Tipo de cliente" className="grid grid-cols-3 gap-2">
            {TIPOS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={tipoCliente === value}
                onClick={() => setTipoCliente(value)}
                className={`flex flex-col items-center gap-1.5 rounded-md border px-3 py-3 text-sm transition-colors ${
                  tipoCliente === value
                    ? 'border-accent bg-accent-soft font-medium text-accent'
                    : 'border-line-strong bg-surface text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
        </div>

        {tipoCliente !== 'Peaton' && (
          <Field
            label="Identificación vehicular (opcional)"
            htmlFor="patente"
            hint="No se registran datos personales del cliente."
          >
            <input
              id="patente"
              data-autofocus
              type="text"
              maxLength={12}
              autoComplete="off"
              placeholder="AB 123 CD"
              className={`${inputClass} font-mono uppercase`}
              value={patente}
              onChange={(e) => setPatente(e.target.value.toUpperCase())}
            />
          </Field>
        )}

        <p className="rounded-md bg-surface-2 px-3 py-2.5 text-sm text-muted">
          Estadía base de {ESTADIA_BASE_MIN / 60} horas, con {TOLERANCIA_MIN} minutos de tolerancia. Luego se liquida por
          fracciones.
        </p>
      </form>
    );
    footer = (
      <Button type="submit" form="form-apertura" className="w-full">
        Ocupar habitación
      </Button>
    );
  } else if (room.estado === 'En Limpieza') {
    body = (
      <p className="text-sm text-muted">
        La habitación está pendiente de limpieza. Al marcarla como disponible volverá a estar lista para ocupar.
      </p>
    );
    footer = (
      <Button
        className="w-full"
        disabled={enviando}
        onClick={() =>
          void accionSimple(
            () => api.liberarHabitacion(room.id),
            `${titulo} disponible.`,
            'No se pudo liberar la habitación.',
          )
        }
      >
        Marcar como disponible
      </Button>
    );
  } else if (room.estado === 'Mantenimiento') {
    body = (
      <p className="text-sm text-muted">
        La habitación está fuera de servicio. Al habilitarla volverá a estar disponible para ocupar.
      </p>
    );
    footer = (
      <Button
        className="w-full"
        disabled={enviando}
        onClick={() =>
          void accionSimple(
            () => api.updateHabitacionEstado(room.id, 'Libre'),
            `${titulo} habilitada.`,
            'No se pudo habilitar la habitación.',
          )
        }
      >
        Habilitar habitación
      </Button>
    );
  } else if (!resumen) {
    body = <p className="text-sm text-muted">{cargando ? 'Cargando cuenta…' : 'No se pudo cargar la cuenta.'}</p>;
  } else if (vista === 'cuenta') {
    const minutos = elapsedMinutes(resumen, now);
    const fase = faseEstadia(minutos);
    const nombreArticulo = (id: number) => articulos.find((a) => a.id === id)?.descripcion ?? 'Producto';

    body = (
      <div className="space-y-6">
        <div className="flex items-baseline justify-between rounded-md bg-surface-2 px-4 py-3">
          <span className="text-sm text-muted">Tiempo transcurrido</span>
          <span className="text-right">
            <span className={`font-mono text-lg font-semibold tabular-nums ${FASE_META[fase].text}`}>
              {formatDuration(elapsedMs(resumen, now))}
            </span>
            {fase === 'tolerancia' && <span className="block text-xs font-medium text-warn">En tolerancia</span>}
            {fase === 'excedido' && (
              <span className="block text-xs font-medium text-danger">Excedido +{minutos - ESTADIA_BASE_MIN} min</span>
            )}
          </span>
        </div>

        <div>
          <SectionTitle>Detalle</SectionTitle>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-line">
              <tr>
                <td className="py-2 text-muted">Estadía base ({ESTADIA_BASE_MIN / 60} h)</td>
                <td className="py-2 text-right tabular-nums text-ink">{formatMoney(resumen.tarifa_base)}</td>
              </tr>
              <tr>
                <td className="py-2 text-muted">Sobreturno</td>
                <td className="py-2 text-right tabular-nums text-ink">{formatMoney(resumen.total_sobreturno)}</td>
              </tr>
              {resumen.consumos.map((c) => (
                <tr key={c.id}>
                  <td className="py-2 text-muted">
                    {nombreArticulo(c.articulo_id)} <span className="text-subtle">× {c.cantidad}</span>
                  </td>
                  <td className="py-2 text-right tabular-nums text-ink">{formatMoney(c.subtotal)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {resumen.consumos.length === 0 && <p className="mt-2 text-xs text-subtle">Sin consumos registrados.</p>}
        </div>

        <div className="flex items-baseline justify-between border-t border-line-strong pt-4">
          <span className="text-sm font-medium text-ink">Total a cobrar</span>
          <span className="text-2xl font-semibold tabular-nums text-ink">{formatMoney(resumen.total_general)}</span>
        </div>
      </div>
    );
    footer = (
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={() => setVista('productos')}>
          Agregar productos
        </Button>
        <Button className="flex-1" onClick={() => setVista('cobro')}>
          Cobrar
        </Button>
      </div>
    );
  } else if (vista === 'productos') {
    body =
      articulos.length === 0 ? (
        <p className="text-sm text-muted">No hay artículos cargados en el inventario.</p>
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line">
          {articulos.map((art) => {
            const qty = quantities[art.id] ?? 0;
            const sinStock = art.stock_actual === 0;
            return (
              <li key={art.id} className="flex items-center justify-between gap-3 px-3 py-2.5">
                <div className="min-w-0">
                  <p className={`truncate text-sm font-medium ${sinStock ? 'text-subtle' : 'text-ink'}`}>
                    {art.descripcion}
                  </p>
                  <p className="text-xs text-muted">
                    {formatMoney(art.precio_unitario)} ·{' '}
                    {sinStock ? <span className="text-danger">Sin stock</span> : `Stock ${art.stock_actual}`}
                  </p>
                </div>
                <div className="flex items-center rounded-md border border-line-strong">
                  <button
                    type="button"
                    aria-label={`Quitar una unidad de ${art.descripcion}`}
                    disabled={qty === 0}
                    onClick={() => changeQty(art, -1)}
                    className="p-2 text-muted hover:text-ink disabled:opacity-40"
                  >
                    <Minus className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                  <span className="w-8 text-center text-sm font-medium tabular-nums" aria-live="polite">
                    {qty}
                  </span>
                  <button
                    type="button"
                    aria-label={`Agregar una unidad de ${art.descripcion}`}
                    disabled={qty >= art.stock_actual}
                    onClick={() => changeQty(art, 1)}
                    className="p-2 text-muted hover:text-ink disabled:opacity-40"
                  >
                    <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      );
    footer = (
      <div className="space-y-3">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-muted">Subtotal seleccionado</span>
          <span className="font-semibold tabular-nums text-ink">{formatMoney(subtotalSeleccion)}</span>
        </div>
        <div className="flex gap-3">
          <Button
            variant="secondary"
            className="flex-1"
            onClick={() => {
              if (initialAddProduct) {
                onClose();
              } else {
                setQuantities({});
                setVista('cuenta');
              }
            }}
          >
            {initialAddProduct ? 'Cancelar' : 'Volver'}
          </Button>
          <Button className="flex-1" disabled={seleccion.length === 0 || enviando} onClick={() => void guardarConsumos()}>
            Guardar en la cuenta
          </Button>
        </div>
      </div>
    );
  } else {
    body = (
      <div className="space-y-6">
        <div className="rounded-md border border-line bg-surface-2 px-4 py-4">
          <p className="text-xs font-medium uppercase tracking-wide text-subtle">Total a cobrar</p>
          <p className="mt-1 text-3xl font-semibold tabular-nums text-ink">{formatMoney(resumen.total_general)}</p>
        </div>

        <div>
          <SectionTitle>Medio de pago</SectionTitle>
          <div role="radiogroup" aria-label="Medio de pago" className="grid grid-cols-3 gap-2">
            {MEDIOS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={medioPago === value}
                onClick={() => {
                  setMedioPago(value);
                  setErrorComprobante('');
                }}
                className={`flex flex-col items-center gap-1.5 rounded-md border px-2 py-3 text-center text-sm transition-colors ${
                  medioPago === value
                    ? 'border-accent bg-accent-soft font-medium text-accent'
                    : 'border-line-strong bg-surface text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
        </div>

        {medioPago !== 'EFECTIVO' && (
          <Field label="Nº de comprobante / lote" htmlFor="comprobante" error={errorComprobante}>
            <input
              id="comprobante"
              data-autofocus
              type="text"
              inputMode="numeric"
              autoComplete="off"
              placeholder="000123456"
              className={`${inputClass} font-mono`}
              value={comprobante}
              onChange={(e) => {
                setComprobante(e.target.value);
                setErrorComprobante('');
              }}
            />
          </Field>
        )}
      </div>
    );
    footer = (
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" disabled={enviando} onClick={() => setVista('cuenta')}>
          Volver
        </Button>
        <Button className="flex-[2]" disabled={enviando} onClick={() => void cobrar()}>
          Confirmar cobro de {formatMoney(resumen.total_general)}
        </Button>
      </div>
    );
  }

  return (
    <Drawer title={titulo} subtitle={subtitulo} onClose={onClose} footer={footer}>
      {body}
    </Drawer>
  );
};

export default SlideOverPanel;
