import { useEffect, useRef, useState } from 'react';
import { EVENTO_RECONECTADO, marcarSinConexion, onCambioConexion, sondearServidor, estaConectado } from '../services/api';

// RNF-09: mientras no hay conexión se sondea el servidor cada 2 s, de modo que la vuelta se detecta y la ventanilla
// recupera su estado dentro de los 5 s del criterio. Con conexión se sondea cada 5 s: así el corte se detecta aunque
// la vista abierta no haga peticiones (por ejemplo, la configuración).
const SONDEO_MS = 2000;
const SONDEO_CONECTADO_MS = 5000;

export interface EstadoConexion {
  conectado: boolean;
  // Momento (ms) en que se perdió la conexión, para mostrarlo en el aviso.
  sinConexionDesde: number | null;
  reintentar: () => void;
}

export function useConexion(alReconectar: () => Promise<void>): EstadoConexion {
  const [conectado, setConectado] = useState(estaConectado());
  const [sinConexionDesde, setSinConexionDesde] = useState<number | null>(null);
  const alReconectarRef = useRef(alReconectar);
  alReconectarRef.current = alReconectar;

  useEffect(() => {
    const quitar = onCambioConexion((valor) => {
      setConectado(valor);
      setSinConexionDesde(valor ? null : Date.now());
      if (valor) {
        // Trae de nuevo la sesión y la grilla, y avisa a las vistas abiertas para que recarguen sus datos.
        void alReconectarRef.current().finally(() => window.dispatchEvent(new Event(EVENTO_RECONECTADO)));
      }
    });
    // El navegador avisa el corte de la red local antes de que falle una petición.
    const alCortarse = () => marcarSinConexion();
    const alVolver = () => void sondearServidor();
    window.addEventListener('offline', alCortarse);
    window.addEventListener('online', alVolver);
    return () => {
      quitar();
      window.removeEventListener('offline', alCortarse);
      window.removeEventListener('online', alVolver);
    };
  }, []);

  useEffect(() => {
    const intervalo = setInterval(() => void sondearServidor(), conectado ? SONDEO_CONECTADO_MS : SONDEO_MS);
    return () => clearInterval(intervalo);
  }, [conectado]);

  return { conectado, sinConexionDesde, reintentar: () => void sondearServidor() };
}
