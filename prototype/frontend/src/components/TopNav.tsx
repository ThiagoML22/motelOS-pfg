import React from 'react';
import { BarChart3, LayoutGrid, Lock, LogOut, Package } from 'lucide-react';
import { Sesion } from '../types';
import { formatClock, parseUtc } from '../utils/format';

export type View = 'dashboard' | 'inventario' | 'caja' | 'gerencia';

interface TopNavProps {
  sesion: Sesion;
  activeView: View;
  setActiveView: (view: View) => void;
  online: boolean;
  now: number;
  onSalir: () => void;
}

const ITEMS: { view: View; label: string; icon: React.ElementType; roles: string[] }[] = [
  { view: 'dashboard', label: 'Habitaciones', icon: LayoutGrid, roles: ['OPERADOR', 'ADMINISTRADOR'] },
  { view: 'inventario', label: 'Inventario', icon: Package, roles: ['OPERADOR', 'ADMINISTRADOR'] },
  { view: 'caja', label: 'Cierre de caja', icon: Lock, roles: ['OPERADOR'] },
  { view: 'gerencia', label: 'Control de caja', icon: BarChart3, roles: ['ADMINISTRADOR'] },
];

const hora = (iso: string): string => {
  const d = parseUtc(iso);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};

const TopNav: React.FC<TopNavProps> = ({ sesion, activeView, setActiveView, online, now, onSalir }) => {
  const { operador, guardia } = sesion;
  const items = ITEMS.filter((i) => i.roles.includes(operador.rol));

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface print:hidden">
      <div className="mx-auto flex h-14 max-w-[1600px] items-stretch gap-4 px-4 sm:gap-6 sm:px-6">
        <div className="flex items-center">
          <img src="/logo.png" alt="MotelOS" className="h-7 object-contain" />
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
                aria-label={label}
                className={`press flex items-center gap-2 border-b-2 px-2.5 text-sm sm:px-3 ${
                  active ? 'border-accent font-medium text-ink' : 'border-transparent text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">{label}</span>
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4 text-sm">
          <span className="hidden text-right leading-tight lg:block">
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
