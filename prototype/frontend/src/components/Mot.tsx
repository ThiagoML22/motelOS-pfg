import React, { useEffect, useRef } from 'react';

// Mot, el robotcito del asistente. Es un dibujo propio en SVG: el cuerpo toma el color de marca del motel y cada parte se
// anima desde index.css. `estado` dice cómo está (cambia la cara y el movimiento) y `gesto` es algo suelto y corto.

export type EstadoMot = 'reposo' | 'saludando' | 'pensando' | 'hablando' | 'contento' | 'triste' | 'durmiendo';
export type GestoMot = 'salto' | 'saludo' | 'mirar' | 'voltereta';

interface MotProps {
  estado?: EstadoMot;
  gesto?: GestoMot | null;
  // Solo la cabeza, para el encabezado del chat.
  soloCabeza?: boolean;
  // Los ojos miran hacia donde está el cursor.
  seguirCursor?: boolean;
  className?: string;
}

export const sinMovimiento = (): boolean => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Lo más que se corren los ojos desde el centro, y a qué distancia del cursor llegan a ese punto.
const MIRADA_X = 3.4;
const MIRADA_Y = 2.6;
const DISTANCIA_MIRADA = 160;

const Mot: React.FC<MotProps> = ({ estado = 'reposo', gesto = null, soloCabeza = false, seguirCursor = false, className = '' }) => {
  const dibujo = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!seguirCursor || sinMovimiento()) return;
    let cuadro = 0;
    let x = 0;
    let y = 0;
    const mirar = () => {
      cuadro = 0;
      const svg = dibujo.current;
      if (!svg) return;
      const caja = svg.getBoundingClientRect();
      const dx = x - (caja.left + caja.width / 2);
      const dy = y - (caja.top + caja.height * 0.36);
      const distancia = Math.hypot(dx, dy) || 1;
      const fuerza = Math.min(distancia / DISTANCIA_MIRADA, 1);
      // Se escribe directo en el dibujo: mover el mouse no le pide nada a React.
      svg.style.setProperty('--mirar-x', `${((dx / distancia) * MIRADA_X * fuerza).toFixed(2)}px`);
      svg.style.setProperty('--mirar-y', `${((dy / distancia) * MIRADA_Y * fuerza).toFixed(2)}px`);
    };
    const mover = (e: PointerEvent) => {
      x = e.clientX;
      y = e.clientY;
      if (!cuadro) cuadro = requestAnimationFrame(mirar);
    };
    window.addEventListener('pointermove', mover, { passive: true });
    return () => {
      window.removeEventListener('pointermove', mover);
      cancelAnimationFrame(cuadro);
    };
  }, [seguirCursor]);

  return (
    <svg
      ref={dibujo}
      viewBox={soloCabeza ? '4 0 64 54' : '0 0 72 92'}
      className={`mot ${className}`}
      data-estado={estado}
      data-gesto={gesto ?? undefined}
      aria-hidden="true"
    >
      <g className="mot-flotar">
        <g className="mot-gesto">
          {!soloCabeza && (
            <>
              <path className="mot-llama" d="M29 73 Q36 95 43 73 Z" />
              <path className="mot-llama-centro" d="M32.5 73 Q36 86 39.5 73 Z" />
              <rect className="mot-cuello" x="31" y="49" width="10" height="7" />
              <rect className="mot-cuerpo" x="22" y="54" width="28" height="21" rx="9.5" />
              <rect className="mot-brillo" x="27" y="57" width="18" height="3" rx="1.5" />
              <circle className="mot-pecho" cx="36" cy="67" r="3.4" />
            </>
          )}

          <g className="mot-cabeza">
            <g className="mot-antena">
              <line x1="36" y1="14" x2="36" y2="7" />
              <circle className="mot-luz" cx="36" cy="5.4" r="3.4" />
            </g>
            <rect className="mot-oreja" x="6.5" y="25" width="7" height="15" rx="3.5" />
            <rect className="mot-oreja" x="58.5" y="25" width="7" height="15" rx="3.5" />
            <rect className="mot-craneo" x="11" y="13" width="50" height="38" rx="15" />
            <rect className="mot-brillo" x="20" y="15.5" width="24" height="2.4" rx="1.2" />
            <rect className="mot-pantalla" x="17" y="20" width="38" height="26" rx="10.5" />

            <g className="mot-ojos">
              <g className="mot-mirada">
                <rect className="mot-ojo" x="25" y="26.5" width="6.5" height="10" rx="3.25" />
                <rect className="mot-ojo" x="40.5" y="26.5" width="6.5" height="10" rx="3.25" />
              </g>
            </g>
            <g className="mot-trazo mot-ojos-felices">
              <path d="M24 33 q4.2 -6.5 8.4 0" />
              <path d="M39.6 33 q4.2 -6.5 8.4 0" />
            </g>
            <g className="mot-trazo mot-ojos-tristes">
              <path d="M23.5 31 l7.5 -3.2" />
              <path d="M48.5 31 l-7.5 -3.2" />
              <path d="M27.6 33.6 v2.2" />
              <path d="M44.4 33.6 v2.2" />
            </g>
            <g className="mot-trazo mot-ojos-dormidos">
              <path d="M24 31.5 q4.2 3.6 8.4 0" />
              <path d="M39.6 31.5 q4.2 3.6 8.4 0" />
            </g>

            <path className="mot-trazo-solo mot-boca" d="M31.6 39.6 q4.4 3.2 8.8 0" />
            <path className="mot-trazo-solo mot-boca-triste" d="M31.6 41.6 q4.4 -3 8.8 0" />
            <rect className="mot-boca-hablar" x="31.6" y="37.6" width="8.8" height="4.8" rx="2.4" />
            <g className="mot-puntos">
              <circle cx="30.5" cy="40.4" r="1.5" />
              <circle cx="36" cy="40.4" r="1.5" />
              <circle cx="41.5" cy="40.4" r="1.5" />
            </g>
            <circle className="mot-mejilla" cx="21.8" cy="38.6" r="2.5" />
            <circle className="mot-mejilla" cx="50.2" cy="38.6" r="2.5" />
          </g>

          {!soloCabeza && (
            <>
              {/* Después de la cabeza: al saludar, la mano pasa por delante. */}
              <g className="mot-brazo mot-brazo-izq">
                <path d="M24 60 Q16 62 12.5 69" />
                <circle cx="12" cy="70.5" r="3.6" />
              </g>
              <g className="mot-brazo mot-brazo-der">
                <path d="M48 60 Q56 62 59.5 69" />
                <circle cx="60" cy="70.5" r="3.6" />
              </g>
              <g className="mot-chispas">
                <path className="mot-chispa" d="M5 13 l1.2 3 3 1.2 -3 1.2 -1.2 3 -1.2 -3 -3 -1.2 3 -1.2 Z" />
                <path className="mot-chispa" d="M66 6 l1.4 3.4 3.4 1.4 -3.4 1.4 -1.4 3.4 -1.4 -3.4 -3.4 -1.4 3.4 -1.4 Z" />
                <path className="mot-chispa" d="M69 42 l1 2.4 2.4 1 -2.4 1 -1 2.4 -1 -2.4 -2.4 -1 2.4 -1 Z" />
                <path className="mot-chispa" d="M2 48 l1 2.4 2.4 1 -2.4 1 -1 2.4 -1 -2.4 -2.4 -1 2.4 -1 Z" />
              </g>
              <g className="mot-zetas">
                <text className="mot-zeta" x="56" y="16" fontSize="9">z</text>
                <text className="mot-zeta" x="60" y="11" fontSize="11">z</text>
                <text className="mot-zeta" x="65" y="5" fontSize="13">Z</text>
              </g>
            </>
          )}
        </g>
      </g>
    </svg>
  );
};

export default Mot;
