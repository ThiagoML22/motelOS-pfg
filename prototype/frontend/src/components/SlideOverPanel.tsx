import React, { useState, useEffect } from 'react';
import { X, Plus, Minus, CreditCard, Banknote, Receipt, Car, Bike, Footprints } from 'lucide-react';
import { HabitacionConDetalles, Articulo, TurnoResumen, TipoCliente } from '../types';
import { api } from '../services/api';

interface SlideOverPanelProps {
  room: HabitacionConDetalles;
  onClose: () => void;
  onAperturaTurno?: (patente: string, tipoCliente: TipoCliente) => void;
  onRefreshRooms?: () => void;
  initialAddProduct?: boolean;
}

const getHeaderStyle = (estado: string) => {
  switch (estado) {
    case 'Libre': return 'bg-gradient-to-r from-emerald-50 to-white border-emerald-100';
    case 'Ocupada': return 'bg-gradient-to-r from-rose-50 to-white border-rose-100';
    case 'En Limpieza': return 'bg-gradient-to-r from-amber-50 to-white border-amber-100';
    default: return 'bg-slate-50 border-gray-100';
  }
};

const SlideOverPanel: React.FC<SlideOverPanelProps> = ({ room, onClose, onAperturaTurno, onRefreshRooms, initialAddProduct = false }) => {
  const isOcupada = room.estado === 'Ocupada';
  const isLibre = room.estado === 'Libre';
  const isLimpieza = room.estado === 'En Limpieza';
  
  const [patente, setPatente] = useState('');
  const [tipoCliente, setTipoCliente] = useState<TipoCliente>('Auto');
  
  const [resumen, setResumen] = useState<TurnoResumen | null>(null);
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [addingProduct, setAddingProduct] = useState(initialAddProduct);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  
  const [isCheckout, setIsCheckout] = useState(false);
  const [medioPago, setMedioPago] = useState('EFECTIVO');
  const [comprobante, setComprobante] = useState('');

  useEffect(() => {
    if (isOcupada && room.turno_activo?.id) {
      loadResumenAndArticulos(room.turno_activo.id);
    }
  }, [isOcupada, room]);

  const loadResumenAndArticulos = async (turnoId: string) => {
    try {
      const [res, arts] = await Promise.all([
        api.getResumen(turnoId),
        api.getArticulos()
      ]);
      setResumen(res);
      setArticulos(arts);
    } catch (e) {
      console.error(e);
    }
  };

  const handleQtyChange = (artId: number, delta: number) => {
    const art = articulos.find(a => a.id === artId);
    if (!art) return;
    const current = quantities[artId] || 0;
    const next = current + delta;
    if (next >= 0 && next <= art.stock_actual) {
      setQuantities({ ...quantities, [artId]: next });
    }
  };

  const handleAddConsumo = async () => {
    if (!resumen?.id) return;
    try {
      for (const artId in quantities) {
        const qty = quantities[artId];
        if (qty > 0) {
          await api.addConsumo(resumen.id, parseInt(artId), qty);
        }
      }
      setQuantities({});
      
      if (initialAddProduct) {
        if (onRefreshRooms) onRefreshRooms();
        onClose();
      } else {
        setAddingProduct(false);
        await loadResumenAndArticulos(resumen.id);
      }
    } catch (e: any) {
      alert(e.response?.data?.detail || "Error al agregar consumo");
    }
  };

  const handleCobrar = async () => {
    if (!resumen?.id) return;
    if ((medioPago === 'POSNET' || medioPago === 'MERCADO_PAGO') && !comprobante) {
      alert("Ingrese el número de comprobante");
      return;
    }
    try {
      await api.cerrarTurno(resumen.id, resumen.total_general, medioPago, comprobante);
      if (onRefreshRooms) onRefreshRooms();
      onClose();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Error al cobrar");
    }
  };
  
  const handleLiberar = async () => {
      try {
          await api.liberarHabitacion(room.id);
          if (onRefreshRooms) onRefreshRooms();
          onClose();
      } catch(e: any) {
          alert("Error al liberar");
      }
  };

  const handleApertura = () => {
    if (!onAperturaTurno) return;
    const identificador = tipoCliente === 'Peaton' ? 'S/V' : patente.trim();
    if (tipoCliente !== 'Peaton' && !identificador) return;
    onAperturaTurno(identificador, tipoCliente);
  };

  return (
    <>
      <div className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-50 transition-opacity" onClick={onClose} />

      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-white shadow-2xl border-l border-gray-100 flex flex-col">
        
        {/* Header with contextual gradient */}
        <div className={`flex items-center justify-between px-6 py-5 border-b ${getHeaderStyle(room.estado)}`}>
          <div className="flex items-center space-x-3">
            <h2 className="text-xl font-extrabold text-slate-900">
              HAB {room.numero.toString().padStart(2, '0')}
            </h2>
            <span className="text-gray-400 text-sm font-medium">— {isOcupada ? 'Cuenta Corriente' : isLibre ? 'Apertura' : 'Limpieza'}</span>
          </div>
          <button onClick={onClose} className="p-2 rounded-xl hover:bg-white/80 text-gray-400 hover:text-gray-600 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* APERTURA */}
          {isLibre && (
            <div className="p-6">
               <form onSubmit={(e) => { e.preventDefault(); handleApertura(); }}>
                  <div className="mb-6">
                    <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-3">Tipo de Cliente</label>
                    <div className="grid grid-cols-3 gap-3">
                      {([
                        { value: 'Auto' as TipoCliente, icon: Car, label: 'Auto' },
                        { value: 'Moto' as TipoCliente, icon: Bike, label: 'Moto' },
                        { value: 'Peaton' as TipoCliente, icon: Footprints, label: 'Peatón' },
                      ]).map(opt => (
                        <button key={opt.value} type="button" onClick={() => setTipoCliente(opt.value)}
                          className={`p-3.5 rounded-xl border flex flex-col items-center justify-center transition-all ${
                            tipoCliente === opt.value 
                              ? 'border-slate-900 bg-slate-50 text-slate-900 shadow-sm' 
                              : 'border-gray-200 text-gray-400 hover:border-gray-300 hover:text-gray-500'
                          }`}>
                          <opt.icon className="w-5 h-5 mb-1.5" />
                          <span className="text-xs font-bold">{opt.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {tipoCliente !== 'Peaton' && (
                    <div className="mb-6">
                      <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Identificador Vehicular</label>
                      <input 
                        type="text" autoFocus required
                        className="w-full border border-gray-200 rounded-xl px-4 py-3 text-lg uppercase focus:border-slate-900 focus:ring-0 outline-none transition-colors"
                        placeholder="AB 123 CD"
                        value={patente}
                        onChange={(e) => setPatente(e.target.value.toUpperCase())}
                      />
                    </div>
                  )}

                  <button type="submit" disabled={tipoCliente !== 'Peaton' && !patente.trim()} className="w-full bg-slate-900 text-white font-bold py-3.5 rounded-xl hover:bg-slate-800 disabled:opacity-40 transition-colors shadow-sm">
                    Ocupar Habitación
                  </button>
               </form>
            </div>
          )}

          {/* LIMPIEZA */}
          {isLimpieza && (
            <div className="p-6 flex flex-col items-center justify-center h-full space-y-4">
               <div className="w-16 h-16 rounded-2xl bg-amber-50 flex items-center justify-center border border-amber-100">
                 <span className="text-3xl">🧹</span>
               </div>
               <h3 className="text-lg font-bold text-slate-900">Habitación en Limpieza</h3>
               <p className="text-sm text-gray-400 text-center max-w-xs">Marque como lista cuando finalice el reacondicionamiento.</p>
               <button onClick={handleLiberar} className="mt-2 w-full bg-emerald-500 text-white font-bold py-3.5 rounded-xl hover:bg-emerald-600 transition-colors shadow-sm">
                  Marcar como Disponible
               </button>
            </div>
          )}

          {/* CUENTA CORRIENTE */}
          {isOcupada && resumen && !addingProduct && !isCheckout && (
            <div className="p-6 flex flex-col h-full">
              <div className="mb-6">
                <h3 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-3">Detalle de Estadía</h3>
                <div className="space-y-2.5 text-sm bg-gradient-to-br from-gray-50 to-white p-4 rounded-xl border border-gray-100">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Tarifa Base (2 hs)</span>
                    <span className="font-semibold text-slate-800 tabular-nums">${resumen.tarifa_base}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Sobreturno ({Math.max(0, resumen.minutos_transcurridos - 120)} min)</span>
                    <span className="font-semibold text-rose-500 tabular-nums">${resumen.total_sobreturno}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Tiempo Transcurrido</span>
                    <span className="font-mono font-bold text-slate-800">{room.tiempo_transcurrido}</span>
                  </div>
                  <div className="pt-2.5 border-t border-gray-100 flex justify-between mt-1">
                    <span className="font-bold text-slate-800">Subtotal Estadía</span>
                    <span className="font-bold text-slate-800 tabular-nums">${resumen.tarifa_base + resumen.total_sobreturno}</span>
                  </div>
                </div>
              </div>

              <div className="mb-6 flex-1">
                <h3 className="text-[11px] font-bold text-gray-400 uppercase tracking-widest mb-3">Consumos</h3>
                <div className="space-y-2">
                  {resumen.consumos.length === 0 ? (
                      <p className="text-sm text-gray-400 italic">Sin consumos registrados.</p>
                  ) : (
                      resumen.consumos.map((c, i) => {
                          const art = articulos.find(a => a.id === c.articulo_id);
                          return (
                            <div key={i} className="flex justify-between text-sm items-center py-2 border-b border-gray-50">
                                <span className="text-slate-700">{art?.descripcion || 'Producto'} <span className="text-gray-400">×{c.cantidad}</span></span>
                                <span className="font-semibold text-slate-800 tabular-nums">${c.subtotal}</span>
                            </div>
                          );
                      })
                  )}
                </div>
              </div>

              <div className="border-t border-gray-100 pt-6 mt-auto">
                <div className="space-y-2 mb-6">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-400">Subtotal Productos</span>
                    <span className="font-semibold text-slate-800 tabular-nums">${resumen.total_consumos}</span>
                  </div>
                  <div className="flex justify-between items-center pt-2">
                    <span className="font-bold text-slate-800 uppercase tracking-wide text-sm">Total a Cobrar</span>
                    <span className="font-extrabold text-3xl text-slate-900 tabular-nums">${resumen.total_general}</span>
                  </div>
                </div>
                
                <div className="space-y-2.5">
                  <button onClick={() => setAddingProduct(true)} className="w-full bg-white text-slate-700 font-semibold py-3 rounded-xl border border-gray-200 hover:bg-gray-50 hover:border-gray-300 transition-colors">
                    + Agregar Producto
                  </button>
                  <button onClick={() => setIsCheckout(true)} className="w-full bg-slate-900 text-white font-bold py-3.5 rounded-xl hover:bg-slate-800 transition-colors shadow-sm">
                    Finalizar y Cobrar
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* MINIBAR */}
          {isOcupada && addingProduct && (
              <div className="p-6 flex flex-col h-full">
                  <h3 className="text-lg font-bold text-slate-900 mb-4">Despacho de Minibar</h3>
                  <div className="flex-1 overflow-y-auto space-y-3">
                      {articulos.map(art => (
                          <div key={art.id} className="flex items-center justify-between p-3.5 border border-gray-100 rounded-xl bg-gradient-to-r from-gray-50/50 to-white hover:border-gray-200 transition-colors">
                              <div className="flex flex-col">
                                  <span className="font-semibold text-slate-800 text-sm">{art.descripcion}</span>
                                  <span className="text-xs text-gray-400 mt-0.5">Stock: {art.stock_actual} · ${art.precio_unitario}</span>
                              </div>
                              <div className="flex items-center bg-white rounded-xl border border-gray-200 shadow-sm">
                                  <button type="button" onClick={() => handleQtyChange(art.id, -1)} className="p-2 text-gray-400 hover:text-slate-900 transition-colors"><Minus className="w-3.5 h-3.5" /></button>
                                  <span className="w-7 text-center font-bold text-sm text-slate-900 tabular-nums">{quantities[art.id] || 0}</span>
                                  <button type="button" onClick={() => handleQtyChange(art.id, 1)} className="p-2 text-gray-400 hover:text-slate-900 transition-colors"><Plus className="w-3.5 h-3.5" /></button>
                              </div>
                          </div>
                      ))}
                  </div>
                  <div className="pt-5 mt-4 border-t border-gray-100 flex space-x-3">
                      <button onClick={() => {
                        if (initialAddProduct) {
                          onClose();
                        } else {
                          setAddingProduct(false); 
                          setQuantities({});
                        }
                      }} className="flex-1 bg-white text-slate-600 font-semibold py-3 rounded-xl border border-gray-200 hover:bg-gray-50 transition-colors">
                        {initialAddProduct ? 'Cancelar' : 'Volver'}
                      </button>
                      <button onClick={handleAddConsumo} className="flex-1 bg-indigo-600 text-white font-bold py-3 rounded-xl hover:bg-indigo-700 transition-colors shadow-sm">Guardar en la Cuenta</button>
                  </div>
              </div>
          )}

          {/* CHECKOUT */}
          {isOcupada && isCheckout && resumen && (
              <div className="p-6 flex flex-col h-full">
                  <h3 className="text-lg font-bold text-slate-900 mb-6">Liquidación de Turno</h3>
                  
                  <div className="bg-gradient-to-br from-slate-900 to-slate-800 text-white p-6 rounded-2xl mb-8 flex flex-col items-center justify-center shadow-lg">
                      <span className="text-xs text-slate-400 uppercase tracking-widest font-medium mb-1">Total a Pagar</span>
                      <span className="text-4xl font-extrabold tracking-tight tabular-nums">${resumen.total_general}</span>
                  </div>

                  <div className="space-y-4 flex-1">
                      <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider">Medio de Pago</label>
                      <div className="grid grid-cols-2 gap-3">
                          <button onClick={() => setMedioPago('EFECTIVO')} className={`p-4 rounded-xl border flex flex-col items-center justify-center transition-all ${medioPago === 'EFECTIVO' ? 'border-indigo-500 bg-indigo-50 text-indigo-700 shadow-sm' : 'border-gray-200 text-gray-400 hover:border-gray-300'}`}>
                              <Banknote className="w-5 h-5 mb-2" />
                              <span className="text-sm font-bold">Efectivo</span>
                          </button>
                          <button onClick={() => setMedioPago('POSNET')} className={`p-4 rounded-xl border flex flex-col items-center justify-center transition-all ${medioPago === 'POSNET' ? 'border-indigo-500 bg-indigo-50 text-indigo-700 shadow-sm' : 'border-gray-200 text-gray-400 hover:border-gray-300'}`}>
                              <CreditCard className="w-5 h-5 mb-2" />
                              <span className="text-sm font-bold">Tarjeta / MP</span>
                          </button>
                      </div>

                      {medioPago === 'POSNET' && (
                          <div className="mt-4">
                              <label className="block text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">Nº Comprobante / Lote</label>
                              <div className="relative">
                                <Receipt className="absolute left-3 top-3 w-4 h-4 text-gray-400" />
                                <input type="text" value={comprobante} onChange={e => setComprobante(e.target.value)} placeholder="000123456" className="w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl outline-none focus:border-indigo-500 font-mono text-sm transition-colors" />
                              </div>
                          </div>
                      )}
                  </div>

                  <div className="pt-5 mt-4 border-t border-gray-100 flex space-x-3">
                      <button onClick={() => setIsCheckout(false)} className="flex-1 bg-white text-slate-600 font-semibold py-3 rounded-xl border border-gray-200 hover:bg-gray-50 transition-colors">Cancelar</button>
                      <button onClick={handleCobrar} className="flex-1 bg-emerald-500 text-white font-bold py-3 rounded-xl hover:bg-emerald-600 shadow-sm transition-colors">Confirmar Pago</button>
                  </div>
              </div>
          )}

        </div>
      </div>
    </>
  );
};

export default SlideOverPanel;
