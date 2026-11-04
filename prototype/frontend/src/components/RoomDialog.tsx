import React, { useCallback, useEffect, useState } from 'react';
import { ArrowRightLeft, BellRing, Banknote, Bike, CalendarClock, Car, CreditCard, ExternalLink, Footprints, Minus, Plus, Printer, QrCode, Receipt } from 'lucide-react';
import { Articulo, Categoria, HabitacionConDetalles, MedioPago, PedidoVentanilla, TicketCliente, TipoCliente, TurnoResumen } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDuration, formatMoney, formatRoomNumber } from '../utils/format';
import { ESTADIA_BASE_MIN, elapsedMs, faseEstadia, formatMinutos, minutosExcedidos } from '../utils/turno';
import ArreglosHabitacion, { BotonArreglos } from './ArreglosHabitacion';
import { ChipCategoria } from './CategoriasConfig';
import TrasladoTurno from './TrasladoTurno';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { FASE_META } from './ui/status';
import { useToast } from './ui/Toast';

interface RoomDialogProps {
  room: HabitacionConDetalles;
  // Categoría de la habitación: su tarifa vigente es la que tomará el turno al abrirse.
  categoria?: Categoria;
  now: number;
  onClose: () => void;
  onAperturaTurno: (patente: string | undefined, tipoCliente: TipoCliente, tarifaId?: number) => Promise<void>;
  onRefreshRooms: () => Promise<void>;
  initialAddProduct?: boolean;
  // Lo que el cliente de esta habitación pidió con su QR y todavía espera.
  pedidos?: PedidoVentanilla[];
  onCambioPedidos?: () => Promise<void>;
  // El nombre del motel, para el ticket.
  motel?: string;
  // Para elegir a qué habitación trasladar el turno.
  habitaciones?: HabitacionConDetalles[];
  categorias?: Categoria[];
}

type Vista = 'cuenta' | 'productos' | 'cobro' | 'ticket' | 'arreglos' | 'trasladar';

const AVISO_CAMBIO_TARIFA_MIN = 60;

// Las líneas de un carrito comparten lote: se atienden como un solo pedido.
const agruparPedidos = (pedidos: PedidoVentanilla[]): PedidoVentanilla[][] => {
  const grupos = new Map<string, PedidoVentanilla[]>();
  for (const p of pedidos) {
    const clave = p.lote ?? `p${p.id}`;
    grupos.set(clave, [...(grupos.get(clave) ?? []), p]);
  }
  return [...grupos.values()];
};

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

const RoomDialog: React.FC<RoomDialogProps> = ({
  room,
  categoria,
  now,
  onClose,
  onAperturaTurno,
  onRefreshRooms,
  initialAddProduct = false,
  pedidos = [],
  onCambioPedidos,
  motel,
  habitaciones = [],
  categorias = [],
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
  const [ticket, setTicket] = useState<TicketCliente | null>(null);

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

  const abrirTicket = async () => {
    if (!turnoId) return;
    try {
      setTicket(await api.getTicket(turnoId));
      setVista('ticket');
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo generar el ticket.'), 'error');
    }
  };

  // Una línea por vez: si falta stock de una, las demás quedan hechas y el mensaje dice cuál falló.
  const moverPedidos = async (lineas: PedidoVentanilla[], accion: (id: number) => Promise<unknown>, listo: string) => {
    setEnviando(true);
    try {
      for (const linea of lineas) await accion(linea.id);
      toast(listo, 'success');
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo atender el pedido.'), 'error');
    } finally {
      await onCambioPedidos?.();
      if (turnoId) await loadData(turnoId);
      await onRefreshRooms();
      setEnviando(false);
    }
  };

  const pedidoDeCuenta = pedidos.find((p) => p.tipo === 'SALIDA');
  const irACobrar = () => {
    if (pedidoDeCuenta?.medio_pago) setMedioPago(pedidoDeCuenta.medio_pago);
    setVista('cobro');
  };

  const titulo = formatRoomNumber(room.numero);
  let subtitulo = 'Apertura de turno';
  if (isOcupada) {
    subtitulo = {
      productos: 'Agregar productos',
      cobro: 'Cobro y cierre',
      cuenta: 'Cuenta del turno',
      ticket: 'Ticket para el cliente',
      arreglos: 'Arreglos',
      trasladar: 'Trasladar el turno',
    }[vista];
  }
  // RNF-04: en el recambio, la guardia entrante ve quién abrió el turno que va a cobrar.
  if (isOcupada && room.turno_activo?.abierto_por) subtitulo += ` · abierto por ${room.turno_activo.abierto_por}`;
  if (room.estado === 'En Limpieza') subtitulo = 'En limpieza';
  if (room.estado === 'Mantenimiento') subtitulo = 'En mantenimiento';
  if (vista === 'arreglos') subtitulo = 'Arreglos';

  let body: React.ReactNode = null;
  let footer: React.ReactNode = null;
  const arreglosAbiertos = room.arreglos_abiertos ?? 0;

  if (vista === 'arreglos') {
    body = <ArreglosHabitacion room={room} onCambio={onRefreshRooms} onVolver={() => setVista('cuenta')} />;
  } else if (vista === 'trasladar' && isOcupada) {
    body = (
      <TrasladoTurno
        room={room}
        habitaciones={habitaciones}
        categorias={categorias}
        onVolver={() => setVista('cuenta')}
        onListo={async () => {
          await onRefreshRooms();
          onClose();
        }}
      />
    );
  } else if (room.estado === 'Libre') {
    const tarifa = categoria?.tarifa_ahora ?? categoria?.tarifa;
    const ahora = categoria?.tarifa_ahora;
    // Una franja que empieza o termina pronto se avisa: el precio del cliente que está en la puerta depende de eso.
    const minutosParaElCambio = ahora?.cambia_en ? (new Date(ahora.cambia_en).getTime() - now) / 60000 : null;
    const cambiaPronto = minutosParaElCambio !== null && minutosParaElCambio <= AVISO_CAMBIO_TARIFA_MIN;
    body = (
      <form
        id="form-apertura"
        onSubmit={(e) => {
          e.preventDefault();
          void onAperturaTurno(tipoCliente === 'Peaton' ? undefined : patente.trim() || undefined, tipoCliente, ahora?.id);
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
                className={`flex flex-col items-center gap-1.5 rounded-md border px-3 py-3 text-sm press ${
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

        {categoria && tarifa ? (
          <div className="rounded-md border border-line bg-surface-2 px-3 py-2.5 text-sm">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="flex min-w-0 items-center gap-2">
                <ChipCategoria categoria={categoria} />
                {tarifa.franja && <span className="truncate text-xs font-medium text-accent">{tarifa.franja}</span>}
              </span>
              <span className="font-semibold tabular-nums text-ink">{formatMoney(tarifa.tarifa_base)}</span>
            </div>
            <p className="text-muted">
              Turno de {formatMinutos(tarifa.estadia_base_min)}. Superado
              {tarifa.tolerancia_min > 0 && ` (con ${tarifa.tolerancia_min} min de tolerancia)`}, se
              cobran {formatMoney(tarifa.tarifa_fraccion)} cada {formatMinutos(tarifa.fraccion_min)}
              {tarifa.tope ? `, con un tope de ${formatMoney(tarifa.tope)} por estadía` : ''}.
            </p>
            {cambiaPronto && ahora?.cambia_en && ahora.cambia_a_precio != null && (
              <p className="mt-1.5 flex items-start gap-1.5 text-warn">
                <CalendarClock className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  A las {new Date(ahora.cambia_en).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })} pasa a{' '}
                  {formatMoney(ahora.cambia_a_precio)}
                  {ahora.cambia_a ? ` (${ahora.cambia_a})` : ' (tarifa general)'}. Este turno se abre con la de ahora.
                </span>
              </p>
            )}
          </div>
        ) : (
          <p className="rounded-md bg-surface-2 px-3 py-2.5 text-sm text-muted">
            Estadía base de {ESTADIA_BASE_MIN / 60} horas. Superada, el excedente se liquida por fracciones.
          </p>
        )}
        <BotonArreglos abiertos={arreglosAbiertos} onClick={() => setVista('arreglos')} />
      </form>
    );
    footer = (
      <Button type="submit" form="form-apertura" className="w-full">
        Ocupar habitación
      </Button>
    );
  } else if (room.estado === 'En Limpieza') {
    body = (
      <div className="space-y-4">
        <p className="text-sm text-muted">
          La habitación está pendiente de limpieza. Al marcarla como disponible volverá a estar lista para ocupar.
        </p>
        <BotonArreglos abiertos={arreglosAbiertos} onClick={() => setVista('arreglos')} />
      </div>
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
      <div className="space-y-4">
        <p className="text-sm text-muted">
          La habitación está fuera de servicio. Al habilitarla volverá a estar disponible para ocupar.
        </p>
        {arreglosAbiertos > 0 && (
          <p className="text-sm text-warn">
            {arreglosAbiertos === 1 ? 'Tiene un arreglo sin resolver.' : `Tiene ${arreglosAbiertos} arreglos sin resolver.`}
          </p>
        )}
        <BotonArreglos abiertos={arreglosAbiertos} onClick={() => setVista('arreglos')} />
      </div>
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
  } else if (vista === 'ticket' && ticket) {
    body = (
      <div data-print-area className="mx-auto flex max-w-xs flex-col items-center gap-2 text-center">
        {motel && <p className="text-base font-semibold text-ink">{motel}</p>}
        <p className="text-sm text-muted">
          {titulo} · entrada{' '}
          {new Date(ticket.hora_inicio).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })}
        </p>
        <img src={ticket.qr} alt="Código QR de la estadía" className="h-52 w-52 animate-pop-in rounded-md bg-white p-1" />
        <p className="text-sm text-ink">Escaneá el código para ver tu tiempo y tu cuenta, o pedir algo sin llamar.</p>
        <p className="text-xs text-muted">Sin cuenta ni datos personales. Deja de funcionar cuando te vas.</p>
      </div>
    );
    footer = (
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={() => setVista('cuenta')}>
          Volver
        </Button>
        <Button variant="secondary" className="flex-1" onClick={() => window.open(ticket.direccion, '_blank', 'noopener')}>
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
          Ver como cliente
        </Button>
        <Button className="flex-1" onClick={() => window.print()}>
          <Printer className="h-4 w-4" aria-hidden="true" />
          Imprimir
        </Button>
      </div>
    );
  } else if (vista === 'cuenta') {
    const transcurrido = elapsedMs(resumen, now);
    // La tarifa del turno (la de su categoría al abrirse), no la vigente hoy.
    const baseMin = resumen.tarifa?.estadia_base_min ?? resumen.estadia_base_min ?? ESTADIA_BASE_MIN;
    const fase = faseEstadia(transcurrido, baseMin);
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
              <span className="block text-xs font-medium text-danger">Excedido +{minutosExcedidos(transcurrido, baseMin)} min</span>
            )}
          </span>
        </div>

        {pedidos.length > 0 && (
          <div className="animate-pop-in rounded-md border border-warn/40 bg-warn-soft px-3 py-2.5">
            <h3 className="mb-1.5 flex items-center gap-1.5 text-sm font-semibold text-warn">
              <BellRing className="h-4 w-4" aria-hidden="true" />
              Pedidos del cliente
            </h3>
            <ul className="space-y-2.5">
              {agruparPedidos(pedidos).map((lineas) => {
                const delMinibar = lineas[0].tipo === 'ARTICULO';
                const sinSalir = lineas.filter((l) => l.estado === 'Pendiente');
                const total = lineas.reduce((suma, l) => suma + (l.subtotal ?? 0), 0);
                return (
                  <li key={lineas[0].lote ?? lineas[0].id} className="text-sm">
                    {delMinibar &&
                      lineas.map((l) => (
                        <div key={l.id} className="flex items-center justify-between gap-2 text-ink">
                          <span className="min-w-0">{`${l.cantidad} × ${l.descripcion}`}</span>
                          <button
                            type="button"
                            disabled={enviando}
                            onClick={() => void moverPedidos([l], api.rechazarPedidoCliente, 'Avisamos que no está disponible.')}
                            className="press shrink-0 rounded px-1.5 py-0.5 text-xs text-muted hover:text-danger"
                          >
                            No hay
                          </button>
                        </div>
                      ))}
                    <div className={`flex flex-wrap items-center justify-between gap-2 ${delMinibar ? 'mt-1.5' : ''}`}>
                      {delMinibar ? (
                        <span className="text-xs text-muted">{`${formatMoney(total)}${sinSalir.length ? '' : ' · En camino'}`}</span>
                      ) : (
                        <span className="min-w-0 text-ink">{lineas[0].descripcion}</span>
                      )}
                      <span className="flex gap-1.5">
                        {delMinibar && sinSalir.length > 0 && (
                          <Button size="sm" variant="secondary" disabled={enviando} onClick={() => void moverPedidos(sinSalir, api.llevarPedidoCliente, 'El cliente ya lo ve en camino.')}>
                            Lo llevo
                          </Button>
                        )}
                        {lineas[0].tipo === 'SALIDA' ? (
                          <Button size="sm" disabled={enviando} onClick={irACobrar}>
                            Cobrar
                          </Button>
                        ) : (
                          <Button size="sm" disabled={enviando} onClick={() => void moverPedidos(lineas, api.atenderPedidoCliente, delMinibar ? 'Pedido entregado.' : 'Listo.')}>
                            {delMinibar ? 'Entregado' : 'Listo'}
                          </Button>
                        )}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        <div>
          <SectionTitle>Detalle</SectionTitle>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-line">
              <tr>
                <td className="py-2 text-muted">
                  Estadía base ({formatMinutos(baseMin)}
                  {resumen.tarifa?.categoria ? ` · ${resumen.tarifa.categoria}` : ''}
                  {resumen.tarifa?.franja ? ` · ${resumen.tarifa.franja}` : ''})
                </td>
                <td className="py-2 text-right tabular-nums text-ink">{formatMoney(resumen.tarifa_base)}</td>
              </tr>
              <tr>
                <td className="py-2 text-muted">
                  Sobreturno
                  {resumen.tarifa && (
                    <span className="text-subtle">
                      {' '}
                      · {formatMoney(resumen.tarifa.tarifa_fraccion)} cada {formatMinutos(resumen.tarifa.fraccion_min)}
                    </span>
                  )}
                </td>
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

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <button type="button" onClick={() => void abrirTicket()} className="press inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline">
            <QrCode className="h-4 w-4" aria-hidden="true" />
            Ticket con QR
          </button>
          <button type="button" onClick={() => setVista('trasladar')} className="press inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline">
            <ArrowRightLeft className="h-4 w-4" aria-hidden="true" />
            Trasladar
          </button>
          <BotonArreglos abiertos={arreglosAbiertos} onClick={() => setVista('arreglos')} />
        </div>
      </div>
    );
    footer = (
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={() => setVista('productos')}>
          Agregar productos
        </Button>
        <Button className="flex-1" onClick={irACobrar}>
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
                    className="press p-2 text-muted hover:text-ink disabled:opacity-40 disabled:active:scale-100"
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
                    className="press p-2 text-muted hover:text-ink disabled:opacity-40 disabled:active:scale-100"
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
          {pedidoDeCuenta?.medio_pago && (
            <p className="mb-2 text-xs text-muted">{pedidoDeCuenta.descripcion}. Podés cambiarlo si paga de otra forma.</p>
          )}
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
                className={`flex flex-col items-center gap-1.5 rounded-md border px-2 py-3 text-center text-sm press ${
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
    <Modal title={titulo} subtitle={subtitulo} onClose={onClose} footer={footer}>
      {body}
    </Modal>
  );
};

export default RoomDialog;
