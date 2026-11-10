import React, { useEffect, useRef, useState } from 'react';

// Gráficos propios en SVG y HTML, sin librerías: barras finas con el extremo de datos redondeado, líneas de 2 px,
// grilla tenue y un tooltip por marca. Los colores salen de los tokens --viz-* (paleta validada en claro y oscuro);
// el texto siempre va en los tokens de tinta, nunca en el color de la serie.

export const useAncho = <T extends HTMLElement>() => {
  const ref = useRef<T>(null);
  const [ancho, setAncho] = useState(0);
  useEffect(() => {
    const elemento = ref.current;
    if (!elemento) return;
    const observador = new ResizeObserver(([entrada]) => setAncho(Math.floor(entrada.contentRect.width)));
    observador.observe(elemento);
    return () => observador.disconnect();
  }, []);
  return [ref, ancho] as const;
};

// Barra apoyada en la base con el extremo de datos redondeado (4 px).
const barra = (x: number, y: number, w: number, h: number, r = 4): string => {
  if (h <= 0 || w <= 0) return '';
  const radio = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + radio} Q${x},${y} ${x + radio},${y} H${x + w - radio} Q${x + w},${y} ${x + w},${y + radio} V${y + h} Z`;
};

// Máximo «redondo» para el eje (1, 2, 2,5 o 5 por potencia de 10).
const maximoRedondo = (valor: number): number => {
  if (valor <= 0) return 1;
  const potencia = 10 ** Math.floor(Math.log10(valor));
  const paso = [1, 2, 2.5, 5, 10].find((p) => p * potencia >= valor) ?? 10;
  return paso * potencia;
};

export const Tooltip: React.FC<{ x: number; y: number; children: React.ReactNode }> = ({ x, y, children }) => (
  <div
    role="tooltip"
    className="pointer-events-none absolute z-10 w-max max-w-[16rem] -translate-x-1/2 -translate-y-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs text-ink shadow-panel"
    style={{ left: x, top: y - 8 }}
  >
    {children}
  </div>
);

export interface Columna {
  clave: string;
  valor: number;
  // Rango plausible (pronóstico): se dibuja como un bigote fino.
  rango?: [number, number];
  eje: string | null;
  detalle: React.ReactNode;
  resaltada?: boolean;
}

interface ColumnasProps {
  columnas: Columna[];
  alto?: number;
  formatoEje: (valor: number) => string;
  descripcion: string;
}

// Columnas de una sola serie (sin leyenda: el título de la tarjeta la nombra), con tooltip por columna.
export const Columnas: React.FC<ColumnasProps> = ({ columnas, alto = 180, formatoEje, descripcion }) => {
  const [ref, ancho] = useAncho<HTMLDivElement>();
  const [activa, setActiva] = useState<number | null>(null);
  const margen = { izq: 44, der: 8, arr: 10, aba: 22 };
  const maximo = maximoRedondo(Math.max(...columnas.map((c) => c.rango?.[1] ?? c.valor), 0));
  const internoX = Math.max(ancho - margen.izq - margen.der, 0);
  const internoY = alto - margen.arr - margen.aba;
  const paso = columnas.length ? internoX / columnas.length : 0;
  const anchoBarra = Math.max(Math.min(paso - 2, 22), 2);
  const y = (v: number) => margen.arr + internoY - (v / maximo) * internoY;
  const marcas = [0, maximo / 2, maximo];

  return (
    <div ref={ref} className="relative" onMouseLeave={() => setActiva(null)}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label={descripcion}>
          {marcas.map((m) => (
            <g key={m}>
              <line x1={margen.izq} x2={ancho - margen.der} y1={y(m)} y2={y(m)} className={m === 0 ? 'stroke-viz-axis' : 'stroke-viz-grid'} strokeWidth={1} />
              <text x={margen.izq - 6} y={y(m)} dy="0.32em" textAnchor="end" className="fill-subtle text-[10px] tabular-nums">
                {formatoEje(m)}
              </text>
            </g>
          ))}
          {columnas.map((c, i) => {
            const cx = margen.izq + paso * i + paso / 2;
            const tope = y(c.valor);
            return (
              <g key={c.clave}>
                <path
                  d={barra(cx - anchoBarra / 2, tope, anchoBarra, margen.arr + internoY - tope)}
                  className={`animate-crecer fill-viz-1 transition-opacity ${activa !== null && activa !== i ? 'opacity-40' : ''}`}
                  style={{ transformOrigin: 'bottom', transformBox: 'fill-box', animationDelay: `${Math.min(i * 18, 500)}ms` }}
                />
                {c.rango && c.rango[1] > c.rango[0] && (
                  <line x1={cx} x2={cx} y1={y(c.rango[0])} y2={y(c.rango[1])} className="stroke-ink/30" strokeWidth={1} />
                )}
                {c.eje && (
                  <text x={cx} y={alto - 6} textAnchor="middle" className="fill-subtle text-[10px] tabular-nums">
                    {c.eje}
                  </text>
                )}
                {/* Área de hover más grande que la marca. */}
                <rect
                  x={margen.izq + paso * i}
                  y={margen.arr}
                  width={paso}
                  height={internoY}
                  fill="transparent"
                  onMouseEnter={() => setActiva(i)}
                />
              </g>
            );
          })}
        </svg>
      )}
      {activa !== null && columnas[activa] && (
        <Tooltip x={margen.izq + paso * activa + paso / 2} y={y(columnas[activa].rango?.[1] ?? columnas[activa].valor)}>
          {columnas[activa].detalle}
        </Tooltip>
      )}
    </div>
  );
};

interface LineaProps {
  valores: number[];
  etiquetas: (string | null)[];
  limite: number;
  etiquetaLimite: string;
  alto?: number;
  detalle: (i: number) => React.ReactNode;
  descripcion: string;
}

// Línea de 2 px con área tenue y una referencia punteada (la capacidad), con cursor vertical y tooltip.
export const Linea: React.FC<LineaProps> = ({ valores, etiquetas, limite, etiquetaLimite, alto = 140, detalle, descripcion }) => {
  const [ref, ancho] = useAncho<HTMLDivElement>();
  const [activa, setActiva] = useState<number | null>(null);
  const margen = { izq: 44, der: 8, arr: 14, aba: 22 };
  const maximo = Math.max(limite, ...valores) || 1;
  const internoX = Math.max(ancho - margen.izq - margen.der, 0);
  const internoY = alto - margen.arr - margen.aba;
  const paso = valores.length ? internoX / valores.length : 0;
  const x = (i: number) => margen.izq + paso * i + paso / 2;
  const y = (v: number) => margen.arr + internoY - (v / maximo) * internoY;
  const trazo = valores.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join(' ');
  const area = valores.length ? `${trazo} L${x(valores.length - 1)},${y(0)} L${x(0)},${y(0)} Z` : '';

  return (
    <div ref={ref} className="relative" onMouseLeave={() => setActiva(null)}>
      {ancho > 0 && (
        <svg width={ancho} height={alto} role="img" aria-label={descripcion}>
          <line x1={margen.izq} x2={ancho - margen.der} y1={y(0)} y2={y(0)} className="stroke-viz-axis" />
          <line x1={margen.izq} x2={ancho - margen.der} y1={y(limite)} y2={y(limite)} className="stroke-muted" strokeDasharray="4 4" />
          <text x={ancho - margen.der} y={y(limite) - 4} textAnchor="end" className="fill-muted text-[10px]">
            {etiquetaLimite}
          </text>
          <text x={margen.izq - 6} y={y(0)} dy="0.32em" textAnchor="end" className="fill-subtle text-[10px] tabular-nums">
            0
          </text>
          <text x={margen.izq - 6} y={y(limite)} dy="0.32em" textAnchor="end" className="fill-subtle text-[10px] tabular-nums">
            {limite}
          </text>
          <path d={area} className="animate-fade-in fill-viz-1/10" style={{ animationDuration: '900ms' }} />
          <path
            d={trazo}
            pathLength={1}
            strokeDasharray="1"
            className="animate-dibujar stroke-viz-1"
            strokeWidth={2}
            fill="none"
            strokeLinejoin="round"
          />
          {etiquetas.map(
            (e, i) =>
              e && (
                <text key={i} x={x(i)} y={alto - 6} textAnchor="middle" className="fill-subtle text-[10px] tabular-nums">
                  {e}
                </text>
              ),
          )}
          {activa !== null && (
            <>
              <line x1={x(activa)} x2={x(activa)} y1={margen.arr} y2={y(0)} className="stroke-muted" strokeWidth={1} />
              <circle cx={x(activa)} cy={y(valores[activa])} r={4.5} className="fill-viz-1 stroke-surface" strokeWidth={2} />
            </>
          )}
          {valores.map((_, i) => (
            <rect key={i} x={margen.izq + paso * i} y={margen.arr} width={paso} height={internoY} fill="transparent" onMouseEnter={() => setActiva(i)} />
          ))}
        </svg>
      )}
      {activa !== null && (
        <Tooltip x={x(activa)} y={y(valores[activa])}>
          {detalle(activa)}
        </Tooltip>
      )}
    </div>
  );
};

interface MapaCalorProps {
  filas: string[];
  valores: number[][];
  maximo: number;
  detalle: (fila: number, columna: number) => React.ReactNode;
}

// Mapa de calor de un solo tono (más intenso = más llegadas). El tono baja hacia la superficie en claro y en oscuro.
export const MapaCalor: React.FC<MapaCalorProps> = ({ filas, valores, maximo, detalle }) => {
  const contenedor = useRef<HTMLDivElement>(null);
  const [activa, setActiva] = useState<{ fila: number; columna: number; x: number; y: number } | null>(null);

  const enCelda = (fila: number, columna: number) => (e: React.MouseEvent<HTMLDivElement>) => {
    const caja = contenedor.current?.getBoundingClientRect();
    const celda = e.currentTarget.getBoundingClientRect();
    if (caja) setActiva({ fila, columna, x: celda.left - caja.left + celda.width / 2, y: celda.top - caja.top });
  };

  return (
    <div ref={contenedor} className="relative" onMouseLeave={() => setActiva(null)}>
      <div className="grid grid-cols-[2.5rem_repeat(24,minmax(0,1fr))] gap-[2px]">
        <span />
        {Array.from({ length: 24 }, (_, h) => (
          <span key={h} className="text-center text-[10px] tabular-nums text-subtle">
            {h % 3 === 0 ? h : ''}
          </span>
        ))}
        {filas.map((nombre, f) => (
          <React.Fragment key={nombre}>
            <span className="self-center pr-1 text-right text-[11px] text-muted">{nombre}</span>
            {valores[f].map((v, h) => (
              <div
                key={h}
                onMouseEnter={enCelda(f, h)}
                className={`h-6 rounded-[3px] ${activa?.fila === f && activa.columna === h ? 'ring-2 ring-ink/60' : ''}`}
                style={{ backgroundColor: `rgb(var(--viz-1) / ${maximo ? 0.06 + 0.94 * (v / maximo) : 0.06})` }}
              />
            ))}
          </React.Fragment>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-end gap-2 text-[11px] text-muted">
        Menos
        <span
          className="h-2 w-28 rounded-full"
          style={{ background: 'linear-gradient(to right, rgb(var(--viz-1) / 0.06), rgb(var(--viz-1)))' }}
          aria-hidden="true"
        />
        Más llegadas por hora
      </div>
      {activa && (
        <Tooltip x={activa.x} y={activa.y}>
          {detalle(activa.fila, activa.columna)}
        </Tooltip>
      )}
    </div>
  );
};

const CLASE_SERIE = ['bg-viz-1', 'bg-viz-2', 'bg-viz-3'];

// Parte de un total en una sola barra (hasta tres segmentos, color fijo por entidad) con leyenda y valores.
export const BarraPartes: React.FC<{ partes: { clave: string; etiqueta: string; parte: number; valor: string }[] }> = ({
  partes,
}) => (
  <div>
    <div className="flex h-3 gap-[2px] overflow-hidden rounded-full" role="img" aria-label={partes.map((p) => `${p.etiqueta} ${Math.round(p.parte * 100)}%`).join(', ')}>
      {partes.map((p, i) => (
        <div key={p.clave} className={`${CLASE_SERIE[i % 3]} h-full first:rounded-l-full last:rounded-r-full`} style={{ width: `${p.parte * 100}%` }} />
      ))}
    </div>
    <ul className="mt-3 space-y-1.5 text-sm">
      {partes.map((p, i) => (
        <li key={p.clave} className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-sm ${CLASE_SERIE[i % 3]}`} aria-hidden="true" />
          <span className="text-ink">{p.etiqueta}</span>
          <span className="ml-auto tabular-nums text-muted">{p.valor}</span>
          <span className="w-10 text-right font-medium tabular-nums text-ink">{Math.round(p.parte * 100)}%</span>
        </li>
      ))}
    </ul>
  </div>
);

// Barras horizontales de una serie, con el valor escrito al final de cada una.
export const BarrasHorizontales: React.FC<{ filas: { clave: string | number; etiqueta: string; valor: number; texto: string }[] }> = ({
  filas,
}) => {
  const maximo = Math.max(...filas.map((f) => f.valor), 1);
  return (
    <ul className="space-y-2">
      {filas.map((f) => (
        <li key={f.clave} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-sm">
          <span className="truncate text-ink" title={f.etiqueta}>
            {f.etiqueta}
          </span>
          <span className="h-2.5 rounded-r bg-viz-1" style={{ width: `${(f.valor / maximo) * 100}%` }} aria-hidden="true" />
          <span className="tabular-nums text-muted">{f.texto}</span>
        </li>
      ))}
    </ul>
  );
};
