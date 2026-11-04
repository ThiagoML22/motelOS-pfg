import React, { useRef, useState } from 'react';
import { DIAS_CORTOS, Regla, reglaTexto, tramosPorDia } from '../utils/franjas';

export interface BloqueFranja extends Regla {
  id: number | string;
  nombre: string;
  color: string;
}

interface MapaSemanaProps {
  franjas: BloqueFranja[];
  compacto?: boolean;
  // La tarifa que se está armando, dibujada encima de las demás.
  fantasma?: (Regla & { error?: boolean }) | null;
  // Con esto se puede arrastrar sobre el mapa para elegir días y horas.
  onPintar?: (regla: Regla) => void;
}

interface Arrastre {
  dia: number;
  hora: number;
  diaFin: number;
  horaFin: number;
}

const pos = (minuto: number) => `${(minuto / 1440) * 100}%`;
const hora = (h: number) => `${String(h % 24).padStart(2, '0')}:00`;

const reglaDe = (a: Arrastre): Regla => {
  const [primerDia, ultimoDia] = [Math.min(a.dia, a.diaFin), Math.max(a.dia, a.diaFin)];
  const [primeraHora, ultimaHora] = [Math.min(a.hora, a.horaFin), Math.max(a.hora, a.horaFin)];
  let dias = 0;
  for (let d = primerDia; d <= ultimoDia; d++) dias |= 1 << d;
  return { dias, desde: hora(primeraHora), hasta: hora(ultimaHora + 1) };
};

// La semana de una categoría: cada fila es un día y lo pintado es lo que tiene tarifa especial; lo vacío es la general.
const MapaSemana: React.FC<MapaSemanaProps> = ({ franjas, compacto = false, fantasma, onPintar }) => {
  const zona = useRef<HTMLDivElement>(null);
  const [arrastre, setArrastre] = useState<Arrastre | null>(null);
  const ahora = new Date();
  const hoy = (ahora.getDay() + 6) % 7;
  const minutoActual = ahora.getHours() * 60 + ahora.getMinutes();
  const filaClase = compacto ? 'h-[9px]' : 'h-7';
  const regla = arrastre ? reglaDe(arrastre) : fantasma;

  const celda = (e: React.PointerEvent) => {
    const caja = zona.current?.getBoundingClientRect();
    if (!caja) return { dia: 0, hora: 0 };
    const x = Math.min(Math.max(e.clientX - caja.left, 0), caja.width - 1);
    const y = Math.min(Math.max(e.clientY - caja.top, 0), caja.height - 1);
    return { dia: Math.floor((y / caja.height) * 7), hora: Math.floor((x / caja.width) * 24) };
  };

  const pintable = onPintar
    ? {
        onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
          const { dia, hora: h } = celda(e);
          e.currentTarget.setPointerCapture(e.pointerId);
          setArrastre({ dia, hora: h, diaFin: dia, horaFin: h });
        },
        onPointerMove: (e: React.PointerEvent) => {
          if (!arrastre) return;
          const { dia, hora: h } = celda(e);
          if (dia !== arrastre.diaFin || h !== arrastre.horaFin) setArrastre({ ...arrastre, diaFin: dia, horaFin: h });
        },
        onPointerUp: () => {
          if (arrastre) onPintar(reglaDe(arrastre));
          setArrastre(null);
        },
        onPointerCancel: () => setArrastre(null),
      }
    : {};

  return (
    <div
      role="img"
      aria-label={
        franjas.length
          ? `Semana con tarifas especiales: ${franjas.map((f) => `${f.nombre}, ${reglaTexto(f)}`).join('; ')}.`
          : 'Semana sin tarifas especiales: rige la general.'
      }
    >
      {!compacto && (
        <div className="ml-9 flex justify-between text-[10px] tabular-nums text-subtle" aria-hidden="true">
          {[0, 6, 12, 18, 24].map((h) => (
            <span key={h}>{h} h</span>
          ))}
        </div>
      )}
      <div className="flex gap-1">
        <div className={`flex w-8 shrink-0 flex-col ${compacto ? 'w-6' : 'gap-px'}`} aria-hidden="true">
          {DIAS_CORTOS.map((d, i) => (
            <span
              key={d}
              className={`${filaClase} flex items-center ${compacto ? 'text-[8px] leading-none' : 'text-[11px]'} ${i === hoy ? 'font-semibold text-ink' : 'text-subtle'}`}
            >
              {compacto ? d[0] : d}
            </span>
          ))}
        </div>
        <div
          ref={zona}
          {...pintable}
          style={onPintar ? { touchAction: 'none' } : undefined}
          className={`relative min-w-0 flex-1 select-none overflow-hidden rounded-sm bg-surface-2 ${onPintar ? 'cursor-crosshair' : ''}`}
        >
          {[6, 12, 18].map((h) => (
            <span key={h} className="absolute inset-y-0 w-px bg-line" style={{ left: pos(h * 60) }} aria-hidden="true" />
          ))}
          <div className={`relative flex flex-col ${compacto ? '' : 'gap-px'}`}>
            {DIAS_CORTOS.map((d, dia) => (
              <div key={d} className={`relative ${filaClase} ${compacto ? '' : 'bg-line/30'}`}>
                {franjas.flatMap((f) =>
                  tramosPorDia(f)
                    .filter((t) => t.dia === dia)
                    .map((t) => (
                      <span
                        key={`${f.id}-${t.inicio}`}
                        title={`${f.nombre}: ${reglaTexto(f)}`}
                        className="absolute inset-y-0"
                        style={{ left: pos(t.inicio), width: pos(t.fin - t.inicio), backgroundColor: f.color }}
                      />
                    )),
                )}
                {regla &&
                  tramosPorDia(regla)
                    .filter((t) => t.dia === dia)
                    .map((t) => (
                      <span
                        key={`nueva-${t.inicio}`}
                        className={`absolute inset-y-0 border-2 border-dashed ${
                          !arrastre && fantasma?.error ? 'border-danger bg-danger/25' : 'border-ink bg-ink/15'
                        }`}
                        style={{ left: pos(t.inicio), width: pos(t.fin - t.inicio) }}
                      />
                    ))}
                {dia === hoy && <span className="absolute inset-y-0 w-0.5 bg-ink" style={{ left: pos(minutoActual) }} title="Ahora" />}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MapaSemana;
