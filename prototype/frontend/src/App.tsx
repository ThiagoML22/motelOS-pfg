import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BedDouble, Keyboard, LogOut, MessageSquarePlus, Moon, Rows3, UserRound, WifiOff } from 'lucide-react';
import { Arqueo, Categoria, HabitacionConDetalles, Novedad, RoomStatus, Sesion, TipoCliente } from './types';
import { AsistenteFlotante, AsistenteProvider, useAsistente } from './components/Asistente';
import AtajosTeclado, { escribiendo } from './components/AtajosTeclado';
import CentroAvisos from './components/CentroAvisos';
import LineaDeTiempo, {
  guardarVistaHabitaciones,
  leerVistaHabitaciones,
  SelectorVista,
  VistaHabitaciones,
} from './components/LineaDeTiempo';
import PaletaComandos, { Comando } from './components/PaletaComandos';
import { AvisoProximaLibre, BotonClientePerdido } from './components/ProximaLibre';
import { NovedadesCard, NuevaNovedadModal } from './components/NovedadesPanel';
import { elegirTema, modoActual } from './utils/tema';
import { api, esSinRespuesta, getErrorMessage, onSesionVencida } from './services/api';
import { useConexion } from './hooks/useConexion';
import { useNow } from './hooks/useNow';
import { formatClock, formatRoomNumber } from './utils/format';
import { aplicarMarca, sonarAviso } from './utils/marca';
import { FaseEstadia, elapsedMs, faseEstadia, fijarAvisoPorVencer } from './utils/turno';
import ActividadView from './components/ActividadView';
import InteligenciaView from './components/InteligenciaView';
import PerfilView from './components/PerfilView';
import PlataformaView from './components/PlataformaView';
import TopNav, { ITEMS, View } from './components/TopNav';
import RoomsGrid from './components/RoomsGrid';
import RoomDialog from './components/RoomDialog';
import InventarioView from './components/InventarioView';
import LoginView from './components/LoginView';
import GuardiaView from './components/GuardiaView';
import CierreCajaView from './components/CierreCajaView';
import PanelGerencia from './components/PanelGerencia';
import ConfiguracionView from './components/ConfiguracionView';
import Button from './components/ui/Button';
import { useToast } from './components/ui/Toast';
import { EstadoVacio, EsqueletoGrilla } from './components/ui/Carga';
import { ESTADOS_ORDEN, ESTADO_META } from './components/ui/status';

const POLL_MS = 10000;
const SESION_POLL_MS = 30000;

type Filtro = RoomStatus | 'Todas';
type Carga = 'cargando' | 'ok' | 'error';

// RNF-04: sin sesión solo se muestra el ingreso. La sesión (cookie httpOnly) la valida el backend en cada
// petición; si vence, la API responde 401 y se vuelve al ingreso.
function App() {
  const [sesion, setSesion] = useState<Sesion | null>(null);
  const [iniciando, setIniciando] = useState(true);
  const [aviso, setAviso] = useState<string | null>(null);

  const refrescarSesion = useCallback(async () => {
    try {
      setSesion(await api.getSesion());
    } catch (err) {
      // RNF-09: sin conexión la sesión sigue (el servidor no la rechazó); solo un 401 la cierra.
      if (!esSinRespuesta(err)) setSesion(null);
    }
  }, []);

  useEffect(() => {
    onSesionVencida(() => {
      setSesion(null);
      setAviso('La sesión venció o se cerró. Ingrese nuevamente.');
    });
    void refrescarSesion().finally(() => setIniciando(false));
  }, [refrescarSesion]);

  // Apariencia y avisos del motel (migración 009). Sin sesión, la pantalla de ingreso aplica la del código escrito.
  const marca = sesion?.establecimiento?.color_marca ?? null;
  const avisoMin = sesion?.establecimiento?.aviso_por_vencer_min;
  useEffect(() => {
    if (!sesion) return;
    aplicarMarca(marca);
    fijarAvisoPorVencer(avisoMin);
  }, [sesion, marca, avisoMin]);

  const salir = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setSesion(null);
      setAviso(null);
    }
  }, []);

  if (iniciando) {
    return <p className="py-24 text-center text-sm text-muted">Cargando…</p>;
  }
  if (!sesion) {
    return (
      <LoginView
        aviso={aviso}
        onIngreso={(nueva) => {
          setAviso(null);
          setSesion(nueva);
        }}
      />
    );
  }
  // Multiinquilino: la plataforma no opera ningún motel; solo da de alta y suspende establecimientos.
  if (sesion.operador.rol === 'PLATAFORMA') {
    return <PlataformaView sesion={sesion} onRefrescarSesion={refrescarSesion} onSalir={() => void salir()} />;
  }
  // La conversación con el asistente de la gerencia vive mientras dura la sesión, en cualquier pantalla.
  return (
    <AsistenteProvider key={sesion.operador.id} esGerencia={sesion.operador.rol === 'ADMINISTRADOR'}>
      <Ventanilla sesion={sesion} onRefrescarSesion={refrescarSesion} onSalir={() => void salir()} />
    </AsistenteProvider>
  );
}

interface VentanillaProps {
  sesion: Sesion;
  onRefrescarSesion: () => Promise<void>;
  onSalir: () => void;
}

function Ventanilla({ sesion, onRefrescarSesion, onSalir }: VentanillaProps) {
  const { toast } = useToast();
  const now = useNow();
  const esGerencia = sesion.operador.rol === 'ADMINISTRADOR';
  // El conserje opera solo con su propia guardia abierta (RF-08).
  const conGuardiaPropia = esGerencia || Boolean(sesion.guardia?.es_propia);
  const [activeView, setActiveView] = useState<View>(esGerencia ? 'gerencia' : 'dashboard');
  const [habitaciones, setHabitaciones] = useState<HabitacionConDetalles[]>([]);
  const [carga, setCarga] = useState<Carga>('cargando');
  const [filtro, setFiltro] = useState<Filtro>('Todas');
  // Categorías de habitación (Simple, Especial, VIP...) con su tarifa vigente, y el filtro de la grilla por categoría.
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [filtroCategoria, setFiltroCategoria] = useState<number | null>(null);
  // Orden de la grilla: por número (como siempre) o, si el puesto lo elige, por vencimiento. Se recuerda en el puesto.
  const [orden, setOrden] = useState<OrdenGrilla>(leerOrden);
  const cambiarOrden = (valor: OrdenGrilla) => {
    setOrden(valor);
    try {
      localStorage.setItem(CLAVE_ORDEN, valor);
    } catch {
      // sin almacenamiento local, vuelve a «por número» al recargar
    }
  };
  // Habitaciones en grilla o en línea de tiempo: se recuerda en el puesto.
  const [vistaHabitaciones, setVistaHabitaciones] = useState<VistaHabitaciones>(leerVistaHabitaciones);
  const cambiarVistaHabitaciones = useCallback((vista: VistaHabitaciones) => {
    setVistaHabitaciones(vista);
    guardarVistaHabitaciones(vista);
  }, []);
  const vistaActual = useRef(vistaHabitaciones);
  vistaActual.current = vistaHabitaciones;
  // Registro de actividad: entradas de los conserjes que la gerencia todavía no vio.
  const [pendientes, setPendientes] = useState(0);
  // Novedades de guardia (migración 009), la paleta de comandos y una pregunta enviada desde ella al asistente.
  const [novedades, setNovedades] = useState<Novedad[]>([]);
  const [nuevaNovedad, setNuevaNovedad] = useState(false);
  const [paleta, setPaleta] = useState(false);
  const [atajos, setAtajos] = useState(false);
  // Panel flotante del asistente (gerencia); la paleta de comandos lo abre con una pregunta.
  const [asistenteAbierto, setAsistenteAbierto] = useState(false);
  const asistente = useAsistente();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [openAddProduct, setOpenAddProduct] = useState(false);
  // Arqueo recién confirmado: el comprobante queda a la vista hasta que el conserje finaliza, aunque el
  // refresco de la sesión ya informe la guardia como cerrada.
  const [ultimoArqueo, setUltimoArqueo] = useState<Arqueo | null>(null);
  const mostrandoComprobante = activeView === 'caja' && ultimoArqueo !== null;

  // Si el conserje abre una guardia nueva, el comprobante anterior deja lugar al formulario de cierre.
  useEffect(() => {
    if (ultimoArqueo && sesion.guardia?.es_propia && sesion.guardia.id !== ultimoArqueo.guardia_id) {
      setUltimoArqueo(null);
    }
  }, [sesion.guardia, ultimoArqueo]);

  const fetchHabitaciones = useCallback(async () => {
    try {
      const [lista, cats] = await Promise.all([api.getHabitaciones(), api.getCategorias()]);
      setHabitaciones(lista);
      setCategorias(cats);
      setCarga('ok');
    } catch {
      setCarga((prev) => (prev === 'ok' ? 'ok' : 'error'));
    }
  }, []);

  const fetchPendientes = useCallback(async () => {
    try {
      setNovedades(await api.getNovedades(30));
      if (esGerencia) setPendientes(await api.getActividadPendiente());
    } catch {
      // los contadores se actualizan en el próximo sondeo
    }
  }, [esGerencia]);

  // Ctrl+K (⌘K en Mac) abre y cierra la paleta de comandos. Fuera de los campos de texto también hay teclas sueltas:
  // «/» busca, «?» muestra los atajos, «A» abre el asistente, «N» deja una novedad y los números van a cada sección.
  const seccionesDelRol = useMemo(() => ITEMS.filter((i) => i.roles.includes(sesion.operador.rol)), [sesion.operador.rol]);
  useEffect(() => {
    const teclas = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaleta((v) => !v);
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey || escribiendo(e)) return;
      const tecla = e.key.toLowerCase();
      const seccion = /^[1-9]$/.test(tecla) ? seccionesDelRol[Number(tecla) - 1] : undefined;
      if (tecla === '/') setPaleta(true);
      else if (tecla === '?') setAtajos(true);
      else if (tecla === 'a') setAsistenteAbierto((v) => !v);
      else if (tecla === 'n' && conGuardiaPropia) setNuevaNovedad(true);
      else if (tecla === 'l' && conGuardiaPropia) {
        setActiveView('dashboard');
        cambiarVistaHabitaciones(vistaActual.current === 'grilla' ? 'linea' : 'grilla');
      }
      else if (seccion) setActiveView(seccion.view);
      else return;
      e.preventDefault();
    };
    window.addEventListener('keydown', teclas);
    return () => window.removeEventListener('keydown', teclas);
  }, [seccionesDelRol, conGuardiaPropia, cambiarVistaHabitaciones]);

  // RNF-09: al volver la conexión se traen la sesión, la grilla y el contador del registro (en menos de 5 s).
  const conexion = useConexion(async () => {
    await Promise.all([onRefrescarSesion(), fetchHabitaciones(), fetchPendientes()]);
    toast('Conexión recuperada: la ventanilla se actualizó con los datos del servidor.', 'success');
  });

  useEffect(() => {
    void fetchPendientes();
    const intervalo = setInterval(() => void fetchPendientes(), SESION_POLL_MS);
    return () => clearInterval(intervalo);
  }, [fetchPendientes]);

  useEffect(() => {
    void fetchHabitaciones();
    const interval = setInterval(fetchHabitaciones, POLL_MS);
    const onFocus = () => void fetchHabitaciones();
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, [fetchHabitaciones]);

  // El estado de la guardia de la ventanilla se refresca solo: el conserje que espera ve cuándo la anterior
  // se cerró, y la gerencia ve quién está atendiendo.
  useEffect(() => {
    const interval = setInterval(() => void onRefrescarSesion(), SESION_POLL_MS);
    return () => clearInterval(interval);
  }, [onRefrescarSesion]);

  // Alertas sonoras (migración 009): un aviso cuando un turno pasa a «por vencer» o a «excedido», si el motel las
  // activó y quien atiende es el conserje con su guardia.
  const fasesPrevias = useRef(new Map<number, FaseEstadia>());
  const conSonido = Boolean(sesion.establecimiento?.alertas_sonoras) && !esGerencia && conGuardiaPropia;
  useEffect(() => {
    let aviso: 'por_vencer' | 'excedido' | null = null;
    const previas = fasesPrevias.current;
    for (const h of habitaciones) {
      const turno = h.estado === 'Ocupada' ? h.turno_activo : null;
      if (!turno) {
        previas.delete(h.id);
        continue;
      }
      const fase = faseEstadia(elapsedMs(turno, now), turno.estadia_base_min ?? undefined);
      const antes = previas.get(h.id);
      if (antes !== undefined && antes !== fase && fase !== 'normal') {
        aviso = fase === 'excedido' ? 'excedido' : (aviso ?? 'por_vencer');
      }
      previas.set(h.id, fase);
    }
    if (conSonido && aviso) sonarAviso(aviso);
  }, [habitaciones, now, conSonido]);

  const comandos = useMemo<Comando[]>(() => {
    const lista: Comando[] = ITEMS.filter((i) => i.roles.includes(sesion.operador.rol)).map((i) => ({
      id: `vista-${i.view}`,
      titulo: i.label,
      grupo: 'Ir a',
      icono: i.icon,
      accion: () => setActiveView(i.view),
    }));
    lista.push({ id: 'vista-perfil', titulo: 'Mi perfil', grupo: 'Ir a', icono: UserRound, claves: 'clave contraseña', accion: () => setActiveView('perfil') });
    if (conGuardiaPropia) {
      for (const h of habitaciones) {
        lista.push({
          id: `hab-${h.id}`,
          titulo: `${formatRoomNumber(h.numero)}`,
          detalle: ESTADO_META[h.estado].label,
          grupo: 'Habitaciones',
          icono: BedDouble,
          claves: `${h.numero} habitacion ${categorias.find((c) => c.id === h.categoria_id)?.nombre ?? ''}`,
          accion: () => {
            setActiveView('dashboard');
            openRoom(h, false);
          },
        });
      }
      lista.push({ id: 'novedad', titulo: 'Dejar una novedad', grupo: 'Acciones', icono: MessageSquarePlus, claves: 'nota aviso', accion: () => setNuevaNovedad(true) });
      lista.push({
        id: 'linea-tiempo',
        titulo: 'Línea de tiempo de las habitaciones',
        grupo: 'Ir a',
        icono: Rows3,
        claves: 'historial cronograma 24 horas',
        accion: () => {
          setActiveView('dashboard');
          cambiarVistaHabitaciones('linea');
        },
      });
    }
    lista.push({
      id: 'tema',
      titulo: modoActual() === 'oscuro' ? 'Pasar a modo claro' : 'Pasar a modo oscuro',
      grupo: 'Acciones',
      icono: Moon,
      claves: 'tema oscuro claro luna',
      accion: () => elegirTema(modoActual() === 'oscuro' ? 'claro' : 'oscuro'),
    });
    lista.push({ id: 'atajos', titulo: 'Atajos de teclado', detalle: '?', grupo: 'Acciones', icono: Keyboard, claves: 'teclas rapidas ayuda', accion: () => setAtajos(true) });
    lista.push({ id: 'salir', titulo: 'Cerrar sesión', grupo: 'Acciones', icono: LogOut, claves: 'salir', accion: onSalir });
    return lista;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sesion.operador.rol, conGuardiaPropia, habitaciones, categorias, onSalir, paleta, cambiarVistaHabitaciones]);

  // Botones que propone el asistente: ir a una pantalla permitida para el rol o abrir una habitación.
  const habitacionesRef = useRef(habitaciones);
  habitacionesRef.current = habitaciones;
  const { registrarAcciones, fijarPantalla } = asistente;

  // El asistente sabe qué sección está a la vista; sin guardia propia, el conserje está en «Abrir su guardia».
  const enApertura = !conGuardiaPropia && !mostrandoComprobante && activeView !== 'inventario' && activeView !== 'perfil';
  useEffect(() => {
    if (enApertura) fijarPantalla('guardia', 'abrir la guardia');
    else fijarPantalla(activeView, ITEMS.find((i) => i.view === activeView)?.label ?? 'Mi perfil');
  }, [activeView, enApertura, fijarPantalla]);
  useEffect(() => {
    const permitidas = new Set<string>([...ITEMS.filter((i) => i.roles.includes(sesion.operador.rol)).map((i) => i.view), 'perfil']);
    registrarAcciones((accion) => {
      const habitacion = habitacionesRef.current.find((h) => h.id === accion.habitacion_id);
      if (habitacion) {
        setActiveView('dashboard');
        setAsistenteAbierto(false);
        setSelectedId(habitacion.id);
        setOpenAddProduct(false);
      } else if (accion.vista && permitidas.has(accion.vista)) {
        setActiveView(accion.vista as View);
      }
    });
  }, [registrarAcciones, sesion.operador.rol]);

  const selectedRoom = habitaciones.find((h) => h.id === selectedId) ?? null;

  const openRoom = (habitacion: HabitacionConDetalles, addProduct: boolean) => {
    setSelectedId(habitacion.id);
    setOpenAddProduct(addProduct);
  };

  const closePanel = () => {
    setSelectedId(null);
    setOpenAddProduct(false);
  };

  const handleTurnoSubmit = async (patente: string | undefined, tipoCliente: TipoCliente) => {
    if (!selectedRoom) return;
    try {
      await api.createTurno({
        habitacion_id: selectedRoom.id,
        identificador_vehicular: patente,
        tipo_cliente: tipoCliente,
      });
      toast(`Turno abierto en ${formatRoomNumber(selectedRoom.numero)}.`, 'success');
      closePanel();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo abrir el turno.'), 'error');
    } finally {
      await fetchHabitaciones();
    }
  };

  const handleEstadoChange = async (habitacion: HabitacionConDetalles, newState: RoomStatus) => {
    try {
      await api.updateHabitacionEstado(habitacion.id, newState);
      toast(`${formatRoomNumber(habitacion.numero)} pasó a ${ESTADO_META[newState].label.toLowerCase()}.`, 'success');
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo cambiar el estado de la habitación.'), 'error');
    } finally {
      await fetchHabitaciones();
    }
  };

  const deCategoria = filtroCategoria === null ? habitaciones : habitaciones.filter((h) => h.categoria_id === filtroCategoria);
  const conteo = (estado: RoomStatus) => deCategoria.filter((h) => h.estado === estado).length;
  const filtradas = filtro === 'Todas' ? deCategoria : deCategoria.filter((h) => h.estado === filtro);
  const visibles = orden === 'numero' ? filtradas : ordenarPorVencimiento(filtradas, categorias, now);
  const categoriasConHabitaciones = categorias.filter((c) => habitaciones.some((h) => h.categoria_id === c.id));
  const disponibles = habitaciones.filter((h) => h.estado === 'Libre').length;
  const firmaEstados = habitaciones.map((h) => `${h.id}:${h.estado}`).join();
  // Registrar un cliente que se fue es de quien atiende; la gerencia mira.
  const puedeRegistrar = !esGerencia && conGuardiaPropia;
  const conPocoLugar = carga === 'ok' && habitaciones.length > 0 && disponibles <= 2;

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav
        sesion={sesion}
        activeView={activeView}
        setActiveView={setActiveView}
        online={conexion.conectado}
        now={now}
        pendientes={pendientes}
        onSalir={onSalir}
        onBuscar={() => setPaleta(true)}
        avisos={
          <CentroAvisos
            novedades={novedades}
            pendientes={pendientes}
            esGerencia={esGerencia}
            operadorId={sesion.operador.id}
            claveVistas={`motelos.novedades.${sesion.establecimiento?.codigo ?? ''}.${sesion.operador.id}`}
            onIrActividad={() => setActiveView('actividad')}
            onNuevaNovedad={() => setNuevaNovedad(true)}
          />
        }
      />

      {!conexion.conectado && <AvisoSinConexion desde={conexion.sinConexionDesde} onReintentar={conexion.reintentar} />}

      {/* Cada sección aparece con un fundido corto (la clave reinicia la animación). Solo opacidad: moverla desbordaría
          la página un instante y la barra de desplazamiento correría el encabezado. */}
      <main key={activeView} className="mx-auto flex w-full max-w-[1600px] flex-1 animate-fade-in flex-col px-4 pb-6 pt-4 sm:px-6">
        {enApertura && (
          <GuardiaView sesion={sesion} onGuardiaAbierta={onRefrescarSesion} onSalir={onSalir} />
        )}

        {conGuardiaPropia && activeView === 'dashboard' && (
          <>
            {/* Lo principal de la ventanilla son las habitaciones: arriba de ellas, dos filas finas y una línea de novedades. */}
            <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
              <h1 className="flex items-baseline gap-2 text-xl font-semibold text-ink">
                Habitaciones
                <span className="text-sm font-normal tabular-nums text-muted">{habitaciones.length}</span>
              </h1>
              {esGerencia && (
                <span title="La ventanilla la opera el conserje con su guardia" className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">
                  Solo consulta
                </span>
              )}
              {vistaHabitaciones === 'grilla' && (
                <div role="group" aria-label="Filtrar por estado" className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    aria-pressed={filtro === 'Todas'}
                    onClick={() => setFiltro('Todas')}
                    className={`press hit rounded-md border px-2.5 py-1 text-sm ${
                      filtro === 'Todas'
                        ? 'border-accent bg-accent-soft font-medium text-accent'
                        : 'border-line-strong bg-surface text-muted hover:text-ink'
                    }`}
                  >
                    Todas <span className="tabular-nums">{deCategoria.length}</span>
                  </button>
                  {ESTADOS_ORDEN.map((estado) => (
                    <button
                      key={estado}
                      type="button"
                      aria-pressed={filtro === estado}
                      onClick={() => setFiltro(estado)}
                      className={`press hit flex items-center gap-2 rounded-md border px-2.5 py-1 text-sm ${
                        filtro === estado
                          ? 'border-accent bg-accent-soft font-medium text-accent'
                          : 'border-line-strong bg-surface text-muted hover:text-ink'
                      }`}
                    >
                      <span className={`h-2 w-2 rounded-full ${ESTADO_META[estado].dot}`} aria-hidden="true" />
                      {ESTADO_META[estado].label} <span className="tabular-nums">{conteo(estado)}</span>
                    </button>
                  ))}
                </div>
              )}
              <div className="ml-auto flex items-center gap-2">
                {vistaHabitaciones === 'grilla' && (
                  <select
                    aria-label="Ordenar las habitaciones"
                    value={orden}
                    onChange={(e) => cambiarOrden(e.target.value as OrdenGrilla)}
                    className="h-8 rounded-md border border-line-strong bg-surface px-2 text-sm text-ink focus:border-accent focus-visible:outline-none"
                  >
                    <option value="numero">Por número</option>
                    <option value="vencimiento">Por vencimiento</option>
                  </select>
                )}
                <SelectorVista vista={vistaHabitaciones} onCambiar={cambiarVistaHabitaciones} />
              </div>
            </div>

            {/* Categorías a la izquierda (solo si el motel usa más de una, cada una con su ocupación) y, a la derecha, la
                próxima libre y el registro de un cliente que se fue. */}
            {((vistaHabitaciones === 'grilla' && categoriasConHabitaciones.length > 1) || conPocoLugar || puedeRegistrar) && (
              <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-2">
                {vistaHabitaciones === 'grilla' && categoriasConHabitaciones.length > 1 && (
                  <div role="group" aria-label="Filtrar por categoría" className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      aria-pressed={filtroCategoria === null}
                      onClick={() => setFiltroCategoria(null)}
                      className={`press hit rounded-full border px-2.5 py-0.5 text-sm ${
                        filtroCategoria === null
                          ? 'border-accent bg-accent-soft font-medium text-accent'
                          : 'border-line-strong bg-surface text-muted hover:text-ink'
                      }`}
                    >
                      Todas
                    </button>
                    {categoriasConHabitaciones.map((c) => {
                      const propias = habitaciones.filter((h) => h.categoria_id === c.id);
                      const ocupadas = propias.filter((h) => h.estado === 'Ocupada').length;
                      const activa = filtroCategoria === c.id;
                      return (
                        <button
                          key={c.id}
                          type="button"
                          aria-pressed={activa}
                          onClick={() => setFiltroCategoria(activa ? null : c.id)}
                          title={c.descripcion ?? undefined}
                          className={`press hit flex items-center gap-2 rounded-full border px-2.5 py-0.5 text-sm ${
                            activa ? 'font-medium' : 'border-line-strong bg-surface text-muted hover:text-ink'
                          }`}
                          style={activa ? { borderColor: c.color, color: c.color, backgroundColor: `${c.color}14` } : undefined}
                        >
                          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.color }} aria-hidden="true" />
                          {c.nombre}
                          <span className="tabular-nums text-xs opacity-80">
                            {ocupadas}/{propias.length}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="ml-auto flex min-w-0 items-center gap-2">
                  {conPocoLugar && (
                    <AvisoProximaLibre
                      firma={firmaEstados}
                      onAbrir={(id) => {
                        setSelectedId(id);
                        setOpenAddProduct(false);
                      }}
                    />
                  )}
                  {puedeRegistrar && <BotonClientePerdido categorias={categoriasConHabitaciones} destacado={disponibles === 0} />}
                </div>
              </div>
            )}

            {vistaHabitaciones === 'linea' && (
              <LineaDeTiempo
                onAbrir={(id) => {
                  setSelectedId(id);
                  setOpenAddProduct(false);
                }}
              />
            )}

            {vistaHabitaciones === 'grilla' && (
            <>
            <NovedadesCard novedades={novedades} onNueva={() => setNuevaNovedad(true)} />

            {carga === 'cargando' && <EsqueletoGrilla />}

            {carga === 'error' && (
              <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
                <p className="text-sm text-muted">No se pudo obtener el estado de las habitaciones.</p>
                <Button variant="secondary" onClick={() => void fetchHabitaciones()}>
                  Reintentar
                </Button>
              </div>
            )}

            {carga === 'ok' && visibles.length === 0 && (
              <EstadoVacio icono={BedDouble} titulo="No hay habitaciones con este filtro" texto="Probá con otro estado o con todas las categorías." />
            )}

            {carga === 'ok' && visibles.length > 0 && (
              <RoomsGrid
                habitaciones={visibles}
                categorias={categorias}
                now={now}
                onRoomClick={(h) => openRoom(h, false)}
                onAddConsumo={(h) => openRoom(h, true)}
                onChangeEstado={handleEstadoChange}
              />
            )}
            </>
            )}
          </>
        )}

        {activeView === 'inventario' && <InventarioView esConserje={!esGerencia} />}

        {(conGuardiaPropia || mostrandoComprobante) && activeView === 'caja' && !esGerencia && (
          <CierreCajaView sesion={sesion} resultado={ultimoArqueo} onConfirmado={setUltimoArqueo} onFinalizar={onSalir} />
        )}

        {esGerencia && activeView === 'inteligencia' && <InteligenciaView />}

        {esGerencia && activeView === 'gerencia' && <PanelGerencia onCambioGuardia={onRefrescarSesion} />}

        {esGerencia && activeView === 'configuracion' && (
          <ConfiguracionView onCambioHabitaciones={fetchHabitaciones} onCambioApariencia={onRefrescarSesion} />
        )}

        {esGerencia && activeView === 'actividad' && <ActividadView onCambioPendientes={setPendientes} />}

        {activeView === 'perfil' && <PerfilView onPerfilActualizado={onRefrescarSesion} onSalir={onSalir} />}
      </main>

      {nuevaNovedad && (
        <NuevaNovedadModal
          habitaciones={habitaciones}
          onClose={() => setNuevaNovedad(false)}
          onCreada={() => {
            setNuevaNovedad(false);
            void fetchPendientes();
          }}
        />
      )}

      {paleta && (
        <PaletaComandos
          comandos={comandos}
          onClose={() => setPaleta(false)}
          onPreguntar={(texto) => {
            setAsistenteAbierto(true);
            void asistente.preguntar(texto);
          }}
        />
      )}

      {atajos && (
        <AtajosTeclado
          onClose={() => setAtajos(false)}
          grupos={[
            {
              titulo: 'General',
              atajos: [
                { teclas: ['Ctrl K', '/'], descripcion: 'Buscar una sección, una habitación o una acción' },
                { teclas: ['A'], descripcion: 'Abrir o cerrar el asistente' },
                ...(conGuardiaPropia
                  ? [
                      { teclas: ['N'], descripcion: 'Dejar una novedad para la próxima guardia' },
                      { teclas: ['L'], descripcion: 'Cambiar entre la grilla y la línea de tiempo' },
                    ]
                  : []),
                { teclas: ['?'], descripcion: 'Ver estos atajos' },
                { teclas: ['Esc'], descripcion: 'Cerrar el diálogo o el panel abierto' },
              ],
            },
            {
              titulo: 'Secciones',
              atajos: seccionesDelRol.map((s, i) => ({ teclas: [String(i + 1)], descripcion: `Ir a ${s.label}` })),
            },
            {
              titulo: 'En las listas y el asistente',
              atajos: [
                { teclas: ['Tab'], descripcion: 'Pasar de una habitación a la siguiente' },
                { teclas: ['Enter'], descripcion: 'Abrir la habitación elegida o enviar la pregunta' },
                { teclas: ['↑'], descripcion: 'Recuperar la pregunta anterior en el asistente' },
              ],
            },
          ]}
        />
      )}

      {/* El asistente está para todo el personal; en Inteligencia, con pantalla ancha, ya está en el costado. */}
      <AsistenteFlotante
        abierto={asistenteAbierto}
        onCambiar={setAsistenteAbierto}
        ocultarEnPantallaAncha={esGerencia && activeView === 'inteligencia'}
      />

      {selectedRoom && (
        <RoomDialog
          key={selectedRoom.id}
          room={selectedRoom}
          categoria={categorias.find((c) => c.id === selectedRoom.categoria_id)}
          now={now}
          onClose={closePanel}
          onAperturaTurno={handleTurnoSubmit}
          onRefreshRooms={fetchHabitaciones}
          initialAddProduct={openAddProduct}
        />
      )}
    </div>
  );
}

type OrdenGrilla = 'numero' | 'vencimiento';
const CLAVE_ORDEN = 'motelos.orden-grilla';

const leerOrden = (): OrdenGrilla => {
  try {
    return localStorage.getItem(CLAVE_ORDEN) === 'vencimiento' ? 'vencimiento' : 'numero';
  } catch {
    return 'numero';
  }
};

// Por vencimiento: primero las ocupadas, de la que vence (o ya se excedió) antes a la que vence después; luego las de
// limpieza, las disponibles y las de mantenimiento, cada grupo por número.
const GRUPO: Record<RoomStatus, number> = { Ocupada: 0, 'En Limpieza': 1, Libre: 2, Mantenimiento: 3 };
const ordenarPorVencimiento = (habitaciones: HabitacionConDetalles[], categorias: Categoria[], now: number) => {
  const restante = (h: HabitacionConDetalles) => {
    const turno = h.estado === 'Ocupada' ? h.turno_activo : null;
    if (!turno) return Infinity;
    const base = turno.estadia_base_min ?? categorias.find((c) => c.id === h.categoria_id)?.tarifa?.estadia_base_min ?? 120;
    return base * 60000 - elapsedMs(turno, now);
  };
  return [...habitaciones].sort(
    (a, b) => GRUPO[a.estado] - GRUPO[b.estado] || restante(a) - restante(b) || a.numero - b.numero,
  );
};

// RNF-09: aviso fijo mientras dura el corte. Lo que no se confirmó antes del corte no quedó registrado.
function AvisoSinConexion({ desde, onReintentar }: { desde: number | null; onReintentar: () => void }) {
  return (
    <div role="alert" className="border-b border-warn/30 bg-warn-soft print:hidden">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-4 py-2.5 text-sm text-warn sm:px-6">
        <WifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />
        <p className="flex-1">
          <span className="font-medium">Sin conexión con el servidor{desde ? ` desde las ${formatClock(new Date(desde))}` : ''}.</span>{' '}
          No se pueden abrir ni cobrar turnos hasta que vuelva; los cronómetros siguen corriendo en el servidor. Reintentando
          cada 2 segundos…
        </p>
        <Button variant="secondary" className="h-11" onClick={onReintentar}>
          Reintentar ahora
        </Button>
      </div>
    </div>
  );
}

export default App;
