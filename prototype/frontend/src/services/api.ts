import axios from 'axios';
import {
  Actividad,
  Arqueo,
  ArqueoDetalle,
  Articulo,
  ArticuloCambios,
  CategoriaActividad,
  ConserjeAlta,
  ConstanciaCobro,
  DeclaracionCaja,
  Establecimiento,
  EstablecimientoAlta,
  EstablecimientoDatos,
  EstablecimientoResumen,
  FondoCambio,
  Guardia,
  HabitacionConDetalles,
  HabitacionConfiguracion,
  MedioPago,
  MetricasCaja,
  OperadorEstado,
  Sesion,
  Tarifa,
  TarifaDatos,
  Turno,
  TurnoCreate,
  TurnoResumen,
} from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

// RNF-04: la sesión viaja en una cookie httpOnly que el navegador envía solo (withCredentials); este código
// nunca la lee. El encabezado X-Requested-With es la marca de la aplicación que el backend exige en las
// peticiones que modifican datos (protección contra CSRF).
const http = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: { 'X-Requested-With': 'motelos' },
});

let alVencerSesion: (() => void) | null = null;

// La aplicación registra qué hacer cuando la API responde 401 (sesión vencida o cerrada en otro lado).
export const onSesionVencida = (handler: () => void) => {
  alVencerSesion = handler;
};

// --- RNF-09: recuperación al reconectar ------------------------------------------------------------------------
// Cualquier petición sin respuesta marca la ventanilla sin conexión; cualquier respuesta, conectada. Durante el corte
// no se envían operaciones (abrir, cobrar, cargar): se rechazan antes de salir, para que nada quede a medias ni se
// duplique al volver. Los cronómetros siguen en el servidor: al reconectar la grilla trae los minutos que él calcula.
export const EVENTO_RECONECTADO = 'motelos:reconectado';
const SIN_CONEXION = 'Sin conexión con el servidor: la operación no se envió. Reintente cuando vuelva la conexión.';
const METODOS_QUE_MODIFICAN = new Set(['post', 'put', 'patch', 'delete']);
const URL_SALUD = API_URL.replace(/\/api\/v1\/?$/, '') + '/health';

let conectado = true;
const oyentesConexion = new Set<(conectado: boolean) => void>();

const marcarConexion = (valor: boolean) => {
  if (valor === conectado) return;
  conectado = valor;
  oyentesConexion.forEach((oyente) => oyente(valor));
};

export const onCambioConexion = (oyente: (conectado: boolean) => void): (() => void) => {
  oyentesConexion.add(oyente);
  return () => oyentesConexion.delete(oyente);
};

export const estaConectado = (): boolean => conectado;

export const marcarSinConexion = () => marcarConexion(false);

// Sondeo liviano del servidor (sin sesión ni interceptores) para detectar la vuelta de la conexión.
export const sondearServidor = async (): Promise<boolean> => {
  try {
    await axios.get(URL_SALUD, { timeout: 2000 });
    marcarConexion(true);
    return true;
  } catch {
    return false;
  }
};

class OperacionSinConexion extends Error {}

http.interceptors.request.use((config) => {
  const url = config.url ?? '';
  if (!conectado && METODOS_QUE_MODIFICAN.has((config.method ?? 'get').toLowerCase()) && !url.startsWith('/auth/')) {
    return Promise.reject(new OperacionSinConexion(SIN_CONEXION));
  }
  return config;
});

http.interceptors.response.use(
  (response) => {
    marcarConexion(true);
    return response;
  },
  (error) => {
    const url: string = error?.config?.url ?? '';
    if (axios.isAxiosError(error)) {
      marcarConexion(Boolean(error.response));
      if (error.response?.status === 401 && !url.startsWith('/auth/')) {
        alVencerSesion?.();
      }
    }
    return Promise.reject(error);
  },
);

export const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof OperacionSinConexion) return error.message;
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'No se pudo conectar con el servidor.';
    const detail = error.response.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      return detail.map((d: { msg?: string }) => d.msg ?? '').filter(Boolean).join('. ') || fallback;
    }
  }
  return fallback;
};

export const esConflicto = (error: unknown): boolean => axios.isAxiosError(error) && error.response?.status === 409;

export const api = {
  // --- Sesión ---
  // El establecimiento es el código del motel (multiinquilino); vacío, el predeterminado de la instalación.
  login: async (establecimiento: string, usuario: string, clave: string): Promise<Sesion> =>
    (await http.post('/auth/login', { establecimiento: establecimiento || null, usuario, clave })).data,

  logout: async (): Promise<void> => {
    await http.post('/auth/logout');
  },

  getSesion: async (): Promise<Sesion> => (await http.get('/auth/sesion')).data,

  // --- Guardias y cierre de caja ciego (RF-08) ---
  abrirGuardia: async (): Promise<Guardia> => (await http.post('/guardias/')).data,

  confirmarArqueo: async (declaracion: DeclaracionCaja): Promise<Arqueo> =>
    (await http.post('/guardias/actual/arqueo', declaracion)).data,

  // --- Panel de la gerencia (RF-09) ---
  getArqueos: async (filtro: { desde?: string; hasta?: string; operador_id?: number }): Promise<Arqueo[]> =>
    (await http.get('/arqueos/', { params: filtro })).data,

  getArqueo: async (id: number): Promise<ArqueoDetalle> => (await http.get(`/arqueos/${id}`)).data,

  getMetricas: async (filtro: { desde?: string; hasta?: string }): Promise<MetricasCaja> =>
    (await http.get('/arqueos/metricas', { params: filtro })).data,

  getOperadores: async (): Promise<OperadorEstado[]> => (await http.get('/operadores/')).data,

  getGuardiaActual: async (): Promise<Guardia | null> => (await http.get('/guardias/actual')).data,

  cierreSupervisado: async (guardiaId: number, declaracion: DeclaracionCaja & { observacion: string }): Promise<Arqueo> =>
    (await http.post(`/arqueos/guardias/${guardiaId}/cierre-supervisado`, declaracion)).data,

  // --- Panel de configuración de la gerencia (RF-11) ---
  getTarifas: async (): Promise<Tarifa[]> => (await http.get('/configuracion/tarifas')).data,

  nuevaTarifa: async (tarifa: TarifaDatos): Promise<Tarifa> => (await http.post('/configuracion/tarifas', tarifa)).data,

  getFondoCambio: async (): Promise<FondoCambio> => (await http.get('/configuracion/caja')).data,

  setFondoCambio: async (fondo_cambio: number): Promise<FondoCambio> =>
    (await http.patch('/configuracion/caja', { fondo_cambio })).data,

  getArticulosConfiguracion: async (): Promise<Articulo[]> => (await http.get('/configuracion/articulos')).data,

  configurarArticulo: async (id: number, cambios: ArticuloCambios): Promise<Articulo> =>
    (await http.patch(`/configuracion/articulos/${id}`, cambios)).data,

  getHabitacionesConfiguracion: async (): Promise<HabitacionConfiguracion[]> =>
    (await http.get('/configuracion/habitaciones')).data,

  altaHabitacion: async (numero: number): Promise<HabitacionConfiguracion> =>
    (await http.post('/configuracion/habitaciones', { numero })).data,

  configurarHabitacion: async (
    id: number,
    cambios: { numero?: number; activa?: boolean },
  ): Promise<HabitacionConfiguracion> => (await http.patch(`/configuracion/habitaciones/${id}`, cambios)).data,

  altaConserje: async (conserje: ConserjeAlta): Promise<OperadorEstado> => (await http.post('/operadores/', conserje)).data,

  setOperadorActivo: async (id: number, activo: boolean): Promise<OperadorEstado> =>
    (await http.patch(`/operadores/${id}`, { activo })).data,

  // --- Datos del establecimiento y registro de actividad (gerencia) ---
  getEstablecimiento: async (): Promise<Establecimiento> => (await http.get('/configuracion/establecimiento')).data,

  setEstablecimiento: async (datos: EstablecimientoDatos): Promise<Establecimiento> =>
    (await http.patch('/configuracion/establecimiento', datos)).data,

  getActividad: async (filtro: { categoria?: CategoriaActividad; pendientes?: boolean }): Promise<Actividad[]> =>
    (await http.get('/configuracion/actividad', { params: filtro })).data,

  getActividadPendiente: async (): Promise<number> => (await http.get('/configuracion/actividad/pendientes')).data.pendientes,

  // Sin ids marca todas las pendientes. Devuelve cuántas quedan.
  revisarActividad: async (ids?: number[]): Promise<number> =>
    (await http.post('/configuracion/actividad/revision', { ids: ids ?? null })).data.pendientes,

  // --- Comprobante del arqueo en PDF (RF-10) ---
  // El conserje descarga el de su propio arqueo; la gerencia, el de cualquiera.
  descargarComprobante: async (arqueoId: number, comoGerencia: boolean): Promise<void> => {
    const ruta = comoGerencia ? `/arqueos/${arqueoId}/comprobante.pdf` : `/guardias/arqueos/${arqueoId}/comprobante.pdf`;
    const datos: Blob = (await http.get(ruta, { responseType: 'blob' })).data;
    const url = URL.createObjectURL(datos);
    const enlace = document.createElement('a');
    enlace.href = url;
    enlace.download = `arqueo-${arqueoId}.pdf`;
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },

  // --- Plataforma (multiinquilino) ---
  getEstablecimientos: async (): Promise<EstablecimientoResumen[]> => (await http.get('/plataforma/establecimientos')).data,

  altaEstablecimiento: async (datos: EstablecimientoAlta): Promise<Establecimiento> =>
    (await http.post('/plataforma/establecimientos', datos)).data,

  setEstablecimientoActivo: async (id: number, activo: boolean): Promise<Establecimiento> =>
    (await http.patch(`/plataforma/establecimientos/${id}`, { activo })).data,

  // --- Operación de la ventanilla ---
  getHabitaciones: async (): Promise<HabitacionConDetalles[]> => (await http.get('/habitaciones/')).data,

  createTurno: async (turno: TurnoCreate): Promise<Turno> => (await http.post('/turnos/', turno)).data,

  getArticulos: async (): Promise<Articulo[]> => (await http.get('/articulos/')).data,

  createArticulo: async (articulo: Omit<Articulo, 'id'>): Promise<Articulo> =>
    (await http.post('/articulos/', articulo)).data,

  // Unidades que llegan de un artículo existente; queda en el registro de la gerencia.
  reponerArticulo: async (id: number, cantidad: number): Promise<Articulo> =>
    (await http.post(`/articulos/${id}/reposicion`, { cantidad })).data,

  addConsumo: async (turno_id: string, articulo_id: number, cantidad: number) =>
    (await http.post(`/turnos/${turno_id}/consumos`, { articulo_id, cantidad })).data,

  getResumen: async (turno_id: string): Promise<TurnoResumen> => (await http.get(`/turnos/${turno_id}/resumen`)).data,

  // El backend registra un pago por medio; la interfaz liquida el total con un único medio.
  cerrarTurno: async (
    turno_id: string,
    monto: number,
    medio_pago: MedioPago,
    comprobante_referencia?: string,
  ): Promise<ConstanciaCobro> =>
    (
      await http.post(`/turnos/${turno_id}/cerrar`, {
        pagos: [{ monto, medio_pago, comprobante_referencia: comprobante_referencia || null }],
      })
    ).data,

  liberarHabitacion: async (habitacion_id: number) => (await http.patch(`/habitaciones/${habitacion_id}/liberar`)).data,

  updateHabitacionEstado: async (habitacion_id: number, estado: string) =>
    (await http.patch(`/habitaciones/${habitacion_id}/estado`, { estado })).data,
};
