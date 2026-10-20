import { CategoriaArqueo } from '../types';

// Importe escrito por el operador, con como máximo dos decimales. Admite «1.500,50» (formato argentino),
// «1.500» (punto de miles) y «1500.5» (punto decimal del teclado numérico). Vacío = 0; inválido = null.
export const aImporte = (texto: string): number | null => {
  let limpio = texto.trim();
  if (limpio.includes(',')) limpio = limpio.replace(/\./g, '').replace(',', '.');
  else if (/^\d{1,3}(\.\d{3})+$/.test(limpio)) limpio = limpio.replace(/\./g, '');
  if (limpio === '') return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(limpio)) return null;
  return Number(limpio);
};

export const redondear = (valor: number): number => Math.round(valor * 100) / 100;

export const CATEGORIA_META: Record<CategoriaArqueo, { label: string; clase: string; descripcion: string }> = {
  Correcto: {
    label: 'Correcto',
    clase: 'bg-libre-soft text-libre',
    descripcion: 'Lo declarado coincide con lo registrado por el sistema.',
  },
  Faltante: {
    label: 'Faltante',
    clase: 'bg-danger-soft text-danger',
    descripcion: 'Lo declarado es menor que lo registrado por el sistema.',
  },
  Sobrante: {
    label: 'Sobrante',
    clase: 'bg-warn-soft text-warn',
    descripcion: 'Lo declarado es mayor que lo registrado por el sistema.',
  },
};

export const NOMBRE_FRANJA: Record<string, string> = {
  '06:00': 'Mañana (06:00–14:00)',
  '14:00': 'Tarde (14:00–22:00)',
  '22:00': 'Noche (22:00–06:00)',
};

export const formatPorcentaje = (fraccion: number): string =>
  `${(fraccion * 100).toLocaleString('es-AR', { maximumFractionDigits: 1 })} %`;
