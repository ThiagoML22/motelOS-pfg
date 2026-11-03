// Tema de la interfaz: claro, oscuro o el del sistema operativo. La preferencia es del puesto (localStorage), no de la
// persona: la ventanilla la comparte cada guardia. index.html la aplica antes de pintar para que no haya destello.

export type Preferencia = 'claro' | 'oscuro' | 'sistema';
export type Modo = 'claro' | 'oscuro';

const CLAVE = 'motelos.tema';
const EVENTO = 'motelos:tema';
const consultaOscuro = () => window.matchMedia('(prefers-color-scheme: dark)');

export const leerPreferencia = (): Preferencia => {
  try {
    const valor = localStorage.getItem(CLAVE);
    return valor === 'claro' || valor === 'oscuro' ? valor : 'sistema';
  } catch {
    return 'sistema';
  }
};

export const modoDe = (preferencia: Preferencia): Modo =>
  preferencia === 'sistema' ? (consultaOscuro().matches ? 'oscuro' : 'claro') : preferencia;

export const modoActual = (): Modo => (document.documentElement.dataset.theme === 'dark' ? 'oscuro' : 'claro');

const aplicar = (modo: Modo) => {
  document.documentElement.dataset.theme = modo === 'oscuro' ? 'dark' : 'light';
};

interface ViewTransition {
  ready: Promise<void>;
}
type DocumentoConTransicion = Document & { startViewTransition?: (cambio: () => void) => ViewTransition };

/**
 * Guarda la preferencia y cambia el tema. Si se indica el punto de origen (el centro de la lunita), la página nueva
 * aparece en un círculo que crece desde ahí; si el navegador no tiene View Transitions o el usuario pidió menos
 * movimiento, los colores se funden.
 */
export const elegirTema = (preferencia: Preferencia, origen?: { x: number; y: number }) => {
  try {
    if (preferencia === 'sistema') localStorage.removeItem(CLAVE);
    else localStorage.setItem(CLAVE, preferencia);
  } catch {
    // sin almacenamiento local el tema dura hasta recargar
  }
  const modo = modoDe(preferencia);
  const notificar = () => window.dispatchEvent(new CustomEvent(EVENTO, { detail: { preferencia, modo } }));
  if (modo === modoActual()) {
    notificar();
    return;
  }
  const doc = document as DocumentoConTransicion;
  const menosMovimiento = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (origen && doc.startViewTransition && !menosMovimiento) {
    const radio = Math.hypot(Math.max(origen.x, innerWidth - origen.x), Math.max(origen.y, innerHeight - origen.y));
    const transicion = doc.startViewTransition(() => aplicar(modo));
    void transicion.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${origen.x}px ${origen.y}px)`, `circle(${radio}px at ${origen.x}px ${origen.y}px)`] },
        { duration: 650, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', pseudoElement: '::view-transition-new(root)' },
      );
    });
  } else {
    const raiz = document.documentElement;
    raiz.classList.add('tema-en-transicion');
    aplicar(modo);
    window.setTimeout(() => raiz.classList.remove('tema-en-transicion'), 450);
  }
  notificar();
};

// Sigue los cambios del tema (de otra pantalla o del sistema operativo, si la preferencia es «sistema»).
export const alCambiarTema = (oyente: (modo: Modo, preferencia: Preferencia) => void): (() => void) => {
  const porEvento = (e: Event) => {
    const { modo, preferencia } = (e as CustomEvent<{ modo: Modo; preferencia: Preferencia }>).detail;
    oyente(modo, preferencia);
  };
  const porSistema = () => {
    if (leerPreferencia() === 'sistema') {
      const modo = modoDe('sistema');
      aplicar(modo);
      oyente(modo, 'sistema');
    }
  };
  window.addEventListener(EVENTO, porEvento);
  const consulta = consultaOscuro();
  consulta.addEventListener('change', porSistema);
  return () => {
    window.removeEventListener(EVENTO, porEvento);
    consulta.removeEventListener('change', porSistema);
  };
};
