/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      colors: {
        bg: token('bg'),
        surface: { DEFAULT: token('surface'), 2: token('surface-2') },
        line: { DEFAULT: token('line'), strong: token('line-strong') },
        ink: token('ink'),
        muted: token('muted'),
        subtle: token('subtle'),
        accent: {
          DEFAULT: token('accent'),
          hover: token('accent-hover'),
          soft: token('accent-soft'),
          fg: token('accent-fg'),
        },
        libre: { DEFAULT: token('libre'), soft: token('libre-soft') },
        ocupada: { DEFAULT: token('ocupada'), soft: token('ocupada-soft') },
        limpieza: { DEFAULT: token('limpieza'), soft: token('limpieza-soft') },
        mant: { DEFAULT: token('mant'), soft: token('mant-soft') },
        warn: { DEFAULT: token('warn'), soft: token('warn-soft') },
        danger: { DEFAULT: token('danger'), soft: token('danger-soft') },
        viz: { 1: token('viz-1'), 2: token('viz-2'), 3: token('viz-3'), grid: token('viz-grid'), axis: token('viz-axis') },
      },
      boxShadow: {
        panel: '0 8px 24px rgb(15 23 42 / 0.12)',
        lift: '0 4px 14px rgb(15 23 42 / 0.08)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'pop-in': {
          from: { opacity: '0', transform: 'translateY(6px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'toast-in': {
          from: { opacity: '0', transform: 'translateX(-12px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
        // Tarjetas de la grilla y filas: entrada escalonada (el retraso lo pone cada elemento).
        'tarjeta-in': {
          from: { opacity: '0', transform: 'translateY(10px) scale(0.985)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        // Una habitación que cambió de estado se ilumina un momento con el acento.
        destello: {
          '0%': { boxShadow: '0 0 0 0 rgb(var(--accent) / 0.55)' },
          '60%': { boxShadow: '0 0 0 6px rgb(var(--accent) / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(var(--accent) / 0)' },
        },
        // Barras de los gráficos que crecen desde la base y líneas que se dibujan.
        crecer: { from: { transform: 'scaleY(0)' }, to: { transform: 'scaleY(1)' } },
        dibujar: { from: { strokeDashoffset: '1' }, to: { strokeDashoffset: '0' } },
        // Brillo que recorre los esqueletos de carga.
        brillo: { from: { backgroundPosition: '200% 0' }, to: { backgroundPosition: '-200% 0' } },
        // Latido suave del cronómetro de un turno excedido.
        latido: { '0%, 100%': { opacity: '1' }, '50%': { opacity: '0.55' } },
        // El botón del asistente invita a usarlo con una onda.
        llamado: {
          '0%': { boxShadow: '0 0 0 0 rgb(var(--accent) / 0.45)' },
          '70%': { boxShadow: '0 0 0 14px rgb(var(--accent) / 0)' },
          '100%': { boxShadow: '0 0 0 0 rgb(var(--accent) / 0)' },
        },
      },
      // Las entradas usan `backwards`: si el estado final quedara aplicado, el elemento encerraría a los diálogos
      // (`fixed`) que tiene adentro y anularía su propio transform al pasar el mouse.
      animation: {
        'fade-in': 'fade-in 160ms ease-out backwards',
        'pop-in': 'pop-in 200ms cubic-bezier(0.2, 0.8, 0.2, 1) backwards',
        'toast-in': 'toast-in 220ms cubic-bezier(0.2, 0.8, 0.2, 1) both',
        'tarjeta-in': 'tarjeta-in 320ms cubic-bezier(0.2, 0.8, 0.2, 1) backwards',
        destello: 'destello 1.4s ease-out',
        crecer: 'crecer 650ms cubic-bezier(0.2, 0.8, 0.2, 1) both',
        dibujar: 'dibujar 900ms ease-out both',
        brillo: 'brillo 1.6s linear infinite',
        latido: 'latido 1.6s ease-in-out infinite',
        llamado: 'llamado 1.8s ease-out 3',
      },
    },
  },
  plugins: [],
}
