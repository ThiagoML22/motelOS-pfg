import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BedDouble, LogOut, MessageSquarePlus, Moon, UserRound, WifiOff } from 'lucide-react';
import { Arqueo, Categoria, HabitacionConDetalles, Novedad, RoomStatus, Sesion, TipoCliente } from './types';
import { AsistenteFlotante, AsistenteProvider, useAsistente } from './components/Asistente';
import CentroAvisos from './components/CentroAvisos';
import PaletaComandos, { Comando } from './components/PaletaComandos';
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
    <AsistenteProvider key={sesion.operador.id}>
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
  // Registro de actividad: entradas de los conserjes que la gerencia todavía no vio.
  const [pendientes, setPendientes] = useState(0);
  // Novedades de guardia (migración 009), la paleta de comandos y una pregunta enviada desde ella al asistente.
  const [novedades, setNovedades] = useState<Novedad[]>([]);
  const [nuevaNovedad, setNuevaNovedad] = useState(false);
  const [paleta, setPaleta] = useState(false);
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

  // Ctrl+K (⌘K en Mac) abre y cierra la paleta de comandos.
  useEffect(() => {
    const teclas = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPaleta((v) => !v);
      }
    };
    window.addEventListener('keydown', teclas);
    return () => window.removeEventListener('keydown', teclas);
  }, []);

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
    }
    lista.push({
      id: 'tema',
      titulo: modoActual() === 'oscuro' ? 'Pasar a modo claro' : 'Pasar a modo oscuro',
      grupo: 'Acciones',
      icono: Moon,
      claves: 'tema oscuro claro luna',
      accion: () => elegirTema(modoActual() === 'oscuro' ? 'claro' : 'oscuro'),
    });
    lista.push({ id: 'salir', titulo: 'Cerrar sesión', grupo: 'Acciones', icono: LogOut, claves: 'salir', accion: onSalir });
    return lista;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sesion.operador.rol, conGuardiaPropia, habitaciones, categorias, onSalir, paleta]);

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
  const visibles = filtro === 'Todas' ? deCategoria : deCategoria.filter((h) => h.estado === filtro);
  const categoriasConHabitaciones = categorias.filter((c) => habitaciones.some((h) => h.categoria_id === c.id));

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

      <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-4 py-6 sm:px-6">
        {!conGuardiaPropia && !mostrandoComprobante && activeView !== 'inventario' && activeView !== 'perfil' && (
          <GuardiaView sesion={sesion} onGuardiaAbierta={onRefrescarSesion} onSalir={onSalir} />
        )}

        {conGuardiaPropia && activeView === 'dashboard' && (
          <>
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-xl font-semibold text-ink">Habitaciones</h1>
                <p className="mt-0.5 text-sm text-muted">
                  {habitaciones.length} habitaciones
                  {esGerencia && ' · vista de consulta: la ventanilla la opera el conserje con su guardia'}
                </p>
              </div>

              <div role="group" aria-label="Filtrar por estado" className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  aria-pressed={filtro === 'Todas'}
                  onClick={() => setFiltro('Todas')}
                  className={`press hit rounded-md border px-3 py-1.5 text-sm ${
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
                    className={`press hit flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${
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
            </div>

            {/* Filtro por categoría: solo si el motel tiene más de una en uso. Cada una muestra su ocupación. */}
            {categoriasConHabitaciones.length > 1 && (
              <div role="group" aria-label="Filtrar por categoría" className="-mt-2 mb-5 flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs font-medium uppercase tracking-wide text-subtle">Categoría</span>
                <button
                  type="button"
                  aria-pressed={filtroCategoria === null}
                  onClick={() => setFiltroCategoria(null)}
                  className={`press hit rounded-full border px-3 py-1 text-sm ${
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
                      className={`press hit flex items-center gap-2 rounded-full border px-3 py-1 text-sm ${
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

            <NovedadesCard novedades={novedades} onNueva={() => setNuevaNovedad(true)} />

            {carga === 'cargando' && <p className="py-16 text-center text-sm text-muted">Cargando habitaciones…</p>}

            {carga === 'error' && (
              <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
                <p className="text-sm text-muted">No se pudo obtener el estado de las habitaciones.</p>
                <Button variant="secondary" onClick={() => void fetchHabitaciones()}>
                  Reintentar
                </Button>
              </div>
            )}

            {carga === 'ok' && visibles.length === 0 && (
              <p className="py-16 text-center text-sm text-muted">No hay habitaciones con este estado.</p>
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
          onPreguntar={
            esGerencia
              ? (texto) => {
                  setAsistenteAbierto(true);
                  void asistente.preguntar(texto);
                }
              : undefined
          }
        />
      )}

      {esGerencia && (
        <AsistenteFlotante
          abierto={asistenteAbierto}
          onCambiar={setAsistenteAbierto}
          ocultarEnPantallaAncha={activeView === 'inteligencia'}
        />
      )}

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
