import React, { useState, useEffect } from 'react';
import { LayoutGrid, Package, Lock, Bell, Settings } from 'lucide-react';

interface TopNavProps {
  activeView: string;
  setActiveView: (view: string) => void;
}

const TopNav: React.FC<TopNavProps> = ({ activeView, setActiveView }) => {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="bg-white border-b border-gray-200 h-16 flex items-center justify-between px-6 sticky top-0 z-40">
      {/* Left section: Branding & User */}
      <div className="flex items-center space-x-6">
        <div className="flex items-center">
          <img src="/logo.png" alt="MotelOS" className="h-8 object-contain" />
        </div>
        
        <div className="h-6 w-px bg-gray-300 hidden md:block"></div>
        
        <div className="hidden md:flex items-center space-x-2">
          <span className="text-sm font-semibold text-slate-800">Carlos Méndez</span>
          <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-[10px] font-bold uppercase tracking-widest rounded-md border border-gray-200">
            Conserje
          </span>
        </div>
      </div>

      {/* Center section: Navigation */}
      <nav className="hidden lg:flex items-center space-x-8 h-full">
        <button 
          onClick={() => setActiveView('dashboard')}
          className={`flex items-center h-full border-b-2 px-1 transition-colors ${
            activeView === 'dashboard' ? 'border-slate-900 text-slate-900 font-semibold' : 'border-transparent text-gray-500 hover:text-slate-800'
          }`}
        >
          <LayoutGrid className="w-4 h-4 mr-2" />
          <span className="text-sm">Dashboard</span>
        </button>
        <button 
          onClick={() => setActiveView('inventario')}
          className={`flex items-center h-full border-b-2 px-1 transition-colors ${
            activeView === 'inventario' ? 'border-slate-900 text-slate-900 font-semibold' : 'border-transparent text-gray-500 hover:text-slate-800'
          }`}
        >
          <Package className="w-4 h-4 mr-2" />
          <span className="text-sm">Inventario</span>
        </button>
        <button 
          onClick={() => setActiveView('caja')}
          className={`flex items-center h-full border-b-2 px-1 transition-colors ${
            activeView === 'caja' ? 'border-slate-900 text-slate-900 font-semibold' : 'border-transparent text-gray-500 hover:text-slate-800'
          }`}
        >
          <Lock className="w-4 h-4 mr-2" />
          <span className="text-sm">Cierre de Caja</span>
        </button>
      </nav>

      {/* Right section: Status & Time */}
      <div className="flex items-center space-x-5">
        <div className="hidden xl:flex bg-gray-100 px-3 py-1.5 rounded-full text-xs font-medium text-gray-600 border border-gray-200">
          Turno: {(() => {
            const h = time.getHours();
            if (h >= 6 && h < 14) return 'Mañana (06:00–14:00)';
            if (h >= 14 && h < 22) return 'Tarde (14:00–22:00)';
            return 'Noche (22:00–06:00)';
          })()}
        </div>
        
        <div className="flex items-center space-x-3 text-gray-500">
          <button 
            onClick={() => alert("Módulo de Notificaciones en desarrollo (Sprint 4)")}
            className="relative hover:text-slate-800 transition-colors"
          >
            <Bell className="w-5 h-5" />
          </button>
          <button 
            onClick={() => alert("Módulo de Configuración en desarrollo (Sprint 4)")}
            className="hover:text-slate-800 transition-colors"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>

        <div className="flex items-center space-x-3">
          <span className="text-sm font-bold font-mono text-slate-900">
            {time.toLocaleTimeString('en-US', { hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
          <div className="flex items-center space-x-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            <span className="text-xs font-medium text-emerald-600">Online</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopNav;
