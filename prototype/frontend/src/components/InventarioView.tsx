import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { Articulo } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatMoney } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

const STOCK_BAJO = 5;
const SIN_CATEGORIA = 'General';

const categoriaDe = (a: Articulo): string => a.categoria || SIN_CATEGORIA;

const FORM_VACIO = { codigo: '', descripcion: '', categoria: '', precio: '', stock: '' };

const InventarioView: React.FC = () => {
  const { toast } = useToast();
  const [articulos, setArticulos] = useState<Articulo[]>([]);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [busqueda, setBusqueda] = useState('');
  const [categoria, setCategoria] = useState<string | null>(null);
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
    const conteo = new Map<string, number>();
    articulos.forEach((a) => conteo.set(categoriaDe(a), (conteo.get(categoriaDe(a)) ?? 0) + 1));
    return Array.from(conteo.entries()).sort(([a], [b]) => a.localeCompare(b, 'es'));
  }, [articulos]);

  const visibles = useMemo(() => {
    const term = busqueda.trim().toLowerCase();
    return articulos.filter(
      (a) =>
        (!categoria || categoriaDe(a) === categoria) &&
        (!term ||
          a.codigo.toLowerCase().includes(term) ||
          a.descripcion.toLowerCase().includes(term) ||
          categoriaDe(a).toLowerCase().includes(term)),
    );
  }, [articulos, busqueda, categoria]);

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

  const chip = (activo: boolean) =>
    `rounded-md border px-3 py-1.5 text-sm transition-colors ${
      activo
        ? 'border-accent bg-accent-soft font-medium text-accent'
        : 'border-line-strong bg-surface text-muted hover:text-ink'
    }`;

  return (
    <div className="w-full">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Inventario</h1>
          <p className="mt-0.5 text-sm text-muted">{articulos.length} artículos</p>
        </div>
        <Button onClick={abrirModal}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Nuevo artículo
        </Button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-subtle" aria-hidden="true" />
          <label htmlFor="busqueda" className="sr-only">
            Buscar artículo
          </label>
          <input
            id="busqueda"
            type="search"
            placeholder="Buscar por código, nombre o categoría"
            className={`${inputClass} pl-9`}
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </div>

        {categorias.length > 0 && (
          <div role="group" aria-label="Filtrar por categoría" className="flex flex-wrap gap-1.5">
            <button type="button" aria-pressed={categoria === null} onClick={() => setCategoria(null)} className={chip(categoria === null)}>
              Todas
            </button>
            {categorias.map(([nombre, cantidad]) => (
              <button
                key={nombre}
                type="button"
                aria-pressed={categoria === nombre}
                onClick={() => setCategoria(nombre)}
                className={chip(categoria === nombre)}
              >
                {nombre} <span className="tabular-nums">{cantidad}</span>
              </button>
            ))}
          </div>
        )}
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
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead>
              <tr className="border-b border-line bg-surface-2 text-xs font-medium uppercase tracking-wide text-subtle">
                <th scope="col" className="px-4 py-2.5">Código</th>
                <th scope="col" className="px-4 py-2.5">Descripción</th>
                <th scope="col" className="px-4 py-2.5">Categoría</th>
                <th scope="col" className="px-4 py-2.5 text-right">Precio</th>
                <th scope="col" className="px-4 py-2.5 text-right">Stock</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {visibles.map((a) => (
                <tr key={a.id} className="hover:bg-surface-2">
                  <td className="px-4 py-2.5 font-mono text-xs text-muted">{a.codigo}</td>
                  <td className="px-4 py-2.5 font-medium text-ink">{a.descripcion}</td>
                  <td className="px-4 py-2.5 text-muted">{categoriaDe(a)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-ink">{formatMoney(a.precio_unitario)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    <span
                      className={
                        a.stock_actual === 0 ? 'font-medium text-danger' : a.stock_actual <= STOCK_BAJO ? 'font-medium text-warn' : 'text-ink'
                      }
                    >
                      {a.stock_actual}
                    </span>
                    {a.stock_actual === 0 && <span className="ml-2 text-xs text-danger">Sin stock</span>}
                    {a.stock_actual > 0 && a.stock_actual <= STOCK_BAJO && <span className="ml-2 text-xs text-warn">Stock bajo</span>}
                  </td>
                </tr>
              ))}
              {visibles.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted">
                    {articulos.length === 0 ? 'Todavía no hay artículos cargados.' : 'Ningún artículo coincide con la búsqueda.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
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
