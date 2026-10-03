import React from 'react';
import { LayoutGrid, Lock, Package } from 'lucide-react';
import { formatClock } from '../utils/format';
import { guardiaActual } from '../utils/turno';

export type View = 'dashboard' | 'inventario' | 'caja';

interface TopNavProps {
  activeView: View;
  setActiveView: (view: View) => void;
  online: boolean;
  now: number;
}

const ITEMS: { view: View; label: string; icon: React.ElementType }[] = [
  { view: 'dashboard', label: 'Habitaciones', icon: LayoutGrid },
  { view: 'inventario', label: 'Inventario', icon: Package },
  { view: 'caja', label: 'Cierre de caja', icon: Lock },
];

const TopNav: React.FC<TopNavProps> = ({ activeView, setActiveView, online, now }) => {
  const date = new Date(now);
  const guardia = guardiaActual(date.getHours());

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface">
      <div className="mx-auto flex h-14 max-w-[1600px] items-stretch gap-4 px-4 sm:gap-8 sm:px-6">
        <div className="flex items-center">
          <img src="/logo.png" alt="MotelOS" className="h-7 object-contain" />
        </div>

        <nav aria-label="Principal" className="flex items-stretch gap-1">
          {ITEMS.map(({ view, label, icon: Icon }) => {
            const active = activeView === view;
            return (
              <button
                key={view}
                type="button"
                onClick={() => setActiveView(view)}
                aria-current={active ? 'page' : undefined}
                aria-label={label}
                className={`press flex min-w-11 items-center justify-center gap-2 border-b-2 px-2.5 text-sm sm:px-3 ${
                  active
                    ? 'border-accent font-medium text-ink'
                    : 'border-transparent text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">{label}</span>
              </button>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-4 text-sm">
          <span className="hidden text-muted md:inline">
            Guardia {guardia.label} <span className="text-subtle">· {guardia.range}</span>
          </span>
          <time className="font-mono text-sm font-medium tabular-nums text-ink">{formatClock(date)}</time>
          <span className="flex items-center gap-1.5 text-xs text-muted" role="status">
            <span className={`h-2 w-2 rounded-full ${online ? 'bg-libre' : 'bg-danger'}`} aria-hidden="true" />
            <span className="hidden sm:inline">{online ? 'Conectado' : 'Sin conexión'}</span>
          </span>
        </div>
      </div>
    </header>
  );
};

export default TopNav;
