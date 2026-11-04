import React, { useEffect, useId, useRef, useState } from 'react';
import { alCambiarTema, elegirTema, Modo, modoActual } from '../../utils/tema';

// El botón del tema: un solo astro que cambia como en un eclipse. En modo claro una sombra lo recorta en luna (con
// estrellas que titilan al pasar el mouse); al apretarlo la sombra se corre, el disco se achica y salen los rayos del
// sol, mientras la página cambia en una onda que nace del botón.
const ThemeToggle: React.FC<{ className?: string }> = ({ className = '' }) => {
  const [modo, setModo] = useState<Modo>(modoActual);
  const [pulsado, setPulsado] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  const mascara = `eclipse-${useId().replace(/:/g, '')}`;

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
      <svg className="astro" width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <defs>
          <mask id={mascara}>
            <rect width="24" height="24" fill="white" />
            <circle className="sombra" cx="17" cy="7.5" r="7.2" fill="black" />
          </mask>
        </defs>
        <g className="rayos-giro">
          <g className="rayos" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round">
            <path d="M12 2.2v2.3M12 19.5v2.3M2.2 12h2.3M19.5 12h2.3M5.1 5.1l1.6 1.6M17.3 17.3l1.6 1.6M5.1 18.9l1.6-1.6M17.3 6.7l1.6-1.6" />
          </g>
        </g>
        <circle className="disco" cx="12" cy="12" r="8.2" fill="currentColor" mask={`url(#${mascara})`} />
        <path className="estrella" d="M18.5 3l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z" fill="currentColor" />
        <path className="estrella estrella-2" d="M21.5 9.2l.4.9.9.4-.9.4-.4.9-.4-.9-.9-.4.9-.4z" fill="currentColor" />
        <circle className="estrella estrella-3" cx="15" cy="9.5" r="0.8" fill="currentColor" />
      </svg>
    </button>
  );
};

export default ThemeToggle;
