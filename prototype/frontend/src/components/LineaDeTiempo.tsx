import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, LayoutGrid, Rows3 } from 'lucide-react';
import { LineaDeTiempoDatos, TramoHabitacion } from '../types';
import { api, EVENTO_RECONECTADO } from '../services/api';
import { formatRoomNumber, parseUtc } from '../utils/format';
import { formatMinutos } from '../utils/turno';
import { EsqueletoTabla } from './ui/Carga';
import { Tooltip } from './ui/Graficos';

export type VistaHabitaciones = 'grilla' | 'linea';

const CLAVE_VISTA = 'motelos.vista-habitaciones';
const REFRESCO_MS = 60000;

export const leerVistaHabitaciones = (): VistaHabitaciones => {
  try {
    return localStorage.getItem(CLAVE_VISTA) === 'linea' ? 'linea' : 'grilla';
  } catch {
    return 'grilla';
  }
};

export const guardarVistaHabitaciones = (vista: VistaHabitaciones) => {
  try {
    localStorage.setItem(CLAVE_VISTA, vista);
  } catch {
    // sin almacenamiento local, vuelve a la grilla al recargar
  }
};

// Dos opciones con una pastilla que se desliza a la elegida. Se recuerda en el puesto.
export const SelectorVista: React.FC<{ vista: VistaHabitaciones; onCambiar: (vista: VistaHabitaciones) => void }> = ({ vista, onCambiar }) => (
  <div role="group" aria-label="Cómo ver las habitaciones" className="relative grid grid-cols-2 rounded-md border border-line-strong bg-surface-2 p-0.5">
    <span
      aria-hidden="true"
      className="absolute inset-y-0.5 left-0.5 w-[calc(50%-2px)] rounded bg-surface shadow-sm transition-transform duration-300 ease-out"
      style={{ transform: vista === 'linea' ? 'translateX(100%)' : 'none' }}
    />
    {(
      [
        ['grilla', 'Grilla', LayoutGrid],
        ['linea', 'Línea de tiempo', Rows3],
      ] as const
    ).map(([valor, etiqueta, Icono]) => (
      <button
        key={valor}
        type="button"
        aria-pressed={vista === valor}
        onClick={() => onCambiar(valor)}
        className={`relative flex items-center justify-center gap-1.5 whitespace-nowrap rounded px-3 py-1 text-sm transition-colors ${
          vista === valor ? 'font-medium text-ink' : 'text-muted hover:text-ink'
        }`}
      >
        <Icono className="h-4 w-4" aria-hidden="true" />
        {etiqueta}
      </button>
    ))}
  </div>
);

const TIPO: Record<TramoHabitacion['tipo'], { etiqueta: string; clase: string }> = {
  ocupada: { etiqueta: 'Ocupada', clase: 'bg-ocupada' },
  limpieza: { etiqueta: 'Limpieza', clase: 'bg-limpieza' },
  mantenimiento: { etiqueta: 'Mantenimiento', clase: 'bg-mant' },
};

const hora = (fecha: Date) => fecha.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const aFecha = (fecha: Date) =>
  `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}-${String(fecha.getDate()).padStart(2, '0')}`;
const CAMBIOS_DE_GUARDIA = [6, 14, 22];

interface Activo {
  x: number;
  y: number;
  titulo: string;
  texto: string;
}

// Las 24 horas de cada habitación, fila por fila: se ven de un vistazo los turnos, las limpiezas, los huecos y los picos.
const LineaDeTiempo: React.FC<{ onAbrir: (habitacionId: number) => void }> = ({ onAbrir }) => {
  // Sin día elegido, las últimas 24 horas; con un día, ese día de 0 a 24.
  const [dia, setDia] = useState<string | null>(null);
  const [datos, setDatos] = useState<LineaDeTiempoDatos | null>(null);
  const [error, setError] = useState(false);
  const [activo, setActivo] = useState<Activo | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);

  const cargar = useCallback(async () => {
    try {
      setDatos(await api.getLineaDeTiempo(dia ?? undefined));
      setError(false);
    } catch {
      setError(true);
    }
  }, [dia]);

  useEffect(() => {
    setDatos(null);
    void cargar();
    window.addEventListener(EVENTO_RECONECTADO, cargar);
    const intervalo = dia ? undefined : setInterval(() => void cargar(), REFRESCO_MS);
    return () => {
      window.removeEventListener(EVENTO_RECONECTADO, cargar);
      clearInterval(intervalo);
    };
  }, [cargar, dia]);

  const inicio = datos ? parseUtc(datos.desde).getTime() : 0;
  const fin = datos ? parseUtc(datos.hasta).getTime() : 1;
  const ahora = datos ? parseUtc(datos.ahora).getTime() : 0;
  const posicion = useCallback((momento: number) => ((momento - inicio) / (fin - inicio)) * 100, [inicio, fin]);

  // Una marca cada dos horas; los cambios de guardia, más marcados.
  const marcas = useMemo(() => {
    if (!datos) return [];
    const lista: { momento: number; hora: number }[] = [];
    const cursor = new Date(inicio);
    cursor.setMinutes(0, 0, 0);
    while (cursor.getTime() < inicio || cursor.getHours() % 2) cursor.setHours(cursor.getHours() + 1);
    while (cursor.getTime() <= fin) {
      lista.push({ momento: cursor.getTime(), hora: cursor.getHours() });
      cursor.setHours(cursor.getHours() + 2);
    }
    return lista;
  }, [datos, inicio, fin]);

  const moverDia = (dias: number) => {
    const base = dia ? new Date(`${dia}T12:00:00`) : new Date();
    base.setDate(base.getDate() + dias);
    setDia(aFecha(base) >= aFecha(new Date()) ? null : aFecha(base));
  };

  const enTramo = (tramo: TramoHabitacion) => (e: React.MouseEvent<HTMLElement>) => {
    const caja = contenedor.current?.getBoundingClientRect();
    const barra = e.currentTarget.getBoundingClientRect();
    if (!caja) return;
    const desde = hora(parseUtc(tramo.desde));
    setActivo({
      x: Math.max(Math.min(barra.left - caja.left + barra.width / 2, caja.width - 90), 90),
      y: barra.top - caja.top,
      titulo: `${TIPO[tramo.tipo].etiqueta}${tramo.en_curso ? ' · en curso' : ''}`,
      texto: `${desde} → ${tramo.en_curso ? 'ahora' : hora(parseUtc(tramo.hasta))} · ${formatMinutos(tramo.minutos)}`,
    });
  };

  const titulo = dia
    ? new Date(`${dia}T12:00:00`).toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'numeric' })
    : 'Últimas 24 horas';

  return (
    <div className="animate-fade-in space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {datos && (
            <>
              <Dato etiqueta="Turnos" valor={String(datos.resumen.turnos)} />
              <Dato etiqueta="Ocupación" valor={datos.resumen.ocupacion === null ? '—' : `${Math.round(datos.resumen.ocupacion * 100)}%`} />
              <Dato etiqueta="Por habitación" valor={datos.resumen.turnos_por_habitacion.toLocaleString('es-AR')} />
              <Dato etiqueta="Limpieza típica" valor={datos.resumen.limpieza_min === null ? '—' : `${datos.resumen.limpieza_min} min`} />
            </>
          )}
        </dl>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => moverDia(-1)} aria-label="Día anterior" className="press hit grid h-8 w-8 place-items-center rounded-md border border-line-strong bg-surface text-muted hover:text-ink">
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="min-w-[9.5rem] text-center text-sm font-medium capitalize text-ink">{titulo}</span>
          <button
            type="button"
            onClick={() => moverDia(1)}
            disabled={dia === null}
            aria-label="Día siguiente"
            className="press hit grid h-8 w-8 place-items-center rounded-md border border-line-strong bg-surface text-muted hover:text-ink disabled:opacity-40"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      {error && !datos && <p className="rounded-lg border border-line bg-surface py-12 text-center text-sm text-muted">No se pudo cargar la línea de tiempo.</p>}
      {!error && !datos && <EsqueletoTabla filas={8} etiqueta="Cargando la línea de tiempo…" />}

      {datos && (
        <div ref={contenedor} className="relative rounded-lg border border-line bg-surface" onMouseLeave={() => setActivo(null)}>
          <div className="overflow-x-auto">
            <div className="min-w-[56rem]">
              {/* Eje de horas */}
              <div className="grid grid-cols-[6.5rem_1fr] border-b border-line">
                <span />
                <div className="relative h-7">
                  {marcas.map((m) => (
                    <span
                      key={m.momento}
                      className={`absolute top-1.5 -translate-x-1/2 text-[11px] tabular-nums ${CAMBIOS_DE_GUARDIA.includes(m.hora) ? 'font-semibold text-muted' : 'text-subtle'}`}
                      style={{ left: `${posicion(m.momento)}%` }}
                    >
                      {String(m.hora).padStart(2, '0')}
                    </span>
                  ))}
                </div>
              </div>

              {datos.habitaciones.map((h, fila) => (
                <div key={h.habitacion_id} className="grid grid-cols-[6.5rem_1fr] border-b border-line last:border-0">
                  <div className="flex items-center gap-2 px-3 text-sm" title={h.categoria}>
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: h.color }} aria-hidden="true" />
                    <span className="truncate font-medium text-ink">{formatRoomNumber(h.numero)}</span>
                  </div>
                  <div className="relative h-9 overflow-hidden">
                    {marcas.map((m) => (
                      <span
                        key={m.momento}
                        aria-hidden="true"
                        className={`absolute inset-y-0 w-px ${CAMBIOS_DE_GUARDIA.includes(m.hora) ? 'bg-line-strong' : 'bg-line/60'}`}
                        style={{ left: `${posicion(m.momento)}%` }}
                      />
                    ))}
                    {h.tramos.map((t, i) => {
                      const izquierda = posicion(parseUtc(t.desde).getTime());
                      const ancho = posicion(parseUtc(t.hasta).getTime()) - izquierda;
                      const Marca = t.en_curso && t.tipo === 'ocupada' ? 'button' : 'div';
                      return (
                        <Marca
                          key={`${t.tipo}-${t.desde}`}
                          {...(Marca === 'button' ? { type: 'button' as const, onClick: () => onAbrir(h.habitacion_id), 'aria-label': `Abrir ${formatRoomNumber(h.numero)}` } : {})}
                          onMouseEnter={enTramo(t)}
                          className={`absolute inset-y-1.5 min-w-[3px] origin-left animate-tramo rounded-[3px] ${TIPO[t.tipo].clase} ${t.tipo === 'ocupada' ? '' : 'opacity-70'} ${
                            t.en_curso ? 'cursor-pointer ring-1 ring-ink/20' : ''
                          }`}
                          style={{ left: `${izquierda}%`, width: `${ancho}%`, animationDelay: `${Math.min(fila * 30 + i * 12, 600)}ms` }}
                        />
                      );
                    })}
                    {ahora > inicio && ahora < fin && (
                      <span aria-hidden="true" className="absolute inset-y-0 w-0.5 bg-danger/70" style={{ left: `${posicion(ahora)}%` }} />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          {activo && (
            <Tooltip x={activo.x} y={activo.y}>
              <span className="font-medium">{activo.titulo}</span>
              <br />
              <span className="tabular-nums text-muted">{activo.texto}</span>
            </Tooltip>
          )}
        </div>
      )}

      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        {Object.entries(TIPO).map(([tipo, meta]) => (
          <li key={tipo} className="flex items-center gap-1.5">
            <span className={`h-2.5 w-4 rounded-sm ${meta.clase} ${tipo === 'ocupada' ? '' : 'opacity-70'}`} aria-hidden="true" />
            {meta.etiqueta}
          </li>
        ))}
        <li className="text-subtle">Las líneas más marcadas son los cambios de guardia (6, 14 y 22 h).</li>
      </ul>
    </div>
  );
};

const Dato: React.FC<{ etiqueta: string; valor: string }> = ({ etiqueta, valor }) => (
  <div className="flex items-baseline gap-1.5">
    <dt className="text-muted">{etiqueta}</dt>
    <dd className="font-semibold tabular-nums text-ink">{valor}</dd>
  </div>
);

export default LineaDeTiempo;
