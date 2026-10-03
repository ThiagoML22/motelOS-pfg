import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Search } from 'lucide-react';
import { Articulo } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatMoney } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

const STOCK_BAJO = 5;
const SIN_CATEGORIA = 'General';

type FiltroStock = 'todos' | 'bajo' | 'sin';
type SortKey = 'codigo' | 'descripcion' | 'categoria' | 'precio_unitario' | 'stock_actual';
type SortDir = 'asc' | 'desc';

const categoriaDe = (a: Articulo): string => a.categoria || SIN_CATEGORIA;
const esBajo = (a: Articulo): boolean => a.stock_actual > 0 && a.stock_actual <= STOCK_BAJO;
const esSin = (a: Articulo): boolean => a.stock_actual === 0;

const valorOrden = (a: Articulo, key: SortKey): string | number => (key === 'categoria' ? categoriaDe(a) : a[key]);

const COLUMNAS: { key: SortKey; label: string; align?: 'right' }[] = [
  { key: 'codigo', label: 'Código' },
  { key: 'descripcion', label: 'Descripción' },
  { key: 'categoria', label: 'Categoría' },
  { key: 'precio_unitario', label: 'Precio', align: 'right' },
  { key: 'stock_actual', label: 'Stock', align: 'right' },
];

const FORM_VACIO = { codigo: '', descripcion: '', categoria: '', precio: '', stock: '' };

const InventarioView: React.FC = () => {
  const { toast } = useToast();
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [busqueda, setBusqueda] = useState('');
  const [categoria, setCategoria] = useState<string | null>(null);
  const [filtroStock, setFiltroStock] = useState<FiltroStock>('todos');
  const [orden, setOrden] = useState<{ key: SortKey; dir: SortDir }>({ key: 'descripcion', dir: 'asc' });
  const [modalAbierto, setModalAbierto] = useState(false);
  const [form, setForm] = useState(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setArticulos(await api.getArticulos());
      setEstado('ok');
    } catch (e) {
      setEstado('error');
      toast(getErrorMessage(e, 'No se pudo cargar el inventario.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const categorias = useMemo(() => {
    const mapa = new Map<string, { items: number; unidades: number; bajos: number; sin: number }>();
    articulos.forEach((a) => {
      const c = mapa.get(categoriaDe(a)) ?? { items: 0, unidades: 0, bajos: 0, sin: 0 };
      c.items += 1;
      c.unidades += a.stock_actual;
      if (esBajo(a)) c.bajos += 1;
      if (esSin(a)) c.sin += 1;
      mapa.set(categoriaDe(a), c);
    });
    return Array.from(mapa.entries()).sort(([a], [b]) => a.localeCompare(b, 'es'));
  }, [articulos]);

  const resumen = useMemo(
    () => ({
      total: articulos.length,
      unidades: articulos.reduce((s, a) => s + a.stock_actual, 0),
      bajos: articulos.filter(esBajo).length,
      sin: articulos.filter(esSin).length,
    }),
    [articulos],
  );

  const visibles = useMemo(() => {
    const term = busqueda.trim().toLowerCase();
    const filtrados = articulos.filter(
      (a) =>
        (!categoria || categoriaDe(a) === categoria) &&
        (filtroStock === 'todos' || (filtroStock === 'bajo' ? esBajo(a) : esSin(a))) &&
        (!term ||
          a.codigo.toLowerCase().includes(term) ||
          a.descripcion.toLowerCase().includes(term) ||
          categoriaDe(a).toLowerCase().includes(term)),
    );
    const signo = orden.dir === 'asc' ? 1 : -1;
    return filtrados.sort((a, b) => {
      const va = valorOrden(a, orden.key);
      const vb = valorOrden(b, orden.key);
      const cmp = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'es');
      return cmp * signo;
    });
  }, [articulos, busqueda, categoria, filtroStock, orden]);

  const ordenarPor = (key: SortKey) =>
    setOrden((prev) => ({ key, dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc' }));

  const abrirModal = () => {
    setForm({ ...FORM_VACIO, categoria: categoria ?? '' });
    setModalAbierto(true);
  };

  const setCampo = (campo: keyof typeof FORM_VACIO) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [campo]: e.target.value }));

  const crear = async (e: React.FormEvent) => {
    e.preventDefault();
    setGuardando(true);
    try {
      await api.createArticulo({
        codigo: form.codigo.trim().toUpperCase(),
        descripcion: form.descripcion.trim(),
        categoria: form.categoria.trim() || null,
        precio_unitario: parseFloat(form.precio),
        stock_actual: parseInt(form.stock, 10),
      });
      toast('Artículo creado.', 'success');
      setModalAbierto(false);
      await cargar();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo crear el artículo.'), 'error');
    } finally {
      setGuardando(false);
    }
  };

  const hayFiltros = categoria !== null || filtroStock !== 'todos' || busqueda.trim() !== '';
  const limpiarFiltros = () => {
    setCategoria(null);
    setFiltroStock('todos');
    setBusqueda('');
  };

  const alternarStock = (valor: FiltroStock) => setFiltroStock((prev) => (prev === valor ? 'todos' : valor));

  return (
    <div className="w-full animate-fade-in">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Inventario</h1>
          <p className="mt-0.5 text-sm text-muted">Minibar y productos de venta</p>
        </div>
        <Button onClick={abrirModal}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Nuevo artículo
        </Button>
      </div>

      {estado === 'cargando' && <p className="py-16 text-center text-sm text-muted">Cargando inventario…</p>}

      {estado === 'error' && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
          <p className="text-sm text-muted">No se pudo obtener el inventario.</p>
          <Button variant="secondary" onClick={() => void cargar()}>
            Reintentar
          </Button>
        </div>
      )}

      {estado === 'ok' && (
        <>
          {/* Resumen: las alertas funcionan como filtro rápido */}
          <div className="mb-4 grid grid-cols-2 divide-x divide-line overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-4">
            <div className="px-4 py-3">
              <p className="text-xs text-muted">Artículos</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums text-ink">{resumen.total}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-xs text-muted">Unidades en stock</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums text-ink">{resumen.unidades}</p>
            </div>
            <button
              type="button"
              aria-pressed={filtroStock === 'bajo'}
              onClick={() => alternarStock('bajo')}
              className={`press px-4 py-3 text-left transition-colors hover:bg-surface-2 ${filtroStock === 'bajo' ? 'bg-warn-soft' : ''}`}
            >
              <p className="text-xs text-muted">Stock bajo (≤ {STOCK_BAJO})</p>
              <p className={`mt-0.5 text-xl font-semibold tabular-nums ${resumen.bajos > 0 ? 'text-warn' : 'text-ink'}`}>
                {resumen.bajos}
              </p>
            </button>
            <button
              type="button"
              aria-pressed={filtroStock === 'sin'}
              onClick={() => alternarStock('sin')}
              className={`press border-t border-line px-4 py-3 text-left transition-colors hover:bg-surface-2 sm:border-t-0 ${filtroStock === 'sin' ? 'bg-danger-soft' : ''}`}
            >
              <p className="text-xs text-muted">Sin stock</p>
              <p className={`mt-0.5 text-xl font-semibold tabular-nums ${resumen.sin > 0 ? 'text-danger' : 'text-ink'}`}>
                {resumen.sin}
              </p>
            </button>
          </div>

          {/* Categorías: navegación por tarjetas que filtra la tabla */}
          {categorias.length > 0 && (
            <div
              role="group"
              aria-label="Filtrar por categoría"
              className="mb-6 grid grid-cols-[repeat(auto-fill,minmax(12rem,1fr))] gap-3"
            >
              {categorias.map(([nombre, c]) => {
                const activa = categoria === nombre;
                return (
                  <button
                    key={nombre}
                    type="button"
                    aria-pressed={activa}
                    onClick={() => setCategoria(activa ? null : nombre)}
                    className={`press rounded-lg border p-4 text-left transition duration-200 hover:-translate-y-0.5 hover:shadow-lift ${
                      activa ? 'border-accent bg-accent-soft' : 'border-line bg-surface hover:border-line-strong'
                    }`}
                  >
                    <p className={`text-sm font-semibold ${activa ? 'text-accent' : 'text-ink'}`}>{nombre}</p>
                    <p className="mt-1 text-xs text-muted">
                      <span className="tabular-nums">{c.items}</span> {c.items === 1 ? 'artículo' : 'artículos'} ·{' '}
                      <span className="tabular-nums">{c.unidades}</span> un.
                    </p>
                    <p className="mt-2 text-xs">
                      {c.sin > 0 ? (
                        <span className="font-medium text-danger">{c.sin} sin stock</span>
                      ) : c.bajos > 0 ? (
                        <span className="font-medium text-warn">{c.bajos} con stock bajo</span>
                      ) : (
                        <span className="text-subtle">Stock al día</span>
                      )}
                    </p>
                  </button>
                );
              })}
            </div>
          )}

          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted" aria-live="polite">
              <span className="font-medium text-ink">{categoria ?? 'Todos los artículos'}</span> ·{' '}
              <span className="tabular-nums">{visibles.length}</span> de{' '}
              <span className="tabular-nums">{articulos.length}</span>
              {hayFiltros && (
                <button type="button" onClick={limpiarFiltros} className="ml-3 inline-flex min-h-11 items-center text-accent underline-offset-2 hover:underline">
                  Limpiar filtros
                </button>
              )}
            </p>
            <div className="relative w-full max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-3.5 h-4 w-4 text-subtle" aria-hidden="true" />
              <label htmlFor="busqueda" className="sr-only">
                Buscar artículo
              </label>
              <input
                id="busqueda"
                type="search"
                placeholder="Buscar por código o nombre"
                className={`${inputClass} pl-9`}
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
              />
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-2 text-xs font-medium uppercase tracking-wide text-subtle">
                  {COLUMNAS.map(({ key, label, align }) => (
                    <th
                      key={key}
                      scope="col"
                      aria-sort={orden.key === key ? (orden.dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      className={`px-4 py-2.5 ${align === 'right' ? 'text-right' : ''}`}
                    >
                      <button
                        type="button"
                        onClick={() => ordenarPor(key)}
                        className={`inline-flex min-h-11 items-center gap-1 uppercase tracking-wide transition-colors hover:text-ink ${
                          orden.key === key ? 'text-ink' : ''
                        }`}
                      >
                        {label}
                        {orden.key === key &&
                          (orden.dir === 'asc' ? (
                            <ArrowUp className="h-3 w-3" aria-hidden="true" />
                          ) : (
                            <ArrowDown className="h-3 w-3" aria-hidden="true" />
                          ))}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {visibles.map((a) => (
                  <tr key={a.id} className="transition-colors hover:bg-surface-2">
                    <td className="px-4 py-2.5 font-mono text-xs text-muted">{a.codigo}</td>
                    <td className="px-4 py-2.5 font-medium text-ink">{a.descripcion}</td>
                    <td className="px-4 py-2.5 text-muted">{categoriaDe(a)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-ink">{formatMoney(a.precio_unitario)}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">
                      <span className={esSin(a) ? 'font-medium text-danger' : esBajo(a) ? 'font-medium text-warn' : 'text-ink'}>
                        {a.stock_actual}
                      </span>
                      {esSin(a) && <span className="ml-2 text-xs text-danger">Sin stock</span>}
                      {esBajo(a) && <span className="ml-2 text-xs text-warn">Stock bajo</span>}
                    </td>
                  </tr>
                ))}
                {visibles.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-12 text-center text-muted">
                      {articulos.length === 0
                        ? 'Todavía no hay artículos cargados.'
                        : 'Ningún artículo coincide con los filtros aplicados.'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      {modalAbierto && (
        <Modal
          title="Nuevo artículo"
          onClose={() => setModalAbierto(false)}
          footer={
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setModalAbierto(false)} disabled={guardando}>
                Cancelar
              </Button>
              <Button type="submit" form="form-articulo" disabled={guardando}>
                Guardar artículo
              </Button>
            </div>
          }
        >
          <form id="form-articulo" onSubmit={crear} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Código" htmlFor="codigo">
                <input id="codigo" data-autofocus required placeholder="BEB-001" className={`${inputClass} font-mono uppercase`} value={form.codigo} onChange={setCampo('codigo')} />
              </Field>
              <Field label="Categoría" htmlFor="categoria">
                <input id="categoria" list="categorias-existentes" placeholder="Bebidas" className={inputClass} value={form.categoria} onChange={setCampo('categoria')} />
                <datalist id="categorias-existentes">
                  {categorias.map(([nombre]) => (
                    <option key={nombre} value={nombre} />
                  ))}
                </datalist>
              </Field>
            </div>
            <Field label="Descripción" htmlFor="descripcion">
              <input id="descripcion" required placeholder="Gaseosa cola 500 ml" className={inputClass} value={form.descripcion} onChange={setCampo('descripcion')} />
            </Field>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Precio unitario ($)" htmlFor="precio">
                <input id="precio" type="number" inputMode="decimal" step="0.01" min="0" required placeholder="0" className={`${inputClass} tabular-nums`} value={form.precio} onChange={setCampo('precio')} />
              </Field>
              <Field label="Stock inicial" htmlFor="stock">
                <input id="stock" type="number" inputMode="numeric" step="1" min="0" required placeholder="0" className={`${inputClass} tabular-nums`} value={form.stock} onChange={setCampo('stock')} />
              </Field>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
};

export default InventarioView;
