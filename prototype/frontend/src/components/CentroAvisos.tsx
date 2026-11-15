import React, { useEffect, useRef, useState } from 'react';
import { Bell, ClipboardList, MessageSquarePlus, ShieldAlert } from 'lucide-react';
import { IntentoAcceso, Novedad } from '../types';

const horaCorta = (iso: string) => new Date(iso).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
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
  // Intentos de entrar desde equipos no autorizados del último día (solo la gerencia, migración 019).
  intentos?: IntentoAcceso[];
  onIrEquipos?: () => void;
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
  intentos = [],
  onIrEquipos,
  onIrActividad,
  onNuevaNovedad,
}) => {
  const [abierto, setAbierto] = useState(false);
  const [vista, setVista] = useState(() => leerVista(claveVistas));
  const claveIntentos = `${claveVistas}.intentos`;
  const [vistoIntento, setVistoIntento] = useState(() => leerVista(claveIntentos));
  const contenedor = useRef<HTMLDivElement>(null);
  const sinLeer = novedades.filter((n) => n.id > vista && n.operador_id !== operadorId);
  const intentosNuevos = esGerencia ? intentos.filter((i) => i.id > vistoIntento) : [];
  const total = sinLeer.length + (esGerencia ? pendientes : 0) + intentosNuevos.length;
  const importantes = sinLeer.some((n) => n.importante) || intentosNuevos.length > 0;

  useEffect(() => {
    if (!abierto) return;
    const ultima = Math.max(0, ...novedades.map((n) => n.id));
    const ultimoIntento = Math.max(0, ...intentos.map((i) => i.id));
    try {
      if (ultima > vista) localStorage.setItem(claveVistas, String(ultima));
      if (ultimoIntento > vistoIntento) localStorage.setItem(claveIntentos, String(ultimoIntento));
    } catch {
      // sin almacenamiento local: la campanita vuelve a contar al recargar
    }
    const cerrar = () => {
      setAbierto(false);
      setVista(ultima);
      setVistoIntento(ultimoIntento);
    };
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) cerrar();
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cerrar();
    };
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', escape);
    };
  }, [abierto, novedades, vista, claveVistas, intentos, vistoIntento, claveIntentos]);

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
        <div className="fixed inset-x-2 top-[3.75rem] z-40 animate-pop-in rounded-lg border border-line bg-surface p-3 shadow-panel sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[22rem]">
          <p className="mb-2 text-sm font-semibold text-ink">Avisos</p>
          {esGerencia && intentos.length > 0 && onIrEquipos && (
            <button
              type="button"
              onClick={() => {
                setAbierto(false);
                setVistoIntento(Math.max(0, ...intentos.map((i) => i.id)));
                onIrEquipos();
              }}
              className="press mb-2 flex w-full items-start gap-2 rounded-md border border-danger/40 bg-danger-soft px-3 py-2 text-left text-sm text-danger"
            >
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                {intentos.length === 1 ? 'Un intento' : `${intentos.length} intentos`} de entrar desde equipos no autorizados en las últimas 24 h
                {intentosNuevos.length > 0 && <span className="font-semibold"> · {intentosNuevos.length} sin ver</span>}
                <span className="block text-xs opacity-80">
                  Último: {intentos[0].operador ?? 'un usuario que no existe'}, a las {horaCorta(intentos[0].creado_en)}, desde{' '}
                  {intentos[0].descripcion}
                </span>
              </span>
            </button>
          )}
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
