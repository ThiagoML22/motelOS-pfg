import { useCallback, useEffect, useState } from 'react';
import { Arqueo, HabitacionConDetalles, RoomStatus, Sesion, TipoCliente } from './types';
import { api, getErrorMessage, onSesionVencida } from './services/api';
import { useNow } from './hooks/useNow';
import { formatRoomNumber } from './utils/format';
import TopNav, { View } from './components/TopNav';
import RoomsGrid from './components/RoomsGrid';
import RoomDialog from './components/RoomDialog';
import InventarioView from './components/InventarioView';
import LoginView from './components/LoginView';
import GuardiaView from './components/GuardiaView';
import CierreCajaView from './components/CierreCajaView';
import PanelGerencia from './components/PanelGerencia';
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
    } catch {
      setSesion(null);
    }
  }, []);

  useEffect(() => {
    onSesionVencida(() => {
      setSesion(null);
      setAviso('La sesión venció o se cerró. Ingrese nuevamente.');
    });
    void refrescarSesion().finally(() => setIniciando(false));
  }, [refrescarSesion]);

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
  return (
    <Ventanilla key={sesion.operador.id} sesion={sesion} onRefrescarSesion={refrescarSesion} onSalir={() => void salir()} />
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
  const [online, setOnline] = useState(true);
  const [filtro, setFiltro] = useState<Filtro>('Todas');
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
      setHabitaciones(await api.getHabitaciones());
      setOnline(true);
      setCarga('ok');
    } catch {
      setOnline(false);
      setCarga((prev) => (prev === 'ok' ? 'ok' : 'error'));
    }
  }, []);

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

  const conteo = (estado: RoomStatus) => habitaciones.filter((h) => h.estado === estado).length;
  const visibles = filtro === 'Todas' ? habitaciones : habitaciones.filter((h) => h.estado === filtro);

  return (
    <div className="flex min-h-screen flex-col">
      <TopNav
        sesion={sesion}
        activeView={activeView}
        setActiveView={setActiveView}
        online={online}
        now={now}
        onSalir={onSalir}
      />

      <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-4 py-6 sm:px-6">
        {!conGuardiaPropia && !mostrandoComprobante && activeView !== 'inventario' && (
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
                  Todas <span className="tabular-nums">{habitaciones.length}</span>
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

            {!online && carga === 'ok' && (
              <p role="alert" className="mb-4 rounded-md border border-warn/30 bg-warn-soft px-4 py-2.5 text-sm text-warn">
                Sin conexión con el servidor. Los datos pueden estar desactualizados.
              </p>
            )}

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
                now={now}
                onRoomClick={(h) => openRoom(h, false)}
                onAddConsumo={(h) => openRoom(h, true)}
                onChangeEstado={handleEstadoChange}
              />
            )}
          </>
        )}

        {activeView === 'inventario' && <InventarioView />}

        {(conGuardiaPropia || mostrandoComprobante) && activeView === 'caja' && !esGerencia && (
          <CierreCajaView sesion={sesion} resultado={ultimoArqueo} onConfirmado={setUltimoArqueo} onFinalizar={onSalir} />
        )}

        {esGerencia && activeView === 'gerencia' && <PanelGerencia onCambioGuardia={onRefrescarSesion} />}
      </main>

      {selectedRoom && (
        <RoomDialog
          key={selectedRoom.id}
          room={selectedRoom}
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

export default App;
