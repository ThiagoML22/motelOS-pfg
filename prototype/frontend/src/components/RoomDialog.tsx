import React, { useCallback, useEffect, useState } from 'react';
import { Banknote, Bike, Car, CreditCard, Footprints, Minus, Plus, Printer, Receipt } from 'lucide-react';
import {
  Articulo,
  ConstanciaCobro,
  HabitacionConDetalles,
  MedioPago,
  PagoItem,
  TipoCliente,
  TurnoResumen,
} from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatDuration, formatMoney, formatRoomNumber } from '../utils/format';
import { ESTADIA_BASE_MIN, elapsedMs, faseEstadia, minutosExcedidos } from '../utils/turno';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { FASE_META } from './ui/status';
import { useToast } from './ui/Toast';

interface RoomDialogProps {
  room: HabitacionConDetalles;
  now: number;
  onClose: () => void;
  onAperturaTurno: (patente: string | undefined, tipoCliente: TipoCliente) => Promise<void>;
  onRefreshRooms: () => Promise<void>;
  initialAddProduct?: boolean;
}

type Vista = 'cuenta' | 'productos' | 'cobro' | 'constancia';
type Montos = Record<MedioPago, string>;

const TIPOS: { value: TipoCliente; label: string; icon: React.ElementType }[] = [
  { value: 'Auto', label: 'Auto', icon: Car },
  { value: 'Moto', label: 'Moto', icon: Bike },
  { value: 'Peaton', label: 'Peatón', icon: Footprints },
];

const MEDIOS: { value: MedioPago; label: string; comprobante: string; icon: React.ElementType }[] = [
  { value: 'EFECTIVO', label: 'Efectivo', comprobante: '', icon: Banknote },
  { value: 'POSNET', label: 'Posnet', comprobante: 'Nº de cupón POSNET', icon: CreditCard },
  { value: 'MERCADO_PAGO', label: 'Mercado Pago', comprobante: 'Nº de comprobante', icon: Receipt },
];

const VACIO: Montos = { EFECTIVO: '', POSNET: '', MERCADO_PAGO: '' };

const aCentavos = (valor: string): number => Math.round((parseFloat(valor.replace(',', '.')) || 0) * 100);

const etiquetaMedio = (medio: string): string => MEDIOS.find((m) => m.value === medio)?.label ?? medio;

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">{children}</h3>
);

const RoomDialog: React.FC<RoomDialogProps> = ({
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
  const [avisoSaldo, setAvisoSaldo] = useState('');

  const [montos, setMontos] = useState<Montos>(VACIO);
  const [comprobantes, setComprobantes] = useState<Montos>(VACIO);
  const [errorCobro, setErrorCobro] = useState('');
  const [dividir, setDividir] = useState(false);
  const [medioUnico, setMedioUnico] = useState<MedioPago>('EFECTIVO');
  const [comprobanteUnico, setComprobanteUnico] = useState('');
  const [constancia, setConstancia] = useState<ConstanciaCobro | null>(null);
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

  // Saldo del turno en centavos, y lo ya asignado en el desglose de cobro.
  const saldoCent = resumen ? Math.round(resumen.saldo_pendiente * 100) : 0;
  const asignadoCent = MEDIOS.reduce((sum, m) => sum + aCentavos(montos[m.value]), 0);
  const restanteCent = saldoCent - asignadoCent;

  const completarCon = (medio: MedioPago) => {
    const otros = MEDIOS.filter((m) => m.value !== medio).reduce((sum, m) => sum + aCentavos(montos[m.value]), 0);
    const resto = Math.max(0, saldoCent - otros);
    setMontos({ ...montos, [medio]: resto > 0 ? (resto / 100).toString() : '' });
    setErrorCobro('');
  };

  const cobrar = async () => {
    if (!resumen) return;
    const pagos: PagoItem[] = dividir
      ? MEDIOS.filter((m) => aCentavos(montos[m.value]) > 0).map((m) => ({
          medio_pago: m.value,
          monto: aCentavos(montos[m.value]) / 100,
          comprobante_referencia: comprobantes[m.value].trim() || undefined,
        }))
      : [{ medio_pago: medioUnico, monto: saldoCent / 100, comprobante_referencia: comprobanteUnico.trim() || undefined }];
    const sinComprobante = pagos.find((p) => p.medio_pago !== 'EFECTIVO' && !p.comprobante_referencia);
    if (sinComprobante) {
      setErrorCobro(`Ingrese el número de comprobante de ${etiquetaMedio(sinComprobante.medio_pago)}.`);
      return;
    }
    if (dividir && restanteCent !== 0) {
      setErrorCobro('El desglose debe cubrir exactamente el saldo pendiente.');
      return;
    }
    setEnviando(true);
    try {
      // El total crece con el tiempo: se vuelve a consultar antes de cobrar para no liquidar un monto viejo.
      const actual = await api.getResumen(resumen.id);
      if (Math.round(actual.saldo_pendiente * 100) !== saldoCent) {
        setResumen(actual);
        toast(`El saldo cambió a ${formatMoney(actual.saldo_pendiente)}. Revise el desglose y confirme nuevamente.`, 'info');
        return;
      }
      const resultado = await api.cerrarTurno(resumen.id, pagos);
      setConstancia(resultado);
      setVista('constancia');
      toast(`Cobro de ${formatMoney(resultado.total_pagado)} registrado.`, 'success');
      await onRefreshRooms();
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo registrar el cobro.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  const liberarALimpieza = async () => {
    setEnviando(true);
    try {
      await api.updateHabitacionEstado(room.id, 'En Limpieza');
      toast(`${formatRoomNumber(room.numero)} pasó a limpieza.`, 'success');
      await onRefreshRooms();
      onClose();
    } catch (e) {
      const mensaje = getErrorMessage(e, 'No se pudo liberar la habitación.');
      setAvisoSaldo(mensaje);
      toast(mensaje, 'error');
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
  if (isOcupada) {
    subtitulo = { cuenta: 'Cuenta del turno', productos: 'Agregar productos', cobro: 'Cobro y cierre', constancia: '' }[vista];
  }
  if (room.estado === 'En Limpieza') subtitulo = 'En limpieza';
  if (room.estado === 'Mantenimiento') subtitulo = 'En mantenimiento';
  if (vista === 'constancia') subtitulo = 'Constancia de cobro';

  let body: React.ReactNode = null;
  let footer: React.ReactNode = null;

  if (vista === 'constancia' && constancia) {
    body = (
      <div data-print-area className="space-y-5">
        <div className="text-sm text-muted">
          <p>
            <span className="font-medium text-ink">{formatRoomNumber(constancia.habitacion_numero)}</span> · Turno{' '}
            {constancia.turno_id.slice(0, 8)}
          </p>
          <p>
            {formatDateTime(constancia.hora_inicio)} a {formatDateTime(constancia.hora_fin)}
          </p>
        </div>
        <table className="w-full text-sm">
          <tbody className="divide-y divide-line">
            <tr>
              <td className="py-2 text-muted">Estadía base ({ESTADIA_BASE_MIN / 60} h)</td>
              <td className="py-2 text-right tabular-nums">{formatMoney(constancia.tarifa_base)}</td>
            </tr>
            <tr>
              <td className="py-2 text-muted">Sobreturno</td>
              <td className="py-2 text-right tabular-nums">{formatMoney(constancia.total_sobreturno)}</td>
            </tr>
            <tr>
              <td className="py-2 text-muted">Consumos</td>
              <td className="py-2 text-right tabular-nums">{formatMoney(constancia.total_consumos)}</td>
            </tr>
            <tr className="font-medium">
              <td className="py-2">Total</td>
              <td className="py-2 text-right tabular-nums">{formatMoney(constancia.total_general)}</td>
            </tr>
          </tbody>
        </table>
        <div>
          <SectionTitle>Pagos registrados</SectionTitle>
          <ul className="divide-y divide-line text-sm">
            {constancia.pagos.map((p, i) => (
              <li key={i} className="flex items-baseline justify-between py-2">
                <span>
                  {etiquetaMedio(p.medio_pago)}
                  {p.comprobante_referencia && <span className="text-muted"> · {p.comprobante_referencia}</span>}
                </span>
                <span className="tabular-nums">{formatMoney(p.monto)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex items-baseline justify-between border-t border-line-strong pt-3 text-sm">
          <span className="text-muted">Saldo pendiente</span>
          <span className="text-lg font-semibold tabular-nums text-libre">{formatMoney(constancia.saldo_pendiente)}</span>
        </div>
      </div>
    );
    footer = (
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={() => window.print()}>
          <Printer className="h-4 w-4" aria-hidden="true" />
          Imprimir
        </Button>
        <Button className="flex-1" onClick={onClose}>
          Cerrar
        </Button>
      </div>
    );
  } else if (room.estado === 'Libre') {
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
                className={`flex min-h-11 flex-col items-center gap-1.5 rounded-md border px-3 py-3 text-sm press ${
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
            label="Código vehicular transitorio (opcional)"
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
          Estadía base de {ESTADIA_BASE_MIN / 60} horas. Superada, el excedente se liquida por fracciones.
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
    const transcurrido = elapsedMs(resumen, now);
    const fase = faseEstadia(transcurrido);
    const nombreArticulo = (id: number) => articulos.find((a) => a.id === id)?.descripcion ?? 'Producto';

    body = (
      <div className="space-y-6">
        <div className="flex items-baseline justify-between rounded-md bg-surface-2 px-4 py-3">
          <span className="text-sm text-muted">Tiempo transcurrido</span>
          <span className="text-right">
            <span className={`font-mono text-lg font-semibold tabular-nums ${FASE_META[fase].text}`}>
              {formatDuration(transcurrido)}
            </span>
            {fase === 'excedido' && (
              <span className="block text-xs font-medium text-danger">Excedido +{minutosExcedidos(transcurrido)} min</span>
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

        <div
          className={`rounded-md border px-4 py-3 ${avisoSaldo ? 'border-danger bg-danger-soft' : 'border-transparent'}`}
        >
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-medium text-ink">Saldo a cobrar</span>
            <span className="text-2xl font-semibold tabular-nums text-ink">{formatMoney(resumen.saldo_pendiente)}</span>
          </div>
          {avisoSaldo && (
            <p role="alert" className="mt-2 text-sm font-medium text-danger">
              {avisoSaldo}
            </p>
          )}
        </div>

        <div>
          <Button variant="ghost" disabled={enviando} onClick={() => void liberarALimpieza()}>
            Liberar a limpieza
          </Button>
          <p className="mt-1 text-xs text-subtle">Solo es posible con el saldo en cero.</p>
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
                    {sinStock ? <span className="text-danger">Stock insuficiente</span> : `Stock ${art.stock_actual}`}
                  </p>
                </div>
                <div className="flex items-center rounded-md border border-line-strong">
                  <button
                    type="button"
                    aria-label={`Quitar una unidad de ${art.descripcion}`}
                    disabled={qty === 0}
                    onClick={() => changeQty(art, -1)}
                    className="press hit p-2 text-muted hover:text-ink disabled:opacity-40 disabled:active:scale-100"
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
                    className="press hit p-2 text-muted hover:text-ink disabled:opacity-40 disabled:active:scale-100"
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
          <p className="mt-1 text-3xl font-semibold tabular-nums text-ink">{formatMoney(resumen.saldo_pendiente)}</p>
        </div>

        {!dividir && (
          <>
            <div>
              <SectionTitle>Medio de pago</SectionTitle>
              <div role="radiogroup" aria-label="Medio de pago" className="grid grid-cols-3 gap-2">
                {MEDIOS.map(({ value, label, icon: Icon }) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={medioUnico === value}
                    onClick={() => {
                      setMedioUnico(value);
                      setErrorCobro('');
                    }}
                    className={`flex flex-col items-center gap-1.5 rounded-md border px-2 py-3 text-center text-sm press ${
                      medioUnico === value
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

            {medioUnico !== 'EFECTIVO' && (
              <Field label="Nº de comprobante / lote" htmlFor="comprobante-unico" error={errorCobro}>
                <input
                  id="comprobante-unico"
                  data-autofocus
                  type="text"
                  inputMode="numeric"
                  autoComplete="off"
                  placeholder="000123456"
                  className={`${inputClass} font-mono`}
                  value={comprobanteUnico}
                  onChange={(e) => {
                    setComprobanteUnico(e.target.value);
                    setErrorCobro('');
                  }}
                />
              </Field>
            )}

            <button
              type="button"
              onClick={() => {
                setDividir(true);
                setErrorCobro('');
              }}
              className="hit text-sm text-accent underline-offset-2 hover:underline"
            >
              Dividir el pago entre medios
            </button>
          </>
        )}

        {dividir && (
        <div>
          <SectionTitle>Desglose del cobro</SectionTitle>
          <div className="space-y-3">
            {MEDIOS.map(({ value, label, comprobante, icon: Icon }) => {
              const conMonto = aCentavos(montos[value]) > 0;
              return (
                <div key={value} className="rounded-md border border-line p-3">
                  <div className="flex items-center gap-3">
                    <Icon className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
                    <label htmlFor={`monto-${value}`} className="flex-1 text-sm font-medium text-ink">
                      {label}
                    </label>
                    <input
                      id={`monto-${value}`}
                      type="number"
                      inputMode="decimal"
                      min="0"
                      step="0.01"
                      placeholder="0"
                      className={`${inputClass} w-32 text-right tabular-nums`}
                      value={montos[value]}
                      onChange={(e) => {
                        setMontos({ ...montos, [value]: e.target.value });
                        setErrorCobro('');
                      }}
                    />
                    <Button variant="ghost" size="sm" aria-label={`Completar con ${label}`} onClick={() => completarCon(value)}>
                      Saldo
                    </Button>
                  </div>
                  {value !== 'EFECTIVO' && conMonto && (
                    <div className="mt-3">
                      <label htmlFor={`comprobante-${value}`} className="mb-1.5 block text-xs font-medium text-muted">
                        {comprobante}
                      </label>
                      <input
                        id={`comprobante-${value}`}
                        type="text"
                        inputMode="numeric"
                        autoComplete="off"
                        placeholder="000123456"
                        className={`${inputClass} font-mono`}
                        value={comprobantes[value]}
                        onChange={(e) => {
                          setComprobantes({ ...comprobantes, [value]: e.target.value });
                          setErrorCobro('');
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        )}

        {dividir && (
          <>
            <div className="flex items-baseline justify-between text-sm" aria-live="polite">
              <span className="text-muted">
                Asignado <span className="tabular-nums text-ink">{formatMoney(asignadoCent / 100)}</span>
              </span>
              <span className={restanteCent === 0 ? 'font-medium text-libre' : 'font-medium text-danger'}>
                {restanteCent === 0 ? 'Saldo cubierto' : `Resta ${formatMoney(restanteCent / 100)}`}
              </span>
            </div>
            <button
              type="button"
              onClick={() => {
                setDividir(false);
                setErrorCobro('');
              }}
              className="hit text-sm text-accent underline-offset-2 hover:underline"
            >
              Volver a un solo medio de pago
            </button>
          </>
        )}

        {dividir && errorCobro && (
          <p role="alert" className="text-sm font-medium text-danger">
            {errorCobro}
          </p>
        )}
      </div>
    );
    footer = (
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" disabled={enviando} onClick={() => setVista('cuenta')}>
          Volver
        </Button>
        <Button className="flex-[2]" disabled={enviando || saldoCent === 0 || (dividir && restanteCent !== 0)} onClick={() => void cobrar()}>
          Confirmar cobro de {formatMoney(saldoCent / 100)}
        </Button>
      </div>
    );
  }

  return (
    <Modal title={titulo} subtitle={subtitulo} onClose={onClose} footer={footer}>
      {body}
    </Modal>
  );
};

export default RoomDialog;
