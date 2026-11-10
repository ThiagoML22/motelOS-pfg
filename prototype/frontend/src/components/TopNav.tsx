import React from 'react';
import { BarChart3, ClipboardList, LayoutGrid, Lock, LogOut, Package, Settings } from 'lucide-react';
import { Sesion } from '../types';
import { formatClock, parseUtc } from '../utils/format';

export type View = 'dashboard' | 'inventario' | 'caja' | 'gerencia' | 'configuracion' | 'actividad';

interface TopNavProps {
  sesion: Sesion;
  activeView: View;
  setActiveView: (view: View) => void;
  online: boolean;
  now: number;
  // Entradas del registro de actividad que la gerencia todavía no revisó.
  pendientes: number;
  onSalir: () => void;
}

const ITEMS: { view: View; label: string; icon: React.ElementType; roles: string[] }[] = [
  { view: 'dashboard', label: 'Habitaciones', icon: LayoutGrid, roles: ['OPERADOR', 'ADMINISTRADOR'] },
  { view: 'inventario', label: 'Inventario', icon: Package, roles: ['OPERADOR', 'ADMINISTRADOR'] },
  { view: 'caja', label: 'Cierre de caja', icon: Lock, roles: ['OPERADOR'] },
  { view: 'gerencia', label: 'Control de caja', icon: BarChart3, roles: ['ADMINISTRADOR'] },
  { view: 'configuracion', label: 'Configuración', icon: Settings, roles: ['ADMINISTRADOR'] },
  { view: 'actividad', label: 'Actividad', icon: ClipboardList, roles: ['ADMINISTRADOR'] },
];

const hora = (iso: string): string => {
  const d = parseUtc(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

const TopNav: React.FC<TopNavProps> = ({ sesion, activeView, setActiveView, online, now, pendientes, onSalir }) => {
  const { operador, guardia, establecimiento } = sesion;
  const items = ITEMS.filter((i) => i.roles.includes(operador.rol));

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface print:hidden">
      <div className="mx-auto flex h-14 max-w-[1600px] items-stretch gap-4 px-4 sm:gap-6 sm:px-6">
        <div className="flex items-center gap-3">
          <img src="/logo.png" alt="MotelOS" className="h-7 object-contain" />
          {establecimiento && (
            <span
              className="hidden max-w-[14rem] truncate whitespace-nowrap rounded-md border border-line bg-surface-2 px-2 py-1 text-xs font-medium text-ink md:inline"
              title={`Establecimiento: ${establecimiento.nombre} (${establecimiento.codigo})`}
            >
              {establecimiento.nombre}
            </span>
          )}
        </div>

        <nav aria-label="Principal" className="flex items-stretch gap-1">
          {items.map(({ view, label, icon: Icon }) => {
            const active = activeView === view;
            return (
              <button
                key={view}
                type="button"
                onClick={() => setActiveView(view)}
                aria-current={active ? 'page' : undefined}
                aria-label={view === 'actividad' && pendientes > 0 ? `${label}: ${pendientes} por revisar` : label}
                className={`press flex items-center gap-2 whitespace-nowrap border-b-2 px-2.5 text-sm sm:px-3 ${
                  active ? 'border-accent font-medium text-ink' : 'border-transparent text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">{label}</span>
                {view === 'actividad' && pendientes > 0 && (
                  <span className="rounded-full bg-warn px-1.5 py-0.5 text-[11px] font-semibold leading-none text-white tabular-nums">
                    {pendientes}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4 text-sm">
          {/* Con el menú de la gerencia (seis secciones) el nombre y la guardia se muestran desde 1536 px. */}
          <span className={`hidden text-right leading-tight ${items.length > 4 ? '2xl:block' : 'lg:block'}`}>
            <span className="block font-medium text-ink">{operador.nombre_visible}</span>
            <span className="block text-xs text-muted">
              {guardia
                ? `Guardia ${guardia.franja}${guardia.es_propia ? '' : ` de ${guardia.operador_nombre}`} · desde ${hora(guardia.abierta_en)}`
                : operador.rol === 'ADMINISTRADOR'
                  ? 'Administración · sin guardia abierta'
                  : 'Sin guardia abierta'}
            </span>
          </span>
          <time className="font-mono text-sm font-medium tabular-nums text-ink">{formatClock(new Date(now))}</time>
          <span className="flex items-center gap-1.5 text-xs text-muted" role="status">
            <span className={`h-2 w-2 rounded-full ${online ? 'bg-libre' : 'bg-danger'}`} aria-hidden="true" />
            <span className="hidden xl:inline">{online ? 'Conectado' : 'Sin conexión'}</span>
          </span>
          <button
            type="button"
            onClick={onSalir}
            aria-label="Cerrar sesión"
            title="Cerrar sesión"
            className="press hit rounded-md p-2 text-muted hover:bg-surface-2 hover:text-ink"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </header>
  );
};

export default TopNav;
