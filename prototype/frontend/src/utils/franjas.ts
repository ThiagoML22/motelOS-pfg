// Tarifas especiales por día y franja (migración 014). La misma cuenta que services/franjas.py: acá solo sirve para
// dibujar el mapa y avisar antes de guardar; quien decide qué tarifa rige es el servidor.

const MINUTOS_DIA = 1440;
const MINUTOS_SEMANA = 7 * MINUTOS_DIA;
const DIAS = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];
export const DIAS_CORTOS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
export const TODOS_LOS_DIAS = 127;
export const COLORES_FRANJA = ['rgb(var(--viz-1))', 'rgb(var(--viz-2))', 'rgb(var(--viz-3))', '#7c3aed', '#be123c', '#0369a1'];

export interface Regla {
  dias: number; // máscara de días de comienzo: lunes = 1 ... domingo = 64
  desde: string; // «20:00» o «20:00:00»
  hasta: string;
}

export const horaCorta = (hora: string): string => hora.slice(0, 5);

const aMinutos = (hora: string): number => {
  const [h, m] = hora.split(':').map(Number);
  return h * 60 + (m || 0);
};

// Los minutos de la semana que cubre una regla (lunes 00:00 = 0). Lo que pasa del domingo vuelve al lunes.
const tramosSemana = ({ dias, desde, hasta }: Regla): [number, number][] => {
  const inicio = aMinutos(desde);
  const fin = aMinutos(hasta) <= inicio ? aMinutos(hasta) + MINUTOS_DIA : aMinutos(hasta);
  const tramos: [number, number][] = [];
  for (let dia = 0; dia < 7; dia++) {
    if (!(dias & (1 << dia))) continue;
    const a = dia * MINUTOS_DIA + inicio;
    const b = dia * MINUTOS_DIA + fin;
    if (b <= MINUTOS_SEMANA) tramos.push([a, b]);
    else tramos.push([a, MINUTOS_SEMANA], [0, b - MINUTOS_SEMANA]);
  }
  return tramos;
};

// Lo mismo, partido por filas del mapa: una noche ocupa el final de un día y el principio del siguiente.
export const tramosPorDia = (regla: Regla): { dia: number; inicio: number; fin: number }[] =>
  tramosSemana(regla).flatMap(([a, b]) => {
    const partes = [];
    for (let desde = a; desde < b; desde = (Math.floor(desde / MINUTOS_DIA) + 1) * MINUTOS_DIA) {
      const dia = Math.floor(desde / MINUTOS_DIA);
      partes.push({ dia, inicio: desde - dia * MINUTOS_DIA, fin: Math.min(b, (dia + 1) * MINUTOS_DIA) - dia * MINUTOS_DIA });
    }
    return partes;
  });

// El primer minuto en el que dos reglas se pisan, o null. Una que termina justo cuando empieza la otra no se pisa.
export const primerCruce = (a: Regla, b: Regla): number | null => {
  const cruces = tramosSemana(a).flatMap((x) =>
    tramosSemana(b)
      .filter((y) => Math.max(x[0], y[0]) < Math.min(x[1], y[1]))
      .map((y) => Math.max(x[0], y[0])),
  );
  return cruces.length ? Math.min(...cruces) : null;
};

export const momentoTexto = (minuto: number): string => {
  const dia = Math.floor(minuto / MINUTOS_DIA);
  const resto = minuto % MINUTOS_DIA;
  return `${DIAS[dia]} a las ${String(Math.floor(resto / 60)).padStart(2, '0')}:${String(resto % 60).padStart(2, '0')}`;
};

export const diasTexto = (dias: number): string => {
  if (dias === TODOS_LOS_DIAS) return 'todos los días';
  const elegidos = [0, 1, 2, 3, 4, 5, 6].filter((d) => dias & (1 << d));
  if (elegidos.length === 0) return 'ningún día';
  const [primero, ultimo] = [elegidos[0], elegidos[elegidos.length - 1]];
  if (elegidos.length >= 3 && ultimo - primero === elegidos.length - 1) return `de ${DIAS[primero]} a ${DIAS[ultimo]}`;
  const nombres = elegidos.map((d) => DIAS[d]);
  return nombres.length === 1 ? nombres[0] : `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`;
};

export const reglaTexto = (regla: Regla): string =>
  horaCorta(regla.desde) === horaCorta(regla.hasta)
    ? `${diasTexto(regla.dias)}, todo el día`
    : `${diasTexto(regla.dias)} de ${horaCorta(regla.desde)} a ${horaCorta(regla.hasta)}`;
