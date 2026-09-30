import axios from 'axios';
import { Articulo, HabitacionConDetalles, Turno, TurnoResumen } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const api = {
  getHabitaciones: async (): Promise<HabitacionConDetalles[]> => {
    const response = await axios.get(`${API_URL}/habitaciones/`);
    return response.data;
  },
  
  createTurno: async (turno: Turno): Promise<Turno> => {
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
      cantidad
    });
    return response.data;
  },

  getResumen: async (turno_id: string): Promise<TurnoResumen> => {
    const response = await axios.get(`${API_URL}/turnos/${turno_id}/resumen`);
    return response.data;
  },

  cerrarTurno: async (turno_id: string, monto: number, medio_pago: string, comprobante_referencia: string) => {
    const response = await axios.post(`${API_URL}/turnos/${turno_id}/cerrar`, {
      monto,
      medio_pago,
      comprobante_referencia
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
  }
};
