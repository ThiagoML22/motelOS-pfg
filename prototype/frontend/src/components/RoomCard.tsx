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
  const [showMenu, setShowMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

  const getStyle = () => {
    switch (room.estado) {
      case 'Libre':
        return {
          cardBg: 'bg-gradient-to-br from-white to-emerald-50/40',
          cardBorder: 'border-gray-200 hover:border-emerald-300',
          badgeBg: 'bg-emerald-50',
          badgeBorder: 'border-emerald-200',
          badgeText: 'text-emerald-600',
          badgeDot: 'bg-emerald-500',
          bottomText: 'text-gray-400 font-medium'
        };
      case 'Ocupada':
        return {
          cardBg: 'bg-gradient-to-br from-white to-rose-50/30',
          cardBorder: 'border-slate-300 hover:border-slate-400 shadow-sm',
          badgeBg: 'bg-rose-50',
          badgeBorder: 'border-rose-200',
          badgeText: 'text-rose-600',
          badgeDot: 'bg-rose-500',
          bottomText: 'text-rose-600 font-mono font-bold'
        };
      case 'En Limpieza':
        return {
          cardBg: 'bg-gradient-to-br from-white to-amber-50/40',
          cardBorder: 'border-amber-200 hover:border-amber-300',
          badgeBg: 'bg-amber-50',
          badgeBorder: 'border-amber-200',
          badgeText: 'text-amber-600',
          badgeDot: 'bg-amber-500',
          bottomText: 'text-gray-400 font-medium'
        };
      case 'Mantenimiento':
        return {
          cardBg: 'bg-gradient-to-br from-white to-slate-50',
          cardBorder: 'border-slate-200 hover:border-slate-300',
          badgeBg: 'bg-slate-100',
          badgeBorder: 'border-slate-200',
          badgeText: 'text-slate-500',
          badgeDot: 'bg-slate-400',
          bottomText: 'text-gray-400 font-medium'
        };
      default:
        return {
          cardBg: 'bg-white',
          cardBorder: 'border-gray-200',
          badgeBg: 'bg-gray-50',
          badgeBorder: 'border-gray-200',
          badgeText: 'text-gray-500',
          badgeDot: 'bg-gray-400',
          bottomText: 'text-gray-400 font-medium'
        };
    }
  };

  const style = getStyle();
  const displayState = room.estado === 'Libre' ? 'Disponible' : (room.estado === 'En Limpieza' ? 'Limpieza' : room.estado);

  const getTipoIcon = () => {
    const tipo = room.turno_activo?.tipo_cliente;
    if (tipo === 'Moto') return <Bike className="w-3.5 h-3.5 mr-1 text-slate-400" />;
    if (tipo === 'Peaton') return <Footprints className="w-3.5 h-3.5 mr-1 text-slate-400" />;
    return <Car className="w-3.5 h-3.5 mr-1 text-slate-400" />;
  };

  const getClienteLabel = () => {
    const turno = room.turno_activo;
    if (!turno) return '';
    if (turno.tipo_cliente === 'Peaton') return 'Peatón';
    return turno.identificador_vehicular || '';
  };

  const hasConsumos = isOcupada && room.turno_activo && room.turno_activo.total_consumos > 0;

  const handleStateChange = (e: React.MouseEvent, state: string) => {
    e.stopPropagation();
    setShowMenu(false);
    if (onChangeEstado) onChangeEstado(room, state);
  };

  return (
    <div 
      onClick={() => onClick(room)}
      className={`${style.cardBg} rounded-2xl border p-5 flex flex-col justify-between relative min-h-[148px] cursor-pointer transition-all duration-200 hover:shadow-lg hover:scale-[1.02] ${style.cardBorder}`}
    >
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h3 className="text-lg font-extrabold text-slate-900 tracking-tight">
            HAB {room.numero.toString().padStart(2, '0')}
          </h3>
          {isOcupada && room.turno_activo && (
            <div className="flex items-center mt-1.5">
              {getTipoIcon()}
              <span className="text-xs text-slate-400 font-medium truncate max-w-[120px]">
                {getClienteLabel()}
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <div className={`flex items-center px-2.5 py-1 rounded-full border ${style.badgeBg} ${style.badgeBorder}`}>
            <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${style.badgeDot}`}></span>
            <span className={`text-[10px] font-bold uppercase tracking-wider ${style.badgeText}`}>
              {displayState}
            </span>
          </div>
          {hasConsumos && (
            <div className="flex items-center px-2 py-0.5 rounded-full bg-blue-50 border border-blue-100 text-blue-600">
              <ShoppingBag className="w-3 h-3 mr-1" />
              <span className="text-[10px] font-bold">${room.turno_activo?.total_consumos}</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex justify-between items-end mt-auto pt-3">
        <div className="flex items-center">
          {isOcupada ? (
            <div className="flex items-center bg-rose-50 px-2.5 py-1 rounded-lg border border-rose-100">
              <Timer className="w-3.5 h-3.5 mr-1.5 text-rose-500" strokeWidth={2.5} />
              <span className={`text-sm ${style.bottomText}`}>
                {room.tiempo_transcurrido || '00:00:00'}
              </span>
            </div>
          ) : (
            <span className={`text-xs ${style.bottomText}`}>Sin ocupar</span>
          )}
        </div>
        
        <div className="flex items-center gap-1.5">
          {isOcupada && onAddConsumo && (
            <button
              onClick={(e) => { e.stopPropagation(); onAddConsumo(room); }}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-indigo-50 text-indigo-600 hover:bg-indigo-100 border border-indigo-100 transition-colors text-[11px] font-bold"
            >
              <ShoppingBag className="w-3.5 h-3.5" />
              + Producto
            </button>
          )}

          {!isOcupada && (
            <div className="relative" ref={menuRef}>
              <button 
                onClick={(e) => { e.stopPropagation(); setShowMenu(!showMenu); }}
                className="w-7 h-7 rounded-lg bg-white/80 flex items-center justify-center border border-gray-200 hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
              >
                <MoreVertical className="w-3.5 h-3.5" />
              </button>
              
              {showMenu && (
                <div className="absolute bottom-full right-0 mb-2 w-44 bg-white border border-gray-200 rounded-xl shadow-xl overflow-hidden z-50">
                  {room.estado !== 'Libre' && (
                    <button onClick={(e) => handleStateChange(e, 'Libre')}
                      className="w-full text-left px-3.5 py-2.5 text-sm hover:bg-gray-50 flex items-center text-slate-700 border-b border-gray-50 transition-colors">
                      <CheckCircle2 className="w-4 h-4 mr-2.5 text-emerald-500" /> Disponible
                    </button>
                  )}
                  {room.estado !== 'En Limpieza' && (
                    <button onClick={(e) => handleStateChange(e, 'En Limpieza')}
                      className="w-full text-left px-3.5 py-2.5 text-sm hover:bg-gray-50 flex items-center text-slate-700 border-b border-gray-50 transition-colors">
                      <Sparkles className="w-4 h-4 mr-2.5 text-amber-500" /> Limpieza
                    </button>
                  )}
                  {room.estado !== 'Mantenimiento' && (
                    <button onClick={(e) => handleStateChange(e, 'Mantenimiento')}
                      className="w-full text-left px-3.5 py-2.5 text-sm hover:bg-gray-50 flex items-center text-slate-700 transition-colors">
                      <Wrench className="w-4 h-4 mr-2.5 text-slate-400" /> Mantenimiento
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {isOcupada && (
            <div className="w-7 h-7 rounded-lg bg-white/80 flex items-center justify-center border border-gray-200 hover:bg-gray-100 transition-colors">
              <ChevronRight className="w-3.5 h-3.5 text-gray-400" strokeWidth={2.5} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RoomCard;
