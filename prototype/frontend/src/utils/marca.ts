// Color de marca de cada motel (migración 009): reemplaza el acento azul de MotelOS en claro y en oscuro. Se calculan
// las variantes con contraste suficiente (AA, 4,5:1) contra la superficie de cada tema, así un color muy claro o muy
// oscuro igual se lee en botones y enlaces.

type Rgb = [number, number, number];

const ID_ESTILO = 'motelos-marca';
const BLANCO: Rgb = [255, 255, 255];
const SUPERFICIE_OSCURA: Rgb = [16, 23, 37];
const FONDO_OSCURO: Rgb = [9, 14, 24];

export const COLORES_SUGERIDOS = [
  { nombre: 'Azul MotelOS', hex: '#244473' },
  { nombre: 'Bordó', hex: '#9f1239' },
  { nombre: 'Violeta', hex: '#6d28d9' },
  { nombre: 'Verde azulado', hex: '#0f766e' },
  { nombre: 'Esmeralda', hex: '#047857' },
  { nombre: 'Ámbar', hex: '#b45309' },
  { nombre: 'Rosa', hex: '#be185d' },
  { nombre: 'Grafito', hex: '#334155' },
];

const aRgb = (hex: string): Rgb | null => {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const luminancia = ([r, g, b]: Rgb): number => {
  const canal = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b);
};

export const contraste = (a: Rgb, b: Rgb): number => {
  const [l1, l2] = [luminancia(a), luminancia(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
};

const mezclar = (a: Rgb, b: Rgb, t: number): Rgb => a.map((v, i) => Math.round(v + (b[i] - v) * t)) as Rgb;

// Acerca el color a `hacia` hasta lograr el contraste pedido contra `fondo`.
const ajustar = (color: Rgb, fondo: Rgb, hacia: Rgb, minimo: number): Rgb => {
  let actual = color;
  for (let t = 0.05; contraste(actual, fondo) < minimo && t <= 1; t += 0.05) actual = mezclar(color, hacia, t);
  return actual;
};

const canales = (c: Rgb) => c.join(' ');

export const tokensDeMarca = (hex: string) => {
  const base = aRgb(hex);
  if (!base) return null;
  const claro = ajustar(base, BLANCO, [0, 0, 0], 4.5);
  const oscuro = ajustar(base, SUPERFICIE_OSCURA, BLANCO, 4.5);
  return {
    claro: {
      accent: canales(claro),
      hover: canales(mezclar(claro, [0, 0, 0], 0.18)),
      soft: canales(mezclar(claro, BLANCO, 0.9)),
      fg: '255 255 255',
    },
    oscuro: {
      accent: canales(oscuro),
      hover: canales(mezclar(oscuro, BLANCO, 0.2)),
      soft: canales(mezclar(oscuro, SUPERFICIE_OSCURA, 0.8)),
      fg: canales(FONDO_OSCURO),
    },
  };
};

// Aplica el color (o vuelve al azul de MotelOS con null) en toda la interfaz, en ambos temas.
export const aplicarMarca = (hex: string | null | undefined) => {
  const tokens = hex ? tokensDeMarca(hex) : null;
  let estilo = document.getElementById(ID_ESTILO) as HTMLStyleElement | null;
  if (!tokens) {
    estilo?.remove();
    return;
  }
  if (!estilo) {
    estilo = document.createElement('style');
    estilo.id = ID_ESTILO;
    document.head.appendChild(estilo);
  }
  const bloque = (t: typeof tokens.claro) =>
    `--accent: ${t.accent}; --accent-hover: ${t.hover}; --accent-soft: ${t.soft}; --accent-fg: ${t.fg};`;
  estilo.textContent = `:root { ${bloque(tokens.claro)} } :root[data-theme='dark'] { ${bloque(tokens.oscuro)} }`;
};

// --- Alertas sonoras de la ventanilla ---------------------------------------------------------------------------

let audio: AudioContext | null = null;

// Dos tonos cortos (Web Audio, sin archivos): más agudo para «excedido» que para «por vencer».
export const sonarAviso = (tipo: 'por_vencer' | 'excedido' = 'excedido') => {
  try {
    const Contexto = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Contexto) return;
    audio ??= new Contexto();
    const notas = tipo === 'excedido' ? [880, 660] : [523, 659];
    notas.forEach((frecuencia, i) => {
      const osc = audio!.createOscillator();
      const ganancia = audio!.createGain();
      const inicio = audio!.currentTime + i * 0.18;
      osc.type = 'sine';
      osc.frequency.value = frecuencia;
      ganancia.gain.setValueAtTime(0.0001, inicio);
      ganancia.gain.exponentialRampToValueAtTime(0.25, inicio + 0.02);
      ganancia.gain.exponentialRampToValueAtTime(0.0001, inicio + 0.16);
      osc.connect(ganancia).connect(audio!.destination);
      osc.start(inicio);
      osc.stop(inicio + 0.18);
    });
  } catch {
    // sin audio disponible: el aviso visual de la tarjeta alcanza
  }
};
