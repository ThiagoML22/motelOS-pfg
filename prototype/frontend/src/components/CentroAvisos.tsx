import React, { useEffect, useRef, useState } from 'react';
import { Bell, ClipboardList, MessageSquarePlus } from 'lucide-react';
import { Novedad } from '../types';
import { ListaNovedades } from './NovedadesPanel';
import Button from './ui/Button';

interface CentroAvisosProps {
  novedades: Novedad[];
  // Entradas del registro de actividad por revisar (solo la gerencia).
  pendientes: number;
  esGerencia: boolean;
  // Las novedades propias no cuentan como «sin leer».
  operadorId: number;
  // Clave del puesto y la persona para recordar hasta qué novedad se leyó.
  claveVistas: string;
  onIrActividad: () => void;
  onNuevaNovedad: () => void;
}

const leerVista = (clave: string): number => {
  try {
    return Number(localStorage.getItem(clave) ?? 0);
  } catch {
    return 0;
  }
};

// La campanita: novedades que todavía no se leyeron y, para la gerencia, lo que cargaron los conserjes por revisar.
const CentroAvisos: React.FC<CentroAvisosProps> = ({
  novedades,
  pendientes,
  esGerencia,
  operadorId,
  claveVistas,
  onIrActividad,
  onNuevaNovedad,
}) => {
  const [abierto, setAbierto] = useState(false);
  const [vista, setVista] = useState(() => leerVista(claveVistas));
  const contenedor = useRef<HTMLDivElement>(null);
  const sinLeer = novedades.filter((n) => n.id > vista && n.operador_id !== operadorId);
  const total = sinLeer.length + (esGerencia ? pendientes : 0);
  const importantes = sinLeer.some((n) => n.importante);

  useEffect(() => {
    if (!abierto) return;
    const ultima = Math.max(0, ...novedades.map((n) => n.id));
    if (ultima > vista) {
      try {
        localStorage.setItem(claveVistas, String(ultima));
      } catch {
        // sin almacenamiento local: la campanita vuelve a contar al recargar
      }
    }
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) {
        setAbierto(false);
        setVista(ultima);
      }
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setAbierto(false);
        setVista(ultima);
      }
    };
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', escape);
    };
  }, [abierto, novedades, vista, claveVistas]);

  return (
    <div ref={contenedor} className="relative">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        aria-label={total ? `Avisos: ${total} sin ver` : 'Avisos'}
        title="Avisos"
        className="press hit relative rounded-md p-2 text-muted hover:bg-surface-2 hover:text-ink"
      >
        <Bell className={`h-4 w-4 ${total ? 'origin-top animate-[campana_1.2s_ease-in-out_2]' : ''}`} aria-hidden="true" />
        {total > 0 && (
          <span
            className={`absolute -right-0.5 -top-0.5 grid h-4 min-w-[1rem] place-items-center rounded-full px-1 text-[10px] font-semibold leading-none text-white tabular-nums ${
              importantes ? 'bg-danger' : 'bg-warn'
            }`}
          >
            {total > 9 ? '9+' : total}
          </span>
        )}
      </button>
      {abierto && (
        <div className="absolute right-0 top-full z-40 mt-2 w-[22rem] max-w-[calc(100vw-2rem)] animate-pop-in rounded-lg border border-line bg-surface p-3 shadow-panel">
          <p className="mb-2 text-sm font-semibold text-ink">Avisos</p>
          {esGerencia && pendientes > 0 && (
            <button
              type="button"
              onClick={() => {
                setAbierto(false);
                onIrActividad();
              }}
              className="press mb-2 flex w-full items-center gap-2 rounded-md border border-warn/40 bg-warn-soft px-3 py-2 text-left text-sm text-warn"
            >
              <ClipboardList className="h-4 w-4 shrink-0" aria-hidden="true" />
              {pendientes} {pendientes === 1 ? 'cambio de un conserje' : 'cambios de conserjes'} por revisar en Actividad
            </button>
          )}
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-subtle">
            Novedades {sinLeer.length > 0 && `· ${sinLeer.length} nuevas`}
          </p>
          <div className="max-h-72 overflow-y-auto">
            <ListaNovedades novedades={novedades.slice(0, 6)} vacio="Todavía no hay novedades." />
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3 w-full"
            onClick={() => {
              setAbierto(false);
              onNuevaNovedad();
            }}
          >
            <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
            Dejar novedad
          </Button>
        </div>
      )}
    </div>
  );
};

export default CentroAvisos;
