import React, { useState, useRef, useEffect } from 'react';
import { ChevronRight, Timer, Car, Bike, Footprints, ShoppingBag, MoreVertical, Wrench, Sparkles, CheckCircle2 } from 'lucide-react';
import { HabitacionConDetalles } from '../types';

interface RoomCardProps {
  room: HabitacionConDetalles;
  onClick: (room: HabitacionConDetalles) => void;
  onAddConsumo?: (room: HabitacionConDetalles) => void;
  onChangeEstado?: (room: HabitacionConDetalles, newState: string) => void;
}

const RoomCard: React.FC<RoomCardProps> = ({ room, onClick, onAddConsumo, onChangeEstado }) => {
  const isOcupada = room.estado === 'Ocupada';
  const [showSettings, setShowSettings] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowSettings(false);
      }
    };
    if (showSettings) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showSettings]);

  const getStyle = () => {
    switch (room.estado) {
      case 'Libre':
        return {
          cardBorder: 'border-gray-200',
          badgeBorder: 'border-emerald-200',
          badgeText: 'text-emerald-500',
          badgeDot: 'bg-emerald-500',
          bottomText: 'text-gray-400 font-medium'
        };
      case 'Ocupada':
        return {
          cardBorder: 'border-slate-800 shadow-sm',
          badgeBorder: 'border-rose-200',
          badgeText: 'text-rose-500',
          badgeDot: 'bg-rose-500',
          bottomText: 'text-rose-500 font-mono font-bold'
        };
      case 'En Limpieza':
        return {
          cardBorder: 'border-amber-200 shadow-sm',
          badgeBorder: 'border-amber-200',
          badgeText: 'text-amber-500',
          badgeDot: 'bg-amber-500',
          bottomText: 'text-gray-400 font-medium'
        };
      case 'Mantenimiento':
        return {
          cardBorder: 'border-slate-200',
          badgeBorder: 'border-slate-300',
          badgeText: 'text-slate-500',
          badgeDot: 'bg-slate-500',
          bottomText: 'text-gray-400 font-medium'
        };
      default:
        return {
          cardBorder: 'border-gray-200',
          badgeBorder: 'border-gray-200',
          badgeText: 'text-gray-500',
          badgeDot: 'bg-gray-500',
          bottomText: 'text-gray-400 font-medium'
        };
    }
  };

  const style = getStyle();
  const displayState = room.estado === 'Libre' ? 'Disponible' : (room.estado === 'En Limpieza' ? 'Limpieza' : room.estado);

  const getTipoIcon = () => {
    const tipo = room.turno_activo?.tipo_cliente;
    if (tipo === 'Moto') return <Bike className="w-3.5 h-3.5 mr-1 text-slate-500" />;
    if (tipo === 'Peaton') return <Footprints className="w-3.5 h-3.5 mr-1 text-slate-500" />;
    return <Car className="w-3.5 h-3.5 mr-1 text-slate-500" />;
  };

  const getClienteLabel = () => {
    const turno = room.turno_activo;
    if (!turno) return '';
    if (turno.tipo_cliente === 'Peaton') return 'Peatón';
    return turno.identificador_vehicular || '';
  };

  const hasConsumos = isOcupada && room.turno_activo && room.turno_activo.total_consumos > 0;

  const handleStateChangeClick = (e: React.MouseEvent, state: string) => {
    e.stopPropagation();
    setShowSettings(false);
    if (onChangeEstado) {
      onChangeEstado(room, state);
    }
  };

  return (
    <div 
      onClick={() => onClick(room)}
      className={`bg-white rounded-2xl border-2 p-5 flex flex-col justify-between relative ${isOcupada ? 'h-[170px]' : 'h-[140px]'} cursor-pointer transition-all hover:shadow-md ${style.cardBorder}`}
    >
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-xl font-bold text-slate-900 tracking-tight">
            HAB {room.numero.toString().padStart(2, '0')}
          </h3>
          {isOcupada && room.turno_activo && (
            <div className="flex items-center mt-1">
              {getTipoIcon()}
              <span className="text-xs text-slate-500 font-medium truncate max-w-[120px]">
                {getClienteLabel()}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5 relative">
          <div className={`flex items-center px-2.5 py-0.5 rounded-full border ${style.badgeBorder}`}>
            <span className={`w-2 h-2 rounded-full mr-1.5 ${style.badgeDot}`}></span>
            <span className={`text-[11px] font-bold uppercase tracking-wider ${style.badgeText}`}>
              {displayState}
            </span>
          </div>
          {hasConsumos && (
            <div className="flex items-center px-2 py-0.5 rounded bg-blue-50 border border-blue-100 text-blue-700">
              <ShoppingBag className="w-3 h-3 mr-1" />
              <span className="text-[10px] font-bold">${room.turno_activo.total_consumos}</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex justify-between items-end mt-auto">
        <div className="flex items-center">
          {isOcupada ? (
            <>
              <Timer className="w-4 h-4 mr-1.5 text-rose-500" strokeWidth={2.5} />
              <span className={`text-base ${style.bottomText}`}>
                {room.tiempo_transcurrido || '00:00:00'}
              </span>
            </>
          ) : (
            <span className={`text-sm ${style.bottomText}`}>Sin ocupar</span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {isOcupada && onAddConsumo && (
            <button
              onClick={(e) => { e.stopPropagation(); onAddConsumo(room); }}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition-colors shadow-sm"
            >
              <ShoppingBag className="w-3.5 h-3.5" />
              <span className="text-[11px] font-bold">+ Producto</span>
            </button>
          )}

          {!isOcupada && (
            <div className="relative" ref={menuRef}>
              <button 
                onClick={(e) => { e.stopPropagation(); setShowSettings(!showSettings); }}
                className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center border border-gray-100 hover:bg-gray-200 transition-colors text-slate-500"
              >
                <MoreVertical className="w-4 h-4" />
              </button>
              
              {showSettings && (
                <div className="absolute bottom-full right-0 mb-2 w-48 bg-white border border-gray-200 rounded-xl shadow-xl overflow-hidden z-50">
                  {room.estado !== 'Libre' && (
                    <button 
                      onClick={(e) => handleStateChangeClick(e, 'Libre')}
                      className="w-full text-left px-4 py-2.5 text-sm hover:bg-slate-50 flex items-center text-slate-700 border-b border-gray-50"
                    >
                      <CheckCircle2 className="w-4 h-4 mr-2 text-emerald-500" /> Disponible
                    </button>
                  )}
                  {room.estado !== 'En Limpieza' && (
                    <button 
                      onClick={(e) => handleStateChangeClick(e, 'En Limpieza')}
                      className="w-full text-left px-4 py-2.5 text-sm hover:bg-slate-50 flex items-center text-slate-700 border-b border-gray-50"
                    >
                      <Sparkles className="w-4 h-4 mr-2 text-amber-500" /> Limpieza
                    </button>
                  )}
                  {room.estado !== 'Mantenimiento' && (
                    <button 
                      onClick={(e) => handleStateChangeClick(e, 'Mantenimiento')}
                      className="w-full text-left px-4 py-2.5 text-sm hover:bg-slate-50 flex items-center text-slate-700"
                    >
                      <Wrench className="w-4 h-4 mr-2 text-slate-500" /> Mantenimiento
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {isOcupada && (
            <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center border border-gray-100 hover:bg-gray-100 transition-colors">
              <ChevronRight className="w-4 h-4 text-slate-400" strokeWidth={3} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RoomCard;
