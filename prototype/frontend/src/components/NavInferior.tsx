import React, { useState } from 'react';
import { ChevronRight, MoreHorizontal, UserRound } from 'lucide-react';
import { Sesion } from '../types';
import { ITEMS, View } from './TopNav';
import Modal from './ui/Modal';

// En el celular las secciones principales van abajo, al alcance del pulgar; el resto, en «Más».
const PRINCIPALES: Record<string, View[]> = {
  OPERADOR: ['dashboard', 'inventario', 'caja'],
  ADMINISTRADOR: ['dashboard', 'gerencia', 'operacion', 'inteligencia'],
};

// Nombres cortos para que entren cinco botones en 375 px.
const CORTO: Partial<Record<View, string>> = { gerencia: 'Caja', caja: 'Caja', configuracion: 'Ajustes' };

interface NavInferiorProps {
  sesion: Sesion;
  activeView: View;
  setActiveView: (view: View) => void;
  // Entradas de Actividad sin revisar: se marcan en «Más».
  pendientes: number;
}

const NavInferior: React.FC<NavInferiorProps> = ({ sesion, activeView, setActiveView, pendientes }) => {
  const [mas, setMas] = useState(false);
  const rol = sesion.operador.rol;
  const propios = ITEMS.filter((i) => i.roles.includes(rol));
  const principales = PRINCIPALES[rol] ?? propios.slice(0, 4).map((i) => i.view);
  const abajo = propios.filter((i) => principales.includes(i.view));
  const resto = [...propios.filter((i) => !principales.includes(i.view)), { view: 'perfil' as View, label: 'Mi perfil', icon: UserRound, roles: [] }];
  const enResto = resto.some((i) => i.view === activeView);

  const ir = (view: View) => {
    setMas(false);
    setActiveView(view);
  };

  const Boton: React.FC<{ activo: boolean; etiqueta: string; icon: React.ElementType; marca?: number; onClick: () => void }> = ({
    activo,
    etiqueta,
    icon: Icon,
    marca,
    onClick,
  }) => (
    <button
      type="button"
      onClick={onClick}
      aria-current={activo ? 'page' : undefined}
      className={`relative flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 pt-1 text-[11px] font-medium transition-colors ${
        activo ? 'text-accent' : 'text-muted active:text-ink'
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute inset-x-4 top-0 h-0.5 rounded-b-full bg-accent transition-opacity ${activo ? 'opacity-100' : 'opacity-0'}`}
      />
      <span className={`relative grid h-7 w-12 place-items-center rounded-full transition-colors ${activo ? 'bg-accent-soft' : ''}`}>
        <Icon className="h-5 w-5" aria-hidden="true" />
        {!!marca && (
          <span className="absolute -right-0.5 -top-1 grid h-4 min-w-[1rem] place-items-center rounded-full bg-warn px-1 text-[10px] font-semibold leading-none text-white tabular-nums">
            {marca}
          </span>
        )}
      </span>
      <span className="max-w-full truncate px-0.5 tracking-tight">{etiqueta}</span>
    </button>
  );

  return (
    <>
      <nav
        aria-label="Secciones"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur print:hidden sm:hidden"
      >
        <div className="flex h-16">
          {abajo.map(({ view, label, icon }) => (
            <Boton
              key={view}
              activo={activeView === view}
              etiqueta={CORTO[view] ?? label}
              icon={icon}
              onClick={() => ir(view)}
            />
          ))}
          <Boton
            activo={enResto || mas}
            etiqueta="Más"
            icon={MoreHorizontal}
            marca={resto.some((i) => i.view === 'actividad') ? pendientes : 0}
            onClick={() => setMas(true)}
          />
        </div>
      </nav>

      {mas && (
        <Modal title="Más secciones" onClose={() => setMas(false)}>
          <ul className="-mx-2 -my-1">
            {resto.map(({ view, label, icon: Icon }) => {
              const activo = activeView === view;
              return (
                <li key={view}>
                  <button
                    type="button"
                    onClick={() => ir(view)}
                    aria-current={activo ? 'page' : undefined}
                    className={`press flex h-14 w-full items-center gap-3 rounded-md px-3 text-left text-base ${
                      activo ? 'bg-accent-soft font-medium text-accent' : 'text-ink active:bg-surface-2'
                    }`}
                  >
                    <Icon className={`h-5 w-5 ${activo ? 'text-accent' : 'text-muted'}`} aria-hidden="true" />
                    <span className="flex-1">{label}</span>
                    {view === 'actividad' && pendientes > 0 && (
                      <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-semibold tabular-nums text-warn">
                        {pendientes} por revisar
                      </span>
                    )}
                    <ChevronRight className="h-4 w-4 text-subtle" aria-hidden="true" />
                  </button>
                </li>
              );
            })}
          </ul>
        </Modal>
      )}
    </>
  );
};

export default NavInferior;
