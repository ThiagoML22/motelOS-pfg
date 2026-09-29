import React, { useState, useEffect, useMemo } from 'react';
import { Search, Plus, X, Package, ChevronRight, ArrowLeft } from 'lucide-react';
import { Articulo } from '../types';
import { api } from '../services/api';

const CATEGORIAS_BASE = ['Bebidas', 'Snacks', 'Farmacia', 'Blanquería'];

const getCategoryStyle = (cat: string) => {
  switch (cat) {
    case 'Bebidas': return 'bg-sky-50 text-sky-700 border-sky-100';
    case 'Snacks': return 'bg-orange-50 text-orange-700 border-orange-100';
    case 'Farmacia': return 'bg-violet-50 text-violet-700 border-violet-100';
    case 'Blanquería': return 'bg-pink-50 text-pink-700 border-pink-100';
    default: return 'bg-gray-50 text-gray-600 border-gray-200';
  }
};

const getCategoryIconStyle = (cat: string) => {
  switch (cat) {
    case 'Bebidas': return 'bg-sky-100 text-sky-600 border-sky-200';
    case 'Snacks': return 'bg-orange-100 text-orange-600 border-orange-200';
    case 'Farmacia': return 'bg-violet-100 text-violet-600 border-violet-200';
    case 'Blanquería': return 'bg-pink-100 text-pink-600 border-pink-200';
    default: return 'bg-gray-100 text-gray-500 border-gray-200';
  }
};

const InventarioView: React.FC = () => {
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Vistas y navegación
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  // Modal y formulario
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [codigo, setCodigo] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [categoria, setCategoria] = useState('');
  const [precio, setPrecio] = useState('');
  const [stock, setStock] = useState('');

  useEffect(() => {
    fetchArticulos();
  }, []);

  const fetchArticulos = async () => {
    try {
      const data = await api.getArticulos();
      setArticulos(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.createArticulo({
        codigo: codigo.toUpperCase(),
        descripcion,
        categoria,
        precio_unitario: parseFloat(precio),
        stock_actual: parseInt(stock, 10)
      });
      setIsModalOpen(false);
      setCodigo(''); setDescripcion(''); setCategoria(''); setPrecio(''); setStock('');
      fetchArticulos();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Error al crear el artículo");
    }
  };

  const openModalForCategory = (cat?: string) => {
    setCategoria(cat || '');
    setIsModalOpen(true);
  };

  // Agrupar artículos por categoría
  const itemsPorCategoria = useMemo(() => {
    const agrupados = CATEGORIAS_BASE.reduce((acc, cat) => {
      acc[cat] = [];
      return acc;
    }, {} as Record<string, Articulo[]>);

    articulos.forEach(art => {
      const cat = art.categoria || 'General';
      if (!agrupados[cat]) agrupados[cat] = [];
      agrupados[cat].push(art);
    });
    return agrupados;
  }, [articulos]);

  // Filtrado general por búsqueda
  const isSearching = searchTerm.trim().length > 0;
  const filteredSearchItems = useMemo(() => {
    if (!isSearching) return [];
    const term = searchTerm.toLowerCase();
    return articulos.filter(a => 
      a.codigo.toLowerCase().includes(term) ||
      a.descripcion.toLowerCase().includes(term) ||
      (a.categoria && a.categoria.toLowerCase().includes(term))
    );
  }, [articulos, searchTerm, isSearching]);

  // Artículos de la categoría seleccionada
  const categoryItems = selectedCategory ? itemsPorCategoria[selectedCategory] || [] : [];

  const renderTable = (items: Articulo[], emptyMessage: string) => (
    <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50/50">
            <th className="py-3 px-5 text-[11px] font-bold text-gray-400 uppercase tracking-widest">Código</th>
            <th className="py-3 px-5 text-[11px] font-bold text-gray-400 uppercase tracking-widest">Descripción</th>
            <th className="py-3 px-5 text-[11px] font-bold text-gray-400 uppercase tracking-widest">Categoría</th>
            <th className="py-3 px-5 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">Precio</th>
            <th className="py-3 px-5 text-[11px] font-bold text-gray-400 uppercase tracking-widest text-right">Stock</th>
          </tr>
        </thead>
        <tbody>
          {items.map((art, i) => (
            <tr key={art.id} className={`border-b border-gray-50 hover:bg-blue-50/30 transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/40'}`}>
              <td className="py-3.5 px-5 text-sm font-mono text-slate-400">{art.codigo}</td>
              <td className="py-3.5 px-5 text-sm font-semibold text-slate-800">{art.descripcion}</td>
              <td className="py-3.5 px-5">
                <span className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border ${getCategoryStyle(art.categoria)}`}>
                  {art.categoria || 'General'}
                </span>
              </td>
              <td className="py-3.5 px-5 text-sm font-semibold text-slate-800 text-right tabular-nums">${art.precio_unitario}</td>
              <td className="py-3.5 px-5 text-right">
                <span className={`inline-flex items-center justify-center px-2.5 py-1 rounded-lg text-sm font-bold min-w-[2.5rem] ${
                  art.stock_actual > 5 ? 'bg-emerald-50 text-emerald-600 border border-emerald-100' 
                  : art.stock_actual > 0 ? 'bg-amber-50 text-amber-600 border border-amber-100' 
                  : 'bg-rose-50 text-rose-600 border border-rose-100'
                }`}>
                  {art.stock_actual}
                </span>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={5} className="py-12 text-center text-gray-400 text-sm font-medium">
                {emptyMessage}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex justify-between items-end mb-8">
        <div>
          {selectedCategory && !isSearching ? (
            <div className="flex items-center space-x-3 mb-1 animate-in fade-in slide-in-from-left-4">
              <button 
                onClick={() => setSelectedCategory(null)}
                className="p-1.5 rounded-lg bg-white border border-gray-200 text-gray-500 hover:text-slate-900 hover:bg-gray-50 transition-colors shadow-sm"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <span className="text-sm font-bold text-gray-400 uppercase tracking-widest">Categorías</span>
            </div>
          ) : (
            <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">Inventario y Minibar</h1>
          )}
          
          <h2 className="text-slate-500 mt-1 text-sm font-medium">
            {isSearching 
              ? `Resultados de búsqueda para "${searchTerm}"` 
              : selectedCategory 
                ? <span className="text-2xl font-extrabold text-slate-900">{selectedCategory}</span>
                : `Gestión de stock en tiempo real · ${articulos.length} productos en total`
            }
          </h2>
        </div>
        
        <button 
          onClick={() => openModalForCategory(selectedCategory && !isSearching ? selectedCategory : undefined)}
          className="bg-slate-900 text-white font-semibold py-2.5 px-5 rounded-xl flex items-center hover:bg-slate-800 transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4 mr-2" />
          {selectedCategory && !isSearching ? `Nuevo en ${selectedCategory}` : 'Nuevo Artículo'}
        </button>
      </div>

      {/* Barra de Búsqueda */}
      <div className="mb-6 relative max-w-xl">
        <Search className={`absolute left-4 top-3.5 w-5 h-5 ${isSearching ? 'text-indigo-500' : 'text-gray-400'} transition-colors`} />
        <input 
          type="text" 
          placeholder="Buscar producto por código, nombre o categoría..." 
          className="w-full pl-12 pr-4 py-3 bg-white border border-gray-200 rounded-2xl text-sm focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 outline-none transition-all shadow-sm font-medium"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
        {isSearching && (
          <button onClick={() => setSearchTerm('')} className="absolute right-4 top-3.5 text-gray-400 hover:text-slate-600">
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Contenido Principal */}
      {loading ? (
         <div className="p-12 text-center text-gray-400 text-sm">Cargando inventario...</div>
      ) : isSearching ? (
         // Vista de Búsqueda
         renderTable(filteredSearchItems, 'No se encontraron resultados para tu búsqueda.')
      ) : selectedCategory ? (
         // Vista de Detalle de Categoría
         <div className="animate-in fade-in slide-in-from-bottom-4">
           {renderTable(categoryItems, `No hay artículos registrados en la categoría ${selectedCategory}.`)}
         </div>
      ) : (
         // Vista Grid de Categorías
         <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 animate-in fade-in">
           {Object.entries(itemsPorCategoria).map(([cat, items]) => (
             <div 
               key={cat} 
               onClick={() => setSelectedCategory(cat)}
               className="bg-white border border-gray-200 rounded-2xl p-6 hover:shadow-lg hover:-translate-y-1 cursor-pointer transition-all duration-200 flex flex-col h-[280px] group"
             >
               <div className="flex items-center justify-between mb-5">
                 <div className="flex items-center space-x-3">
                   <div className={`p-2.5 rounded-xl border ${getCategoryIconStyle(cat)}`}>
                     <Package className="w-5 h-5" />
                   </div>
                   <h3 className="text-lg font-extrabold text-slate-900 tracking-tight">{cat}</h3>
                 </div>
                 <div className="bg-gray-50 border border-gray-100 text-slate-600 text-xs font-bold px-2.5 py-1.5 rounded-lg">
                   {items.length} ítems
                 </div>
               </div>
               
               <div className="flex-1 overflow-hidden relative">
                 {items.length === 0 ? (
                   <div className="h-full flex flex-col items-center justify-center text-gray-400 space-y-2">
                     <span className="text-2xl opacity-50">📦</span>
                     <p className="text-sm font-medium">Categoría vacía</p>
                   </div>
                 ) : (
                   <ul className="space-y-3">
                     {items.slice(0, 4).map(item => (
                       <li key={item.id} className="flex justify-between items-center text-sm">
                         <span className="text-slate-600 font-medium truncate pr-4">{item.descripcion}</span>
                         <span className={`font-semibold tabular-nums shrink-0 ${item.stock_actual > 0 ? 'text-slate-900' : 'text-rose-500'}`}>
                           {item.stock_actual} un.
                         </span>
                       </li>
                     ))}
                   </ul>
                 )}
                 {items.length > 4 && (
                   <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-white to-transparent" />
                 )}
               </div>
               
               <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-sm font-bold text-indigo-600">
                 <span>Ver catálogo completo</span>
                 <div className="w-6 h-6 rounded-full bg-indigo-50 flex items-center justify-center group-hover:bg-indigo-100 group-hover:translate-x-1 transition-all">
                   <ChevronRight className="w-4 h-4" />
                 </div>
               </div>
             </div>
           ))}
         </div>
      )}

      {/* Modal Alta de Artículo */}
      {isModalOpen && (
        <>
          <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 transition-opacity" onClick={() => setIsModalOpen(false)} />
          <div className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 bg-white rounded-2xl shadow-2xl z-50 w-full max-w-lg border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
              <h3 className="text-lg font-bold text-slate-900">Alta de Nuevo Artículo</h3>
              <button onClick={() => setIsModalOpen(false)} className="p-1.5 rounded-lg hover:bg-gray-200 text-gray-500 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Código SKU</label>
                  <input type="text" required placeholder="BEB-001" className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm font-mono uppercase focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all" value={codigo} onChange={e => setCodigo(e.target.value)} />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Categoría</label>
                  <select required className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all" value={categoria} onChange={e => setCategoria(e.target.value)}>
                    <option value="" disabled>Seleccionar...</option>
                    <option value="Bebidas">Bebidas</option>
                    <option value="Snacks">Snacks</option>
                    <option value="Farmacia">Farmacia</option>
                    <option value="Blanquería">Blanquería</option>
                    {categoria && !CATEGORIAS_BASE.includes(categoria) && (
                      <option value={categoria}>{categoria}</option>
                    )}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Descripción del Producto</label>
                <input type="text" required placeholder="Ej: Gaseosa Cola 500ml" className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all" value={descripcion} onChange={e => setDescripcion(e.target.value)} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Precio Unitario ($)</label>
                  <input type="number" step="0.01" min="0" required placeholder="0.00" className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm font-mono focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all" value={precio} onChange={e => setPrecio(e.target.value)} />
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Stock Inicial</label>
                  <input type="number" min="0" step="1" required placeholder="0" className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm font-mono focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 outline-none transition-all" value={stock} onChange={e => setStock(e.target.value)} />
                </div>
              </div>
              <div className="pt-5 border-t border-gray-100 mt-5 flex space-x-3">
                <button type="button" onClick={() => setIsModalOpen(false)} className="flex-1 bg-white text-slate-600 font-semibold py-2.5 rounded-xl border border-gray-200 hover:bg-gray-50 transition-colors">Cancelar</button>
                <button type="submit" className="flex-1 bg-slate-900 text-white font-semibold py-2.5 rounded-xl hover:bg-slate-800 transition-colors shadow-md">Guardar Artículo</button>
              </div>
            </form>
          </div>
        </>
      )}
    </div>
  );
};

export default InventarioView;
