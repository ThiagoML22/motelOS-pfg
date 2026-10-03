const moneyFormatter = new Intl.NumberFormat('es-AR', {
  style: 'currency',
  currency: 'ARS',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

export const formatMoney = (value: number): string => moneyFormatter.format(value);

const pad = (n: number): string => n.toString().padStart(2, '0');

export const formatDuration = (ms: number): string => {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
};

export const formatClock = (date: Date): string =>
  `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;

// El backend puede devolver instantes UTC sin sufijo de zona horaria.
export const parseUtc = (iso: string): Date =>
  new Date(/(Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`);

const dateTimeFormatter = new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'medium' });

export const formatDateTime = (iso: string): string => dateTimeFormatter.format(parseUtc(iso));

export const formatRoomNumber = (numero: number): string => `Hab. ${pad(numero)}`;
