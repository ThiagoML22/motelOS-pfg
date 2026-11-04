import React, { useEffect, useRef, useState } from 'react';
import { BellRing, Bike, Car, CheckCircle2, Footprints, MoreVertical, Sparkles, Wrench } from 'lucide-react';
import { Categoria, HabitacionConDetalles, PedidoVentanilla, RoomStatus } from '../types';
import { formatDuration, formatMoney, formatRoomNumber } from '../utils/format';
import { ESTADIA_BASE_MIN, elapsedMs, faseEstadia, formatMinutos, minutosExcedidos, minutosRestantes } from '../utils/turno';
import { ChipCategoria } from './CategoriasConfig';
import Button from './ui/Button';
import { ESTADO_META, FASE_META } from './ui/status';

interface RoomCardProps {
  room: HabitacionConDetalles;
  // Categoría de la habitación (Simple, Especial, VIP...): chip con su color y la tarifa en la tarjeta libre.
  categoria?: Categoria;
  now: number;
  onClick: (room: HabitacionConDetalles) => void;
  onAddConsumo: (room: HabitacionConDetalles) => void;
  onChangeEstado: (room: HabitacionConDetalles, newState: RoomStatus) => void;
  pedidos?: PedidoVentanilla[];
}

const CAMBIOS_ESTADO: { estado: RoomStatus; label: string; icon: React.ElementType }[] = [
  { estado: 'Libre', label: 'Disponible', icon: CheckCircle2 },
  { estado: 'En Limpieza', label: 'Limpieza', icon: Sparkles },
  { estado: 'Mantenimiento', label: 'Mantenimiento', icon: Wrench },
];

const TIPO_ICON: Record<string, React.ElementType> = { Auto: Car, Moto: Bike, Peaton: Footprints };
const TIPO_LABEL: Record<string, string> = { Auto: 'Auto', Moto: 'Moto', Peaton: 'Peatón' };

const RoomCard: React.FC<RoomCardProps> = ({ room, categoria, now, onClick, onAddConsumo, onChangeEstado, pedidos = [] }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const meta = ESTADO_META[room.estado];
  const turno = room.estado === 'Ocupada' ? room.turno_activo : null;

  // Cuando la habitación cambia de estado (la abrió, la cobró o la liberó alguien), la tarjeta se ilumina un momento.
  const estadoAnterior = useRef(room.estado);
  const [destello, setDestello] = useState(false);
  useEffect(() => {
    if (estadoAnterior.current === room.estado) return;
    estadoAnterior.current = room.estado;
    setDestello(true);
    const fin = setTimeout(() => setDestello(false), 1400);
    return () => clearTimeout(fin);
  }, [room.estado]);

  useEffect(() => {
    if (!menuOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [menuOpen]);

  const transcurrido = turno ? elapsedMs(turno, now) : 0;
  // El exceso se mide con la estadía base de la tarifa del turno (cada categoría tiene la suya).
  const baseMin = turno?.estadia_base_min ?? categoria?.tarifa?.estadia_base_min ?? undefined;
  const fase = faseEstadia(transcurrido, baseMin);
  const faseMeta = FASE_META[fase];
  const barClass = turno && faseMeta.bar ? faseMeta.bar : meta.bar;
  const TipoIcon = turno ? (TIPO_ICON[turno.tipo_cliente] ?? Car) : Car;
  const cliente = turno
    ? turno.tipo_cliente === 'Peaton'
      ? 'Peatón'
      : turno.identificador_vehicular || TIPO_LABEL[turno.tipo_cliente]
    : '';

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick(room)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          onClick(room);
        }
      }}
      aria-label={`${formatRoomNumber(room.numero)}, ${meta.label}`}
      className={`group relative flex h-full min-h-[9.5rem] cursor-pointer flex-col rounded-lg border border-l-4 border-line bg-surface p-4 transition duration-200 ease-out hover:-translate-y-0.5 hover:border-b-line-strong hover:border-r-line-strong hover:border-t-line-strong hover:shadow-lift active:translate-y-0 active:shadow-none ${barClass} ${destello ? 'animate-destello' : ''}`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-base font-semibold text-ink">{formatRoomNumber(room.numero)}</h3>
        <span className={`flex items-center gap-1.5 text-xs font-medium ${meta.text}`}>
          <span className={`h-2 w-2 rounded-full ${meta.dot}`} aria-hidden="true" />
          {meta.label}
        </span>
      </div>
      {categoria && <ChipCategoria categoria={categoria} className="mt-1.5 self-start" />}

      <div className="mt-2 flex-1">
        {turno ? (
          <>
            <p className="flex items-center gap-1.5 text-sm text-muted">
              <TipoIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{cliente}</span>
            </p>
            <p className={`mt-1.5 font-mono text-xl font-semibold tabular-nums ${faseMeta.text} ${fase === 'excedido' ? 'animate-latido' : ''}`}>
              {formatDuration(elapsedMs(turno, now))}
            </p>
            <p className="mt-0.5 min-h-[1rem] text-xs text-muted">
              {fase === 'excedido' && (
                <span className="font-medium text-danger">Excedido +{minutosExcedidos(transcurrido, baseMin)} min</span>
              )}
              {fase === 'por_vencer' && (
                <span className="font-medium text-warn">Vence en {minutosRestantes(transcurrido, baseMin)} min</span>
              )}
              {turno.total_consumos > 0 && (
                <span className={fase !== 'normal' ? 'ml-2' : ''}>Consumos {formatMoney(turno.total_consumos)}</span>
              )}
            </p>
          </>
        ) : (
          <>
            <p className="text-sm text-muted">{meta.hint}</p>
            {room.estado === 'Libre' && categoria?.tarifa && (
              <p className="mt-1 text-xs tabular-nums text-subtle">
                {formatMinutos(categoria.tarifa.estadia_base_min)} · {formatMoney(categoria.tarifa.tarifa_base)}
              </p>
            )}
          </>
        )}
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        {turno ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={(e) => {
              e.stopPropagation();
              onAddConsumo(room);
            }}
          >
            Agregar producto
          </Button>
        ) : (
          <span />
        )}

        {/* Lo que pidió el cliente con su QR: se atiende abriendo la habitación. */}
        {pedidos.length > 0 && (
          <span title={pedidos.map((p) => (p.cantidad ? `${p.cantidad} × ${p.descripcion}` : p.descripcion)).join(' · ')} className="flex min-w-0 animate-pop-in items-center gap-1 rounded-full bg-warn-soft px-2 py-1 text-xs font-medium text-warn">
            <BellRing className="h-3.5 w-3.5 shrink-0 animate-latido" aria-hidden="true" />
            <span className="tabular-nums">{pedidos.length}</span>
            <span className="sr-only">{pedidos.length === 1 ? 'pedido del cliente' : 'pedidos del cliente'}</span>
          </span>
        )}

        {room.estado !== 'Ocupada' && (
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              aria-label={`Cambiar estado de ${formatRoomNumber(room.numero)}`}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={(e) => {
                e.stopPropagation();
                setMenuOpen((v) => !v);
              }}
              onKeyDown={(e) => {
                e.stopPropagation();
                if (e.key === 'Escape') setMenuOpen(false);
              }}
              className="press hit flex h-8 w-8 items-center justify-center rounded-md border border-line-strong bg-surface text-muted hover:bg-surface-2 hover:text-ink"
            >
              <MoreVertical className="h-4 w-4" aria-hidden="true" />
            </button>

            {menuOpen && (
              <div
                role="menu"
                className="absolute bottom-full right-0 z-20 mb-2 w-44 animate-pop-in overflow-hidden rounded-md border border-line bg-surface py-1 shadow-panel"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => {
                  e.stopPropagation();
                  if (e.key === 'Escape') setMenuOpen(false);
                }}
              >
                {CAMBIOS_ESTADO.filter((c) => c.estado !== room.estado).map(({ estado, label, icon: Icon }) => (
                  <button
                    key={estado}
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onChangeEstado(room, estado);
                    }}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-ink transition-colors hover:bg-surface-2"
                  >
                    <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
                    Pasar a {label.toLowerCase()}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Cuánto de la estadía base ya pasó: se lee sin mirar el reloj. */}
      {turno && (
        <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1 overflow-hidden rounded-br-[7px] bg-line/50">
          <span
            className={`block h-full transition-[width] duration-1000 ease-linear ${
              fase === 'excedido' ? 'bg-danger' : fase === 'por_vencer' ? 'bg-warn' : 'bg-ocupada/60'
            }`}
            style={{ width: `${Math.min(transcurrido / ((baseMin ?? ESTADIA_BASE_MIN) * 600), 100)}%` }}
          />
        </span>
      )}
    </div>
  );
};

export default RoomCard;
