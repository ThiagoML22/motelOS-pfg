import { useState, useEffect } from 'react';
import { HabitacionConDetalles, TipoCliente } from './types';
import { api } from './services/api';
import TopNav from './components/TopNav';
import RoomsGrid from './components/RoomsGrid';
import SlideOverPanel from './components/SlideOverPanel';
import InventarioView from './components/InventarioView';

function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [habitaciones, setHabitaciones] = useState<HabitacionConDetalles[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<HabitacionConDetalles | null>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [openAddProduct, setOpenAddProduct] = useState(false);

  const fetchHabitaciones = async () => {
    try {
      const data = await api.getHabitaciones();
      
      const realData = data.map((h: any) => {
         let tiempo_transcurrido = undefined;
         let excede_tiempo = false;
         
         if (h.estado === 'Ocupada' && h.turno_activo && h.turno_activo.hora_inicio) {
             const isUtc = h.turno_activo.hora_inicio.endsWith('Z') || h.turno_activo.hora_inicio.includes('+');
             const start = new Date(h.turno_activo.hora_inicio + (isUtc ? '' : 'Z'));
             const now = new Date();
             const diffMs = Math.max(0, now.getTime() - start.getTime());
             
             const diffHrs = Math.floor(diffMs / 3600000);
             const diffMins = Math.floor((diffMs % 3600000) / 60000);
             const diffSecs = Math.floor((diffMs % 60000) / 1000);
             
             tiempo_transcurrido = `${diffHrs.toString().padStart(2, '0')}:${diffMins.toString().padStart(2, '0')}:${diffSecs.toString().padStart(2, '0')}`;
             excede_tiempo = diffHrs >= 2;
         }
         
         return { ...h, tiempo_transcurrido, excede_tiempo };
      });

      setHabitaciones(realData);
    } catch (err) {
      console.error('Error fetching habitaciones:', err);
    }
  };

  useEffect(() => {
    fetchHabitaciones();
    const interval = setInterval(fetchHabitaciones, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleRoomClick = (habitacion: HabitacionConDetalles) => {
    setSelectedRoom(habitacion);
    setOpenAddProduct(false);
    setIsPanelOpen(true);
  };

  const handleAddConsumoClick = (habitacion: HabitacionConDetalles) => {
    setSelectedRoom(habitacion);
    setOpenAddProduct(true);
    setIsPanelOpen(true);
  };

  const handleTurnoSubmit = async (patente: string, tipoCliente: TipoCliente) => {
    if (!selectedRoom) return;
    try {
      await api.createTurno({
        habitacion_id: selectedRoom.id,
        identificador_vehicular: patente,
        tipo_cliente: tipoCliente
      });
      setIsPanelOpen(false);
      setSelectedRoom(null);
      await fetchHabitaciones();
    } catch (err: any) {
      console.error('Error creating turno:', err);
      alert(err.response?.data?.detail || 'Error al abrir turno');
    }
  };

  const handleEstadoChange = async (habitacion: HabitacionConDetalles, newState: string) => {
    try {
      await api.updateHabitacionEstado(habitacion.id, newState);
      await fetchHabitaciones();
    } catch (err: any) {
      console.error('Error changing room state:', err);
      alert(err.response?.data?.detail || 'Error al cambiar el estado de la habitación');
    }
  };

  const total = habitaciones.length;
  const libres = habitaciones.filter(h => h.estado === 'Libre').length;
  const ocupadas = habitaciones.filter(h => h.estado === 'Ocupada').length;
  const limpieza = habitaciones.filter(h => h.estado === 'En Limpieza').length;
  const mantenimiento = habitaciones.filter(h => h.estado === 'Mantenimiento').length;

  const stats = [
    { label: 'Disponibles', count: libres, dot: 'bg-emerald-500', bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-700' },
    { label: 'Ocupadas', count: ocupadas, dot: 'bg-rose-500', bg: 'bg-rose-50', border: 'border-rose-100', text: 'text-rose-700' },
    { label: 'Limpieza', count: limpieza, dot: 'bg-amber-500', bg: 'bg-amber-50', border: 'border-amber-100', text: 'text-amber-700' },
    { label: 'Mantenimiento', count: mantenimiento, dot: 'bg-slate-400', bg: 'bg-slate-50', border: 'border-slate-100', text: 'text-slate-600' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-gray-100 font-sans text-slate-900 flex flex-col">
      <TopNav activeView={activeView} setActiveView={setActiveView} />

      <main className="flex-1 max-w-[1600px] mx-auto w-full px-8 py-8 flex flex-col">
        {activeView === 'dashboard' && (
          <>
            {/* Header */}
            <div className="flex justify-between items-end mb-8">
              <div>
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Estado de Habitaciones</h1>
                <p className="text-slate-400 mt-0.5 text-sm font-medium">Monitoreo en tiempo real · {total} habitaciones</p>
              </div>
              
              {/* Stats Mini Cards */}
              <div className="hidden md:flex items-center gap-3">
                {stats.map(s => (
                  <div key={s.label} className={`flex items-center gap-2.5 px-4 py-2 rounded-xl border ${s.bg} ${s.border}`}>
                    <span className={`w-2 h-2 rounded-full ${s.dot}`}></span>
                    <div className="flex items-baseline gap-1.5">
                      <span className={`text-xl font-extrabold ${s.text} tabular-nums`}>{s.count}</span>
                      <span className="text-[11px] font-medium text-gray-500">{s.label}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Grid */}
            <div className="flex-1">
              <RoomsGrid 
                habitaciones={habitaciones} 
                onRoomClick={handleRoomClick} 
                onAddConsumo={handleAddConsumoClick} 
                onChangeEstado={handleEstadoChange}
              />
            </div>
          </>
        )}

        {activeView === 'inventario' && (
           <InventarioView />
        )}

        {activeView === 'caja' && (
           <div className="flex-1 flex flex-col items-center justify-center p-12 bg-white rounded-2xl border border-gray-200">
              <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
                <span className="text-2xl">🔒</span>
              </div>
              <span className="text-xl font-bold text-slate-900 mb-1">Cierre de Caja Ciego</span>
              <p className="text-sm text-slate-400">Módulo en desarrollo · Sprint 4</p>
           </div>
        )}
      </main>

      {/* Slide-over panel */}
      {isPanelOpen && selectedRoom && (
        <SlideOverPanel
          room={selectedRoom}
          onClose={() => { setIsPanelOpen(false); setOpenAddProduct(false); }}
          onAperturaTurno={handleTurnoSubmit}
          onRefreshRooms={fetchHabitaciones}
          initialAddProduct={openAddProduct}
        />
      )}
    </div>
  );
}

export default App;
