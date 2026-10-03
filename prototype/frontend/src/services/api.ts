import axios from 'axios';
import {
  Articulo,
  ConstanciaCobro,
  HabitacionConDetalles,
  MedioPago,
  Turno,
  TurnoCreate,
  TurnoResumen,
} from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const getErrorMessage = (error: unknown, fallback: string): string => {
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

export const api = {
  getHabitaciones: async (): Promise<HabitacionConDetalles[]> => {
    const response = await axios.get(`${API_URL}/habitaciones/`);
    return response.data;
  },

  createTurno: async (turno: TurnoCreate): Promise<Turno> => {
    const response = await axios.post(`${API_URL}/turnos/`, turno);
    return response.data;
  },

  getArticulos: async (): Promise<Articulo[]> => {
    const response = await axios.get(`${API_URL}/articulos/`);
    return response.data;
  },

  createArticulo: async (articulo: Omit<Articulo, 'id'>): Promise<Articulo> => {
    const response = await axios.post(`${API_URL}/articulos/`, articulo);
    return response.data;
  },

  addConsumo: async (turno_id: string, articulo_id: number, cantidad: number) => {
    const response = await axios.post(`${API_URL}/turnos/${turno_id}/consumos`, {
      articulo_id,
      cantidad,
    });
    return response.data;
  },

  getResumen: async (turno_id: string): Promise<TurnoResumen> => {
    const response = await axios.get(`${API_URL}/turnos/${turno_id}/resumen`);
    return response.data;
  },

  // El backend registra un pago por medio; la interfaz liquida el total con un único medio.
  cerrarTurno: async (
    turno_id: string,
    monto: number,
    medio_pago: MedioPago,
    comprobante_referencia?: string,
  ): Promise<ConstanciaCobro> => {
    const response = await axios.post(`${API_URL}/turnos/${turno_id}/cerrar`, {
      pagos: [{ monto, medio_pago, comprobante_referencia: comprobante_referencia || null }],
    });
    return response.data;
  },

  liberarHabitacion: async (habitacion_id: number) => {
    const response = await axios.patch(`${API_URL}/habitaciones/${habitacion_id}/liberar`);
    return response.data;
  },

  updateHabitacionEstado: async (habitacion_id: number, estado: string) => {
    const response = await axios.patch(`${API_URL}/habitaciones/${habitacion_id}/estado`, { estado });
    return response.data;
  },
};
