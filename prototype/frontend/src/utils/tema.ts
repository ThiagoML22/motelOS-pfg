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
  finished: Promise<void>;
}
type DocumentoConTransicion = Document & { startViewTransition?: (cambio: () => void) => ViewTransition };

// Espacio que deja el borde difuminado de la onda: el radio final lo supera para que termine fuera de la pantalla.
const BORDE_DE_LA_ONDA = 220;
const ESTRELLAS = 26;
const DURACION_MS = 850;

// Resplandor que viaja con el borde de la onda (cálido si amanece, frío si anochece) y, al anochecer, estrellas que se
// encienden a medida que la noche llega hasta ellas.
const crearResplandor = (modo: Modo, x: number, y: number, radio: number): HTMLElement => {
  const resplandor = document.createElement('div');
  resplandor.className = `tema-resplandor tema-resplandor-${modo}`;
  resplandor.setAttribute('aria-hidden', 'true');
  if (modo === 'oscuro') {
    for (let i = 0; i < ESTRELLAS; i += 1) {
      const estrella = document.createElement('i');
      const left = Math.random() * innerWidth;
      const top = Math.random() * innerHeight;
      estrella.style.left = `${left}px`;
      estrella.style.top = `${top}px`;
      estrella.style.animationDelay = `${(Math.hypot(left - x, top - y) / radio) * DURACION_MS * 0.7}ms`;
      resplandor.appendChild(estrella);
    }
  }
  document.body.appendChild(resplandor);
  return resplandor;
};

/**
 * Guarda la preferencia y cambia el tema. La página nueva aparece en una onda de borde suave que nace del origen (el
 * centro del botón del tema o, si no se indica, donde esté ese botón). Si el navegador no tiene View Transitions o el
 * usuario pidió menos movimiento, los colores se funden.
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
  const raiz = document.documentElement;
  if (doc.startViewTransition && !menosMovimiento) {
    const caja = origen ? null : document.querySelector('.tema-boton')?.getBoundingClientRect();
    const x = origen?.x ?? (caja ? caja.left + caja.width / 2 : innerWidth / 2);
    const y = origen?.y ?? (caja ? caja.top + caja.height / 2 : 0);
    const radio = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + BORDE_DE_LA_ONDA;
    raiz.style.setProperty('--tema-x', `${x}px`);
    raiz.style.setProperty('--tema-y', `${y}px`);
    raiz.style.setProperty('--tema-radio', `${radio}px`);
    raiz.style.setProperty('--tema-duracion', `${DURACION_MS}ms`);
    let resplandor: HTMLElement | null = null;
    // La foto de la página vieja se toma antes de este cambio: el ícono del botón también cambia recién acá.
    const transicion = doc.startViewTransition(() => {
      aplicar(modo);
      resplandor = crearResplandor(modo, x, y, radio);
      notificar();
    });
    transicion.ready.catch(() => undefined);
    void transicion.finished.finally(() => resplandor?.remove());
  } else {
    raiz.classList.add('tema-en-transicion');
    aplicar(modo);
    window.setTimeout(() => raiz.classList.remove('tema-en-transicion'), 450);
    notificar();
  }
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
