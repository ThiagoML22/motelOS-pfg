import React, { useEffect, useRef, useState } from 'react';
import {
  BarChart3,
  ChevronDown,
  ClipboardList,
  DoorOpen,
  LayoutGrid,
  Lock,
  LogOut,
  Package,
  Search,
  Settings,
  Sparkles,
  UserRound,
} from 'lucide-react';
import { Sesion } from '../types';
import { parseUtc } from '../utils/format';
import ThemeToggle from './ui/ThemeToggle';

export type View =
  | 'inteligencia'
  | 'dashboard'
  | 'inventario'
  | 'caja'
  | 'gerencia'
  | 'configuracion'
  | 'actividad'
  | 'perfil';

interface TopNavProps {
  sesion: Sesion;
  activeView: View;
  setActiveView: (view: View) => void;
  online: boolean;
  now: number;
  // Entradas del registro de actividad que la gerencia todavía no revisó.
  pendientes: number;
  onSalir: () => void;
  // Abre la paleta de comandos (Ctrl+K).
  onBuscar: () => void;
  // La campanita de avisos.
  avisos?: React.ReactNode;
}

// Orden del menú: primero la operación diaria, después el control y la configuración, y la inteligencia al final.
export const ITEMS: { view: View; label: string; icon: React.ElementType; roles: string[] }[] = [
  { view: 'dashboard', label: 'Habitaciones', icon: LayoutGrid, roles: ['OPERADOR', 'ADMINISTRADOR'] },
  { view: 'inventario', label: 'Inventario', icon: Package, roles: ['OPERADOR', 'ADMINISTRADOR'] },
  { view: 'caja', label: 'Cierre de caja', icon: Lock, roles: ['OPERADOR'] },
  { view: 'gerencia', label: 'Control de caja', icon: BarChart3, roles: ['ADMINISTRADOR'] },
  { view: 'configuracion', label: 'Configuración', icon: Settings, roles: ['ADMINISTRADOR'] },
  { view: 'actividad', label: 'Actividad', icon: ClipboardList, roles: ['ADMINISTRADOR'] },
  { view: 'inteligencia', label: 'Inteligencia', icon: Sparkles, roles: ['ADMINISTRADOR'] },
];

const ROL: Record<string, string> = { OPERADOR: 'Conserje', ADMINISTRADOR: 'Gerencia', PLATAFORMA: 'Plataforma' };
const FRANJA: Record<string, string> = { '06:00': 'mañana', '14:00': 'tarde', '22:00': 'noche' };

const hora = (fecha: Date): string =>
  `${String(fecha.getHours()).padStart(2, '0')}:${String(fecha.getMinutes()).padStart(2, '0')}`;

// Una línea con el estado de la guardia de la ventanilla.
const textoGuardia = (sesion: Sesion): string => {
  const { guardia, operador } = sesion;
  if (!guardia) return operador.rol === 'ADMINISTRADOR' ? 'Sin guardia abierta en la ventanilla' : 'Sin guardia abierta';
  const turno = `Guardia de la ${FRANJA[guardia.franja] ?? guardia.franja}`;
  const quien = guardia.es_propia ? '' : ` · ${guardia.operador_nombre}`;
  return `${turno}${quien} · desde las ${hora(parseUtc(guardia.abierta_en))}`;
};

// Encabezado en dos filas: arriba el motel y las herramientas (buscar, conexión, avisos, tema, usuario); abajo el menú
// de secciones con su espacio y la guardia en curso. En pantallas angostas el menú se desplaza en lugar de apretarse.
const TopNav: React.FC<TopNavProps> = ({
  sesion,
  activeView,
  setActiveView,
  online,
  now,
  pendientes,
  onSalir,
  onBuscar,
  avisos,
}) => {
  const { operador, establecimiento } = sesion;
  const items = ITEMS.filter((i) => i.roles.includes(operador.rol));

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface print:hidden">
      {/* Fila 1: el motel y las herramientas */}
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <img src="/logo.png" alt="MotelOS" className="logo h-7 shrink-0 object-contain" />
          {establecimiento && (
            <>
              <span className="hidden h-6 w-px bg-line sm:block" aria-hidden="true" />
              <span
                className="hidden truncate text-sm font-semibold text-ink sm:block"
                title={`${establecimiento.nombre} (código ${establecimiento.codigo})`}
              >
                {establecimiento.nombre}
              </span>
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
          <button
            type="button"
            onClick={onBuscar}
            aria-label="Buscar y hacer (Ctrl+K)"
            title="Buscar y hacer (Ctrl+K)"
            className="press flex h-9 items-center gap-2 rounded-md border border-line bg-surface-2 px-2.5 text-sm text-muted hover:border-line-strong hover:text-ink md:w-56 md:px-3"
          >
            <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="hidden flex-1 text-left md:inline">Buscar…</span>
            <kbd className="hidden rounded border border-line bg-surface px-1.5 text-[10px] font-medium md:inline">Ctrl K</kbd>
          </button>

          <span
            role="status"
            title={online ? 'Conectado con el servidor' : 'Sin conexión con el servidor'}
            className={`hidden h-9 items-center gap-2 rounded-md px-2.5 text-sm tabular-nums sm:flex ${
              online ? 'text-ink' : 'bg-danger-soft font-medium text-danger'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${online ? 'bg-libre' : 'bg-danger'}`} aria-hidden="true" />
            <span className="sr-only">{online ? 'Conectado' : 'Sin conexión'}</span>
            {online ? <time>{hora(new Date(now))}</time> : 'Sin conexión'}
          </span>

          <span className="hidden h-6 w-px bg-line sm:block" aria-hidden="true" />
          {avisos}
          <ThemeToggle />
          <MenuUsuario sesion={sesion} activeView={activeView} setActiveView={setActiveView} onSalir={onSalir} />
        </div>
      </div>

      {/* Fila 2: secciones y guardia en curso */}
      <div className="mx-auto flex h-11 max-w-[1600px] items-stretch gap-4 px-4 sm:px-6">
        <nav aria-label="Principal" className="sin-barra -mb-px flex min-w-0 flex-1 items-stretch gap-1 overflow-x-auto">
          {items.map(({ view, label, icon: Icon }) => {
            const active = activeView === view;
            return (
              <button
                key={view}
                type="button"
                onClick={() => setActiveView(view)}
                aria-current={active ? 'page' : undefined}
                aria-label={view === 'actividad' && pendientes > 0 ? `${label}: ${pendientes} por revisar` : label}
                className={`press flex shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 text-sm transition-colors ${
                  active ? 'border-accent font-medium text-ink' : 'border-transparent text-muted hover:border-line-strong hover:text-ink'
                }`}
              >
                <Icon className={`h-4 w-4 ${active ? 'text-accent' : ''}`} aria-hidden="true" />
                {label}
                {view === 'actividad' && pendientes > 0 && (
                  <span className="rounded-full bg-warn px-1.5 py-0.5 text-[11px] font-semibold leading-none text-white tabular-nums">
                    {pendientes}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <p className="hidden shrink-0 items-center gap-1.5 text-xs text-muted xl:flex">
          <DoorOpen className="h-3.5 w-3.5" aria-hidden="true" />
          {textoGuardia(sesion)}
        </p>
      </div>
    </header>
  );
};

interface MenuUsuarioProps {
  sesion: Sesion;
  activeView: View;
  setActiveView: (view: View) => void;
  onSalir: () => void;
}

// Avatar con el nombre: abre un menú con la cuenta, la guardia, Mi perfil y Cerrar sesión.
const MenuUsuario: React.FC<MenuUsuarioProps> = ({ sesion, activeView, setActiveView, onSalir }) => {
  const [abierto, setAbierto] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const { operador } = sesion;
  const primerNombre = operador.nombre_visible.split(/\s+/)[0];

  useEffect(() => {
    if (!abierto) return;
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierto(false);
    };
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setAbierto(false);
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', escape);
    };
  }, [abierto]);

  const elegir = (accion: () => void) => {
    setAbierto(false);
    accion();
  };

  return (
    <div ref={contenedor} className="relative">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        aria-haspopup="menu"
        aria-label={`Cuenta de ${operador.nombre_visible}`}
        className={`press flex h-9 items-center gap-2 rounded-full pl-0.5 pr-2 hover:bg-surface-2 ${
          activeView === 'perfil' || abierto ? 'bg-surface-2' : ''
        }`}
      >
        <Avatar nombre={operador.nombre_visible} />
        <span className="hidden max-w-[8rem] truncate text-sm font-medium text-ink md:inline">{primerNombre}</span>
        <ChevronDown className={`h-4 w-4 text-muted transition-transform ${abierto ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {abierto && (
        <div
          role="menu"
          className="absolute right-0 top-full z-40 mt-2 w-72 animate-pop-in overflow-hidden rounded-lg border border-line bg-surface shadow-panel"
        >
          <div className="flex items-center gap-3 border-b border-line px-4 py-3">
            <Avatar nombre={operador.nombre_visible} />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{operador.nombre_visible}</p>
              <p className="truncate text-xs text-muted">
                {ROL[operador.rol] ?? operador.rol} · {operador.usuario}
              </p>
            </div>
          </div>
          <p className="flex items-start gap-2 border-b border-line px-4 py-2.5 text-xs text-muted">
            <DoorOpen className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {textoGuardia(sesion)}
          </p>
          <div className="p-1.5">
            <button
              type="button"
              role="menuitem"
              onClick={() => elegir(() => setActiveView('perfil'))}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-ink hover:bg-surface-2"
            >
              <UserRound className="h-4 w-4 text-muted" aria-hidden="true" />
              Mi perfil
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => elegir(onSalir)}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm text-danger hover:bg-danger-soft"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Cerrar sesión
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// Iniciales del nombre visible (hasta dos) en un círculo.
export const Avatar: React.FC<{ nombre: string; grande?: boolean }> = ({ nombre, grande = false }) => {
  const iniciales =
    nombre
      .split(/\s+/)
      .filter((p) => /[\p{L}\p{N}]/u.test(p))
      .slice(0, 2)
      .map((p) => p.match(/[\p{L}\p{N}]/u)?.[0] ?? '')
      .join('')
      .toUpperCase() || '?';
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-full bg-accent font-semibold text-accent-fg ${
        grande ? 'h-16 w-16 text-xl' : 'h-8 w-8 text-xs'
      }`}
    >
      {iniciales}
    </span>
  );
};

export default TopNav;
