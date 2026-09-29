import React, { useState, useEffect } from 'react';
import { LayoutGrid, Package, Lock, Bell, Settings } from 'lucide-react';

interface TopNavProps {
  activeView: string;
  setActiveView: (view: string) => void;
}

const getTurnoInfo = (h: number) => {
  if (h >= 6 && h < 14) return { label: 'Mañana', range: '06:00 – 14:00', bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', dot: 'bg-amber-400' };
  if (h >= 14 && h < 22) return { label: 'Tarde', range: '14:00 – 22:00', bg: 'bg-sky-50', text: 'text-sky-700', border: 'border-sky-200', dot: 'bg-sky-400' };
  return { label: 'Noche', range: '22:00 – 06:00', bg: 'bg-indigo-50', text: 'text-indigo-700', border: 'border-indigo-200', dot: 'bg-indigo-400' };
};

const TopNav: React.FC<TopNavProps> = ({ activeView, setActiveView }) => {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const turno = getTurnoInfo(time.getHours());

  return (
    <header className="bg-white/80 backdrop-blur-md border-b border-gray-200/60 h-16 flex items-center justify-between px-6 sticky top-0 z-40">
      {/* Left: Logo */}
      <div className="flex items-center space-x-5">
        <div className="flex items-center">
          <img src="/logo.png" alt="MotelOS" className="h-8 object-contain" />
        </div>
        
        <div className="h-5 w-px bg-gray-200 hidden md:block"></div>
        
        <div className="hidden md:flex items-center space-x-2">
          <span className="text-sm font-semibold text-slate-800">Recepción</span>
        </div>
      </div>

      {/* Center: Navigation */}
      <nav className="hidden lg:flex items-center space-x-1 h-full">
        <button 
          onClick={() => setActiveView('dashboard')}
          className={`flex items-center h-full px-4 border-b-2 transition-all ${
            activeView === 'dashboard' 
              ? 'border-slate-900 text-slate-900 font-semibold' 
              : 'border-transparent text-gray-400 hover:text-slate-700'
          }`}
        >
          <LayoutGrid className="w-4 h-4 mr-2" />
          <span className="text-sm">Dashboard</span>
        </button>
        <button 
          onClick={() => setActiveView('inventario')}
          className={`flex items-center h-full px-4 border-b-2 transition-all ${
            activeView === 'inventario' 
              ? 'border-slate-900 text-slate-900 font-semibold' 
              : 'border-transparent text-gray-400 hover:text-slate-700'
          }`}
        >
          <Package className="w-4 h-4 mr-2" />
          <span className="text-sm">Inventario</span>
        </button>
        <button 
          onClick={() => setActiveView('caja')}
          className={`flex items-center h-full px-4 border-b-2 transition-all ${
            activeView === 'caja' 
              ? 'border-slate-900 text-slate-900 font-semibold' 
              : 'border-transparent text-gray-400 hover:text-slate-700'
          }`}
        >
          <Lock className="w-4 h-4 mr-2" />
          <span className="text-sm">Cierre de Caja</span>
        </button>
      </nav>

      {/* Right: Status & Time */}
      <div className="flex items-center space-x-4">
        <div className={`hidden xl:flex items-center px-3 py-1.5 rounded-full text-xs font-semibold border ${turno.bg} ${turno.text} ${turno.border}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${turno.dot} mr-2`}></span>
          {turno.label} · {turno.range}
        </div>
        
        <div className="flex items-center space-x-2 text-gray-400">
          <button 
            onClick={() => alert("Módulo de Notificaciones en desarrollo (Sprint 4)")}
            className="p-2 rounded-lg hover:bg-gray-100 hover:text-slate-700 transition-colors"
          >
            <Bell className="w-[18px] h-[18px]" />
          </button>
          <button 
            onClick={() => alert("Módulo de Configuración en desarrollo (Sprint 4)")}
            className="p-2 rounded-lg hover:bg-gray-100 hover:text-slate-700 transition-colors"
          >
            <Settings className="w-[18px] h-[18px]" />
          </button>
        </div>

        <div className="h-5 w-px bg-gray-200"></div>

        <div className="flex items-center space-x-3">
          <span className="text-sm font-bold font-mono text-slate-900 tabular-nums tracking-tight">
            {time.toLocaleTimeString('es-AR', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <div className="flex items-center space-x-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
            </span>
            <span className="text-[11px] font-medium text-emerald-600">Online</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopNav;
