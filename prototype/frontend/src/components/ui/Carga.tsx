import React, { useEffect, useRef, useState } from 'react';

// Piezas de interfaz para los tiempos de espera y los vacíos: esqueletos con un brillo que los recorre (en lugar de
// «Cargando…»), cifras que cuentan hasta su valor y estados vacíos con ícono.

export const Bloque: React.FC<{ className?: string }> = ({ className = '' }) => (
  <div
    aria-hidden="true"
    className={`animate-brillo rounded-md bg-[length:200%_100%] ${className}`}
    style={{
      backgroundImage: 'linear-gradient(90deg, rgb(var(--surface-2)) 0%, rgb(var(--line)) 50%, rgb(var(--surface-2)) 100%)',
    }}
  />
);

const Esqueleto: React.FC<{ etiqueta: string; children: React.ReactNode }> = ({ etiqueta, children }) => (
  <div role="status" aria-label={etiqueta} className="animate-fade-in">
    <span className="sr-only">{etiqueta}</span>
    {children}
  </div>
);

export const EsqueletoGrilla: React.FC<{ cantidad?: number }> = ({ cantidad = 10 }) => (
  <Esqueleto etiqueta="Cargando habitaciones…">
    <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4">
      {Array.from({ length: cantidad }, (_, i) => (
        <div key={i} className="flex min-h-[9.5rem] flex-col gap-3 rounded-lg border border-l-4 border-line bg-surface p-4">
          <div className="flex justify-between">
            <Bloque className="h-5 w-16" />
            <Bloque className="h-4 w-20" />
          </div>
          <Bloque className="h-4 w-24" />
          <Bloque className="mt-auto h-6 w-32" />
        </div>
      ))}
    </div>
  </Esqueleto>
);

export const EsqueletoTabla: React.FC<{ filas?: number; etiqueta?: string }> = ({ filas = 6, etiqueta = 'Cargando…' }) => (
  <Esqueleto etiqueta={etiqueta}>
    <div className="overflow-hidden rounded-lg border border-line bg-surface">
      <div className="border-b border-line bg-surface-2 px-4 py-3">
        <Bloque className="h-3 w-1/3" />
      </div>
      {Array.from({ length: filas }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-line px-4 py-3 last:border-0">
          <Bloque className="h-4 w-1/4" />
          <Bloque className="h-4 w-1/5" />
          <Bloque className="ml-auto h-4 w-20" />
        </div>
      ))}
    </div>
  </Esqueleto>
);

export const EsqueletoTablero: React.FC = () => (
  <Esqueleto etiqueta="Analizando los datos…">
    <div className="space-y-5">
      <div className="space-y-3 rounded-lg border border-line bg-surface p-5">
        <Bloque className="h-3 w-32" />
        <Bloque className="h-6 w-2/3" />
        <div className="grid gap-2 md:grid-cols-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Bloque key={i} className="h-4 w-full" />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 2xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="space-y-2 bg-surface px-4 py-3">
            <Bloque className="h-3 w-20" />
            <Bloque className="h-6 w-24" />
          </div>
        ))}
      </div>
      <div className="rounded-lg border border-line bg-surface p-5">
        <Bloque className="mb-4 h-4 w-48" />
        <div className="flex h-36 items-end gap-1.5">
          {Array.from({ length: 24 }, (_, i) => (
            <Bloque key={i} className="flex-1" />
          ))}
        </div>
      </div>
    </div>
  </Esqueleto>
);

// Cifra que cuenta desde 0 (o desde el valor anterior) hasta el nuevo en ~0,7 s, con desaceleración al final.
export const Cifra: React.FC<{ valor: number; formato?: (v: number) => string; duracion?: number }> = ({
  valor,
  formato = (v) => Math.round(v).toLocaleString('es-AR'),
  duracion = 700,
}) => {
  const [mostrado, setMostrado] = useState(0);
  const desde = useRef(0);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setMostrado(valor);
      desde.current = valor;
      return;
    }
    const inicio = performance.now();
    const origen = desde.current;
    let cuadro = 0;
    const paso = (ahora: number) => {
      const t = Math.min(1, (ahora - inicio) / duracion);
      const suave = 1 - (1 - t) ** 3;
      setMostrado(origen + (valor - origen) * suave);
      if (t < 1) cuadro = requestAnimationFrame(paso);
      else desde.current = valor;
    };
    cuadro = requestAnimationFrame(paso);
    // Respaldo: con la pestaña en segundo plano no hay cuadros; la cifra llega igual a su valor.
    const seguro = setTimeout(() => {
      setMostrado(valor);
      desde.current = valor;
    }, duracion + 150);
    return () => {
      cancelAnimationFrame(cuadro);
      clearTimeout(seguro);
    };
  }, [valor, duracion]);
  return <span className="tabular-nums">{formato(mostrado)}</span>;
};

// Estado vacío con ícono: cuando una lista o una búsqueda no tiene resultados.
export const EstadoVacio: React.FC<{ icono: React.ElementType; titulo: string; texto?: string; children?: React.ReactNode }> = ({
  icono: Icono,
  titulo,
  texto,
  children,
}) => (
  <div className="flex animate-fade-in flex-col items-center gap-2 rounded-lg border border-dashed border-line-strong bg-surface px-6 py-12 text-center">
    <span className="grid h-12 w-12 place-items-center rounded-full bg-surface-2 text-muted">
      <Icono className="h-6 w-6" aria-hidden="true" />
    </span>
    <p className="font-medium text-ink">{titulo}</p>
    {texto && <p className="max-w-sm text-sm text-muted">{texto}</p>}
    {children}
  </div>
);
