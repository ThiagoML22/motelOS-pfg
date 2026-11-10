import axios from 'axios';
import {
  Actividad,
  Arqueo,
  ArqueoDetalle,
  Articulo,
  ArticuloCambios,
  Categoria,
  CategoriaActividad,
  CategoriaAlta,
  Franja,
  FranjaAlta,
  FranjaCambio,
  CategoriaDatos,
  ConserjeAlta,
  ConstanciaCobro,
  DeclaracionCaja,
  Establecimiento,
  EstablecimientoAlta,
  EstablecimientoDatos,
  EstablecimientoResumen,
  EstadiaCliente,
  EscenarioGemelo,
  FondoCambio,
  Guardia,
  HabitacionConDetalles,
  HabitacionConfiguracion,
  IntegridadComprobantes,
  LineaDeTiempoDatos,
  MarcaPublica,
  MedioPago,
  MetricasCaja,
  MotivoPerdida,
  Novedad,
  OperadorEstado,
  Pedido,
  PedidoVentanilla,
  Perfil,
  ProximaLibre,
  ResumenCategoria,
  ResultadoGemelo,
  ResumenMes,
  RespuestaAsistente,
  Sesion,
  SugeridoPedido,
  Tablero,
  Tarifa,
  TarifaDatos,
  TicketCliente,
  Turno,
  TurnoCreate,
  TurnoResumen,
  VerificacionComprobante,
  Arreglo,
  ConteoPrenda,
  MotivoTraslado,
  MovimientoRopaHecho,
  PantallaTraspaso,
  Prenda,
  RopaContada,
  RubroArreglo,
  TableroOperacion,
  TipoArreglo,
  TipoMovimientoRopa,
} from '../types';

// Desde otro equipo de la red (el celular de un cliente), «localhost» sería ese equipo: se usa la dirección de la página.
const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1').replace('localhost', window.location.hostname);

// RNF-04: la sesión viaja en una cookie httpOnly que el navegador envía solo (withCredentials); este código
// nunca la lee. El encabezado X-Requested-With es la marca de la aplicación que el backend exige en las
// peticiones que modifican datos (protección contra CSRF).
const http = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: { 'X-Requested-With': 'motelos' },
  // RNF-09: una petición colgada (el servidor aceptó la conexión y no responde) también cuenta como corte.
  timeout: 15000,
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

// Sondeo liviano del servidor (sin sesión ni interceptores). Detecta el corte aunque la vista abierta no haga
// peticiones, y la vuelta de la conexión.
export const sondearServidor = async (): Promise<boolean> => {
  try {
    await axios.get(URL_SALUD, { timeout: 2500 });
    marcarConexion(true);
    return true;
  } catch {
    marcarConexion(false);
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

// Guarda un archivo generado (PDF, CSV) con el diálogo de descarga del navegador.
export const descargar = (datos: Blob, nombre: string) => {
  const url = URL.createObjectURL(datos);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const esConflicto = (error: unknown): boolean => axios.isAxiosError(error) && error.response?.status === 409;

// La petición no llegó a tener respuesta (corte, servidor caído o tiempo agotado): no dice nada de la sesión.
export const esSinRespuesta = (error: unknown): boolean => axios.isAxiosError(error) && !error.response;

export const api = {
  // --- Sesión ---
  // El establecimiento es el código del motel (multiinquilino); vacío, el predeterminado de la instalación.
  login: async (establecimiento: string, usuario: string, clave: string): Promise<Sesion> =>
    (await http.post('/auth/login', { establecimiento: establecimiento || null, usuario, clave })).data,

  logout: async (): Promise<void> => {
    await http.post('/auth/logout');
  },

  getSesion: async (): Promise<Sesion> => (await http.get('/auth/sesion')).data,

  // Nombre y apariencia del motel para la pantalla de ingreso (sin sesión). null si el código no existe.
  getMarca: async (codigo: string): Promise<MarcaPublica | null> => {
    try {
      return (await http.get('/auth/marca', { params: { codigo } })).data;
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 404) return null;
      throw err;
    }
  },

  // --- El cliente en su habitación (migración 013): sin sesión, con el enlace de su ticket ---
  getEstadiaCliente: async (token: string): Promise<EstadiaCliente> => (await http.get(`/cliente/${token}`)).data,

  pedirCliente: async (token: string, pedido: { tipo: string; articulo_id?: number; cantidad?: number; minutos?: number; medio_pago?: string }) =>
    (await http.post(`/cliente/${token}/pedidos`, pedido)).data,

  pedirCarrito: async (token: string, lineas: { articulo_id: number; cantidad: number }[]) =>
    (await http.post(`/cliente/${token}/carrito`, { lineas })).data,

  calificarEstadia: async (token: string, puntaje: number, problemas: number) =>
    (await http.post(`/cliente/${token}/calificacion`, { puntaje, problemas })).data,

  // --- Lo que pide el cliente, en la ventanilla ---
  getTicket: async (turno_id: string): Promise<TicketCliente> => (await http.get(`/turnos/${turno_id}/ticket`)).data,

  getPedidosCliente: async (): Promise<PedidoVentanilla[]> => (await http.get('/pedidos-cliente/')).data,

  llevarPedidoCliente: async (id: number) => (await http.post(`/pedidos-cliente/${id}/llevar`)).data,

  atenderPedidoCliente: async (id: number) => (await http.post(`/pedidos-cliente/${id}/atender`)).data,

  rechazarPedidoCliente: async (id: number) => (await http.post(`/pedidos-cliente/${id}/rechazar`)).data,

  // --- Comprobantes verificables (migración 012) ---
  getIntegridad: async (): Promise<IntegridadComprobantes> => (await http.get('/arqueos/integridad')).data,

  verificarComprobante: async (codigo: string): Promise<VerificacionComprobante> =>
    (await http.get(`/arqueos/verificar/${encodeURIComponent(codigo)}`)).data,

  // --- Gemelo del motel ---
  probarEscenario: async (escenario: EscenarioGemelo): Promise<ResultadoGemelo> =>
    (await http.post('/inteligencia/gemelo', escenario)).data,

  // --- Rotación (migración 011): próxima libre, línea de tiempo y clientes perdidos ---
  getProximaLibre: async (): Promise<ProximaLibre> => (await http.get('/habitaciones/proxima-libre')).data,

  getLineaDeTiempo: async (dia?: string): Promise<LineaDeTiempoDatos> =>
    (await http.get('/habitaciones/linea-de-tiempo', { params: { dia } })).data,

  registrarClientePerdido: async (motivo: MotivoPerdida, categoria_id: number | null): Promise<{ en_la_guardia: number }> =>
    (await http.post('/clientes-perdidos/', { motivo, categoria_id })).data,

  // --- Novedades de guardia (migración 009) ---
  getNovedades: async (limite = 30): Promise<Novedad[]> => (await http.get('/novedades/', { params: { limite } })).data,

  crearNovedad: async (datos: { texto: string; importante: boolean; habitacion_id?: number | null }): Promise<Novedad> =>
    (await http.post('/novedades/', datos)).data,

  // --- Guardias y cierre de caja ciego (RF-08) ---
  // Quien entra confirma lo que recibe: la guardia se abre con su recuento.
  abrirGuardia: async (conteos?: ConteoPrenda[]): Promise<Guardia> =>
    (await http.post('/guardias/', conteos ? { conteos } : undefined)).data,

  getTraspaso: async (): Promise<PantallaTraspaso> => (await http.get('/guardias/traspaso')).data,

  contarRopa: async (conteos: ConteoPrenda[]): Promise<RopaContada[]> =>
    (await http.post('/guardias/actual/ropa', { conteos })).data.prendas,

  movimientoRopa: async (datos: { prenda: Prenda; tipo: TipoMovimientoRopa; cantidad: number }) =>
    (await http.post('/operacion/ropa/movimientos', datos)).data,

  // Lo que el conserje anotó en su guardia abierta.
  getMovimientosRopa: async (): Promise<MovimientoRopaHecho[]> => (await http.get('/operacion/ropa/movimientos')).data,

  // La gerencia elige si la ropa se cuenta por estado o todo junto.
  formaDeContarRopa: async (porEstado: boolean): Promise<{ por_estado: boolean }> =>
    (await http.patch('/operacion/ropa/forma', { por_estado: porEstado })).data,

  getArreglos: async (filtro: { habitacionId?: number; sinResolver?: boolean } = {}): Promise<Arreglo[]> =>
    (
      await http.get('/operacion/arreglos', {
        params: { habitacion_id: filtro.habitacionId, sin_resolver: filtro.sinResolver },
      })
    ).data,

  reportarArreglo: async (datos: {
    habitacion_id: number;
    tipo: TipoArreglo;
    rubro: RubroArreglo;
    descripcion: string;
    fuera_de_servicio: boolean;
  }): Promise<Arreglo> => (await http.post('/operacion/arreglos', datos)).data,

  empezarArreglo: async (id: number): Promise<Arreglo> => (await http.post(`/operacion/arreglos/${id}/empezar`)).data,

  resolverArreglo: async (
    id: number,
    datos: { reparado_por: string; trabajo: string | null; costo: number | null; habilitar: boolean },
  ): Promise<Arreglo> => (await http.post(`/operacion/arreglos/${id}/resolver`, datos)).data,

  costoArreglo: async (id: number, costo: number | null): Promise<Arreglo> =>
    (await http.patch(`/operacion/arreglos/${id}/costo`, { costo })).data,

  trasladarTurno: async (
    turnoId: string,
    datos: { habitacion_id: number; motivo: MotivoTraslado; rubro?: RubroArreglo; descripcion?: string },
  ): Promise<{ desde: number; hacia: number; origen_queda: string }> =>
    (await http.post(`/turnos/${turnoId}/trasladar`, datos)).data,

  getTableroOperacion: async (): Promise<TableroOperacion> => (await http.get('/operacion/tablero')).data,

  confirmarArqueo: async (declaracion: DeclaracionCaja): Promise<Arqueo> =>
    (await http.post('/guardias/actual/arqueo', declaracion)).data,

  // --- Panel de la gerencia (RF-09) ---
  getArqueos: async (filtro: { desde?: string; hasta?: string; operador_id?: number }): Promise<Arqueo[]> =>
    (await http.get('/arqueos/', { params: filtro })).data,

  getArqueo: async (id: number): Promise<ArqueoDetalle> => (await http.get(`/arqueos/${id}`)).data,

  getMetricas: async (filtro: { desde?: string; hasta?: string }): Promise<MetricasCaja> =>
    (await http.get('/arqueos/metricas', { params: filtro })).data,

  getPorCategoria: async (filtro: { desde?: string; hasta?: string }): Promise<ResumenCategoria[]> =>
    (await http.get('/arqueos/por-categoria', { params: filtro })).data,

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

  altaHabitacion: async (numero: number, categoria_id?: number): Promise<HabitacionConfiguracion> =>
    (await http.post('/configuracion/habitaciones', { numero, categoria_id })).data,

  configurarHabitacion: async (
    id: number,
    cambios: { numero?: number; activa?: boolean; categoria_id?: number },
  ): Promise<HabitacionConfiguracion> => (await http.patch(`/configuracion/habitaciones/${id}`, cambios)).data,

  altaConserje: async (conserje: ConserjeAlta): Promise<OperadorEstado> => (await http.post('/operadores/', conserje)).data,

  setOperadorActivo: async (id: number, activo: boolean): Promise<OperadorEstado> =>
    (await http.patch(`/operadores/${id}`, { activo })).data,

  // --- Categorías de habitación (migración 008) ---
  // La ventanilla lee las activas con su tarifa vigente; la gerencia las ve todas y las cambia.
  getCategorias: async (): Promise<Categoria[]> => (await http.get('/categorias/')).data,

  getCategoriasConfiguracion: async (): Promise<Categoria[]> => (await http.get('/configuracion/categorias')).data,

  altaCategoria: async (datos: CategoriaAlta): Promise<Categoria> => (await http.post('/configuracion/categorias', datos)).data,

  cambiarCategoria: async (id: number, datos: CategoriaDatos): Promise<Categoria> =>
    (await http.patch(`/configuracion/categorias/${id}`, datos)).data,

  getTarifasDe: async (categoriaId: number): Promise<Tarifa[]> =>
    (await http.get('/configuracion/tarifas', { params: { categoria_id: categoriaId } })).data,

  // --- Tarifas especiales por día y franja (migración 014) ---
  altaFranja: async (datos: FranjaAlta): Promise<Franja> => (await http.post('/configuracion/franjas', datos)).data,

  cambiarFranja: async (id: number, datos: FranjaCambio): Promise<Franja> =>
    (await http.patch(`/configuracion/franjas/${id}`, datos)).data,

  bajaFranja: async (id: number): Promise<void> => {
    await http.delete(`/configuracion/franjas/${id}`);
  },

  // --- Mi perfil ---
  getPerfil: async (): Promise<Perfil> => (await http.get('/perfil/')).data,

  setNombreVisible: async (nombre_visible: string): Promise<Perfil> => (await http.patch('/perfil/', { nombre_visible })).data,

  cambiarClave: async (actual: string, nueva: string): Promise<void> => {
    await http.post('/perfil/clave', { actual, nueva });
  },

  restablecerClave: async (operadorId: number, nueva: string): Promise<OperadorEstado> =>
    (await http.post(`/operadores/${operadorId}/clave`, { nueva })).data,

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

  // --- Inteligencia local de la gerencia (todo se calcula en el servidor del motel) ---
  getTablero: async (): Promise<Tablero> => (await http.get('/inteligencia/tablero')).data,

  // Asistente de todo el personal: ayuda y estado de la ventanilla; a la gerencia, además, el análisis de datos.
  // `anterior` y `anterior_intencion` permiten seguimientos («¿y la semana pasada?», «¿y la 7?»); `pantalla` es la
  // sección abierta, para responder «¿qué hago acá?».
  preguntar: async (texto: string, anterior?: string, anterior_intencion?: string, pantalla?: string): Promise<RespuestaAsistente> =>
    (
      await http.post('/asistente/pregunta', {
        texto,
        anterior: anterior ?? null,
        anterior_intencion: anterior_intencion ?? null,
        pantalla: pantalla ?? null,
      })
    ).data,

  getArqueosMeses: async (operador_id?: number): Promise<ResumenMes[]> =>
    (await http.get('/arqueos/meses', { params: { operador_id } })).data,

  // --- Pedidos de reposición (migración 010) ---
  getPedidos: async (): Promise<Pedido[]> => (await http.get('/pedidos/')).data,

  getPedidoSugerido: async (): Promise<SugeridoPedido[]> => (await http.get('/pedidos/sugerido')).data,

  crearPedido: async (datos: {
    proveedor?: string;
    nota?: string;
    items: { articulo_id: number; cantidad: number }[];
  }): Promise<Pedido> => (await http.post('/pedidos/', datos)).data,

  recibirPedido: async (id: number, items: { articulo_id: number; recibida: number }[]): Promise<Pedido> =>
    (await http.post(`/pedidos/${id}/recepcion`, { items })).data,

  anularPedido: async (id: number): Promise<Pedido> => (await http.post(`/pedidos/${id}/anulacion`)).data,

  descargarPedido: async (id: number): Promise<void> => {
    const datos: Blob = (await http.get(`/pedidos/${id}/pedido.pdf`, { responseType: 'blob' })).data;
    descargar(datos, `pedido-${id}.pdf`);
  },

  // Informe del mes en PDF (resumen y cada guardia), generado por el servidor.
  descargarInformeMes: async (mes: string, operador_id?: number): Promise<void> => {
    const datos: Blob = (await http.get(`/arqueos/meses/${mes}/informe.pdf`, { params: { operador_id }, responseType: 'blob' }))
      .data;
    descargar(datos, `arqueos-${mes}.pdf`);
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
