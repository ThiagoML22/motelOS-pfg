import { useCallback, useEffect, useState } from 'react';
import { HabitacionConDetalles, RoomStatus, TipoCliente } from './types';
import { api, getErrorMessage } from './services/api';
import { useNow } from './hooks/useNow';
import { formatRoomNumber } from './utils/format';
import TopNav, { View } from './components/TopNav';
import RoomsGrid from './components/RoomsGrid';
import RoomDialog from './components/RoomDialog';
import InventarioView from './components/InventarioView';
import Button from './components/ui/Button';
import { useToast } from './components/ui/Toast';
import { ESTADOS_ORDEN, ESTADO_META } from './components/ui/status';

const POLL_MS = 10000;

type Filtro = RoomStatus | 'Todas';
type Carga = 'cargando' | 'ok' | 'error';

function App() {
  const { toast } = useToast();
  const now = useNow();
  const [activeView, setActiveView] = useState<View>('dashboard');
  const [habitaciones, setHabitaciones] = useState<HabitacionConDetalles[]>([]);
  const [carga, setCarga] = useState<Carga>('cargando');
  const [online, setOnline] = useState(true);
  const [filtro, setFiltro] = useState<Filtro>('Todas');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [openAddProduct, setOpenAddProduct] = useState(false);

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
      <TopNav activeView={activeView} setActiveView={setActiveView} online={online} now={now} />

      <main className="mx-auto flex w-full max-w-[1600px] flex-1 flex-col px-4 py-6 sm:px-6">
        {activeView === 'dashboard' && (
          <>
            <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
              <div>
                <h1 className="text-xl font-semibold text-ink">Habitaciones</h1>
                <p className="mt-0.5 text-sm text-muted">{habitaciones.length} habitaciones</p>
              </div>

              <div role="group" aria-label="Filtrar por estado" className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  aria-pressed={filtro === 'Todas'}
                  onClick={() => setFiltro('Todas')}
                  className={`press min-h-11 rounded-md border px-3 text-sm ${
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
                    className={`press flex min-h-11 items-center gap-2 rounded-md border px-3 text-sm ${
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

        {activeView === 'caja' && (
          <div className="flex flex-1 flex-col items-center justify-center rounded-lg border border-line bg-surface p-12 text-center">
            <h1 className="text-lg font-semibold text-ink">Cierre de caja</h1>
            <p className="mt-1 max-w-sm text-sm text-muted">
              Este módulo todavía no está disponible. Se habilitará junto con el cierre de caja ciego.
            </p>
          </div>
        )}
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
