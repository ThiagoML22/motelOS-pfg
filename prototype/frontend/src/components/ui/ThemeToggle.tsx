import React, { useEffect, useRef, useState } from 'react';
import { alCambiarTema, elegirTema, Modo, modoActual } from '../../utils/tema';

// La lunita del encabezado: en modo claro muestra una luna (con estrellas que titilan al pasar el mouse); al apretarla
// gira, se achica y deja lugar a un sol, y la página cambia de tema en un círculo que crece desde el botón.
const ThemeToggle: React.FC<{ className?: string }> = ({ className = '' }) => {
  const [modo, setModo] = useState<Modo>(modoActual);
  const [pulsado, setPulsado] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => alCambiarTema((nuevo) => setModo(nuevo)), []);

  const cambiar = () => {
    const caja = ref.current?.getBoundingClientRect();
    const origen = caja ? { x: caja.left + caja.width / 2, y: caja.top + caja.height / 2 } : undefined;
    setPulsado(false);
    window.requestAnimationFrame(() => setPulsado(true));
    elegirTema(modo === 'oscuro' ? 'claro' : 'oscuro', origen);
  };

  const etiqueta = modo === 'oscuro' ? 'Pasar a modo claro' : 'Pasar a modo oscuro';

  return (
    <button
      ref={ref}
      type="button"
      onClick={cambiar}
      onAnimationEnd={() => setPulsado(false)}
      aria-label={etiqueta}
      aria-pressed={modo === 'oscuro'}
      title={etiqueta}
      data-modo={modo}
      className={`tema-boton hit ${pulsado ? 'pulsado' : ''} ${className}`}
    >
      <span className="onda" aria-hidden="true" />
      <svg className="astro luna" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          className="cuerpo"
          d="M20.4 14.6A8.5 8.5 0 0 1 9.4 3.6a8.5 8.5 0 1 0 11 11Z"
          fill="currentColor"
          fillOpacity="0.15"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
        <path className="estrella" d="M17 3.5l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z" fill="currentColor" />
        <path className="estrella estrella-2" d="M21 8.2l.4.9.9.4-.9.4-.4.9-.4-.9-.9-.4.9-.4z" fill="currentColor" />
        <circle className="estrella estrella-3" cx="14.5" cy="7.5" r="0.8" fill="currentColor" />
      </svg>
      <svg className="astro sol" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="12" cy="12" r="4.2" fill="currentColor" fillOpacity="0.25" stroke="currentColor" strokeWidth="1.8" />
        <g className="rayos" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.5 1.5M17.2 17.2l1.5 1.5M5.3 18.7l1.5-1.5M17.2 6.8l1.5-1.5" />
        </g>
      </svg>
    </button>
  );
};

export default ThemeToggle;
