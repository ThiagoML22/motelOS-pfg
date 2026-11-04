import React, { useEffect, useState } from 'react';
import { History, Pencil, Plus, Power, Receipt } from 'lucide-react';
import { Categoria, HabitacionConfiguracion, Tarifa } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import { formatMinutos } from '../utils/turno';
import { CamposTarifa, Ejecutar, TarifaForm, resumenTarifa, tarifaDatosDe, tarifaFormDe, tarifaValida } from './CamposTarifa';
import { ModalFranjas, ResumenFranjas } from './FranjasConfig';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';

const campo = `${inputClass} h-11`;
const numero = (valor: string): number => Number(valor.replace(',', '.'));

export type { Ejecutar } from './CamposTarifa';
export interface Confirmacion {
  titulo: string;
  texto: string;
  accion: () => Promise<void>;
}

// Colores sugeridos para las categorías (cualquier otro se elige con el selector).
export const COLORES = ['#244473', '#0f766e', '#7c3aed', '#b45309', '#be123c', '#0369a1', '#4d7c0f', '#475569'];

// Chip con el color y el nombre de la categoría.
export const ChipCategoria: React.FC<{ categoria?: Pick<Categoria, 'nombre' | 'color'> | null; className?: string }> = ({
  categoria,
  className = '',
}) =>
  categoria ? (
    <span
      className={`chip-categoria inline-flex max-w-full items-center gap-1.5 truncate rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}
      style={{ borderColor: `${categoria.color}66`, '--chip': categoria.color, backgroundColor: `${categoria.color}14` } as React.CSSProperties}
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: categoria.color }} aria-hidden="true" />
      <span className="truncate">{categoria.nombre}</span>
    </span>
  ) : null;

// --- Sección -----------------------------------------------------------------------------------------------------

interface SeccionCategoriasProps {
  categorias: Categoria[];
  habitaciones: HabitacionConfiguracion[];
  ocupado: boolean;
  ejecutar: Ejecutar;
  confirmar: (c: Confirmacion) => void;
}

type Modo =
  | { tipo: 'nueva' }
  | { tipo: 'editar'; categoria: Categoria }
  | { tipo: 'tarifa'; categoria: Categoria }
  | { tipo: 'franjas'; categoriaId: number };

const SeccionCategorias: React.FC<SeccionCategoriasProps> = ({ categorias, habitaciones, ocupado, ejecutar, confirmar }) => {
  const [modo, setModo] = useState<Modo | null>(null);
  const [historial, setHistorial] = useState<Categoria | null>(null);
  // Se busca en la lista: al guardar, la gerencia ve la categoría recién recargada.
  const franjasDe = modo?.tipo === 'franjas' ? categorias.find((c) => c.id === modo.categoriaId) : undefined;

  const numerosDe = (c: Categoria) =>
    habitaciones
      .filter((h) => h.activa && h.categoria_id === c.id)
      .map((h) => h.numero)
      .sort((a, b) => a - b);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-ink">Categorías de habitación</h2>
          <p className="text-sm text-muted">
            Cada categoría tiene su tarifa y puede sumar tarifas especiales por día y hora. El turno toma la que rige al abrirse y la conserva.
          </p>
        </div>
        <Button className="h-11" onClick={() => setModo({ tipo: 'nueva' })}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Nueva categoría
        </Button>
      </div>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(19rem,1fr))] gap-4">
        {categorias.map((c) => {
          const numeros = numerosDe(c);
          return (
            <article
              key={c.id}
              className={`flex flex-col overflow-hidden rounded-lg border border-line bg-surface transition hover:shadow-lift ${c.activa ? '' : 'opacity-60'}`}
            >
              <div className="h-1.5" style={{ backgroundColor: c.color }} aria-hidden="true" />
              <div className="flex flex-1 flex-col p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="flex items-center gap-2 text-base font-semibold text-ink">
                      <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: c.color }} aria-hidden="true" />
                      <span className="truncate">{c.nombre}</span>
                    </h3>
                    {c.descripcion && <p className="mt-0.5 text-xs text-muted">{c.descripcion}</p>}
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${c.activa ? 'bg-libre-soft text-libre' : 'bg-surface-2 text-muted'}`}>
                    {c.activa ? `${c.habitaciones} hab.` : 'Dada de baja'}
                  </span>
                </div>

                {c.tarifa ? (
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 rounded-md bg-surface-2 p-3 text-sm">
                    <div>
                      <dt className="text-xs text-muted">Turno</dt>
                      <dd className="font-medium tabular-nums text-ink">
                        {formatMinutos(c.tarifa.estadia_base_min)} · {formatMoney(c.tarifa.tarifa_base)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Extra</dt>
                      <dd className="font-medium tabular-nums text-ink">
                        {formatMinutos(c.tarifa.fraccion_min)} · {formatMoney(c.tarifa.tarifa_fraccion)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Tolerancia</dt>
                      <dd className="tabular-nums text-ink">{c.tarifa.tolerancia_min} min</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Tope</dt>
                      <dd className="tabular-nums text-ink">{c.tarifa.tope ? formatMoney(c.tarifa.tope) : 'Sin tope'}</dd>
                    </div>
                  </dl>
                ) : (
                  <p className="mt-3 rounded-md bg-warn-soft p-3 text-sm text-warn">Sin tarifa vigente.</p>
                )}

                <ResumenFranjas categoria={c} onGestionar={() => setModo({ tipo: 'franjas', categoriaId: c.id })} />

                <p className="mt-3 min-h-[1.25rem] text-xs text-muted">
                  {numeros.length > 0 ? `Habitaciones: ${numeros.map(formatRoomNumber).join(', ')}` : 'Sin habitaciones asignadas.'}
                </p>

                <div className="mt-3 flex flex-wrap gap-2">
                  <Button className="h-11" disabled={!c.activa} onClick={() => setModo({ tipo: 'tarifa', categoria: c })}>
                    <Receipt className="h-4 w-4" aria-hidden="true" />
                    Cambiar tarifa
                  </Button>
                  <Button variant="secondary" className="h-11" aria-label={`Editar ${c.nombre}`} onClick={() => setModo({ tipo: 'editar', categoria: c })}>
                    <Pencil className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button variant="secondary" className="h-11" aria-label={`Historial de tarifas de ${c.nombre}`} onClick={() => setHistorial(c)}>
                    <History className="h-4 w-4" aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    className="h-11"
                    disabled={ocupado}
                    aria-label={c.activa ? `Dar de baja ${c.nombre}` : `Reactivar ${c.nombre}`}
                    title={c.activa && c.habitaciones > 0 ? 'Reasigne sus habitaciones antes de darla de baja' : undefined}
                    onClick={() =>
                      c.activa
                        ? confirmar({
                            titulo: `Dar de baja ${c.nombre}`,
                            texto: 'La categoría deja de ofrecerse. Sus tarifas y los turnos registrados se conservan.',
                            accion: async () => {
                              await ejecutar(
                                () => api.cambiarCategoria(c.id, { activa: false }),
                                `${c.nombre} dada de baja.`,
                                'No se pudo dar de baja la categoría.',
                              );
                            },
                          })
                        : void ejecutar(() => api.cambiarCategoria(c.id, { activa: true }), `${c.nombre} reactivada.`, 'No se pudo reactivar.')
                    }
                  >
                    <Power className="h-4 w-4" aria-hidden="true" />
                  </Button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {modo?.tipo === 'nueva' && <ModalNuevaCategoria ocupado={ocupado} ejecutar={ejecutar} onCerrar={() => setModo(null)} orden={categorias.length + 1} />}
      {modo?.tipo === 'editar' && <ModalEditarCategoria categoria={modo.categoria} ocupado={ocupado} ejecutar={ejecutar} onCerrar={() => setModo(null)} />}
      {modo?.tipo === 'tarifa' && <ModalTarifa categoria={modo.categoria} ocupado={ocupado} ejecutar={ejecutar} onCerrar={() => setModo(null)} />}
      {franjasDe && <ModalFranjas categoria={franjasDe} ocupado={ocupado} ejecutar={ejecutar} confirmar={confirmar} onCerrar={() => setModo(null)} />}
      {historial && <ModalHistorial categoria={historial} onCerrar={() => setHistorial(null)} />}
    </>
  );
};

// --- Modales -------------------------------------------------------------------------------------------------------

const SelectorColor: React.FC<{ valor: string; onChange: (c: string) => void }> = ({ valor, onChange }) => (
  <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label="Color">
    {COLORES.map((c) => (
      <button
        key={c}
        type="button"
        role="radio"
        aria-checked={valor.toLowerCase() === c}
        aria-label={`Color ${c}`}
        onClick={() => onChange(c)}
        className={`press h-8 w-8 rounded-full border-2 ${valor.toLowerCase() === c ? 'border-ink' : 'border-transparent'}`}
        style={{ backgroundColor: c }}
      />
    ))}
    <label className="press flex h-8 cursor-pointer items-center gap-1.5 rounded-full border border-line px-2 text-xs text-muted">
      <input type="color" value={valor} onChange={(e) => onChange(e.target.value)} className="h-5 w-5 cursor-pointer border-0 bg-transparent p-0" />
      Otro
    </label>
  </div>
);

const ModalNuevaCategoria: React.FC<{ ocupado: boolean; ejecutar: Ejecutar; onCerrar: () => void; orden: number }> = ({
  ocupado,
  ejecutar,
  onCerrar,
  orden,
}) => {
  const [datos, setDatos] = useState({ nombre: '', descripcion: '', color: COLORES[2] });
  const [tarifa, setTarifa] = useState<TarifaForm>(tarifaFormDe(null));
  const valida = datos.nombre.trim().length >= 2 && tarifaValida(tarifaDatosDe(tarifa));

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(
      () => api.altaCategoria({ ...datos, nombre: datos.nombre.trim(), descripcion: datos.descripcion.trim() || null, orden, tarifa: tarifaDatosDe(tarifa) }),
      `Categoría ${datos.nombre.trim()} creada. Asígnele habitaciones desde la pestaña Habitaciones.`,
      'No se pudo crear la categoría.',
    );
    if (ok) onCerrar();
  };

  return (
    <Modal title="Nueva categoría de habitación" onClose={onCerrar} size="lg">
      <form onSubmit={guardar} className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nombre" htmlFor="cat_nombre">
            <input id="cat_nombre" data-autofocus required maxLength={40} placeholder="VIP" className={campo} value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} />
          </Field>
          <Field label="Descripción" htmlFor="cat_desc">
            <input id="cat_desc" maxLength={160} placeholder="Jacuzzi y sauna" className={campo} value={datos.descripcion} onChange={(e) => setDatos({ ...datos, descripcion: e.target.value })} />
          </Field>
        </div>
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted">Color en la grilla</p>
          <SelectorColor valor={datos.color} onChange={(color) => setDatos({ ...datos, color })} />
        </div>
        <CamposTarifa form={tarifa} onChange={setTarifa} prefijo="nueva" />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" className="h-11" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button type="submit" className="h-11" disabled={ocupado || !valida}>
            Crear categoría
          </Button>
        </div>
      </form>
    </Modal>
  );
};

const ModalEditarCategoria: React.FC<{ categoria: Categoria; ocupado: boolean; ejecutar: Ejecutar; onCerrar: () => void }> = ({
  categoria,
  ocupado,
  ejecutar,
  onCerrar,
}) => {
  const [datos, setDatos] = useState({
    nombre: categoria.nombre,
    descripcion: categoria.descripcion ?? '',
    color: categoria.color,
    orden: String(categoria.orden),
  });

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(
      () =>
        api.cambiarCategoria(categoria.id, {
          nombre: datos.nombre.trim(),
          descripcion: datos.descripcion.trim() || null,
          color: datos.color,
          orden: numero(datos.orden),
        }),
      `Categoría ${datos.nombre.trim()} actualizada.`,
      'No se pudo actualizar la categoría.',
    );
    if (ok) onCerrar();
  };

  return (
    <Modal title={`Editar ${categoria.nombre}`} onClose={onCerrar}>
      <form onSubmit={guardar} className="space-y-4">
        <Field label="Nombre" htmlFor="ed_nombre">
          <input id="ed_nombre" required maxLength={40} className={campo} value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} />
        </Field>
        <Field label="Descripción" htmlFor="ed_desc">
          <input id="ed_desc" maxLength={160} className={campo} value={datos.descripcion} onChange={(e) => setDatos({ ...datos, descripcion: e.target.value })} />
        </Field>
        <Field label="Orden en las listas" htmlFor="ed_orden" hint="La de menor orden es la predeterminada para habitaciones nuevas.">
          <input id="ed_orden" inputMode="numeric" className={campo} value={datos.orden} onChange={(e) => setDatos({ ...datos, orden: e.target.value })} />
        </Field>
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted">Color</p>
          <SelectorColor valor={datos.color} onChange={(color) => setDatos({ ...datos, color })} />
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" className="h-11" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button type="submit" className="h-11" disabled={ocupado || datos.nombre.trim().length < 2}>
            Guardar
          </Button>
        </div>
      </form>
    </Modal>
  );
};

const ModalTarifa: React.FC<{ categoria: Categoria; ocupado: boolean; ejecutar: Ejecutar; onCerrar: () => void }> = ({
  categoria,
  ocupado,
  ejecutar,
  onCerrar,
}) => {
  const [form, setForm] = useState<TarifaForm>(tarifaFormDe(categoria.tarifa));
  const datos = tarifaDatosDe(form);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    const ok = await ejecutar(
      () => api.nuevaTarifa({ ...datos, categoria_id: categoria.id }),
      `Tarifa nueva de ${categoria.nombre}: rige para los turnos que se abran desde ahora.`,
      'No se pudo cambiar la tarifa.',
    );
    if (ok) onCerrar();
  };

  return (
    <Modal
      title={`Tarifa de ${categoria.nombre}`}
      subtitle={categoria.tarifa ? `Vigente: ${resumenTarifa(categoria.tarifa)}` : 'Sin tarifa vigente'}
      onClose={onCerrar}
      size="lg"
    >
      <form onSubmit={guardar} className="space-y-5">
        <CamposTarifa form={form} onChange={setForm} prefijo="tarifa" />
        <p className="text-xs text-subtle">
          La tarifa anterior no se modifica: los turnos abiertos o cerrados con ella la conservan (RN-DER-06).
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" className="h-11" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button type="submit" className="h-11" disabled={ocupado || !tarifaValida(datos)}>
            Guardar tarifa nueva
          </Button>
        </div>
      </form>
    </Modal>
  );
};

const ModalHistorial: React.FC<{ categoria: Categoria; onCerrar: () => void }> = ({ categoria, onCerrar }) => {
  const [tarifas, setTarifas] = useState<Tarifa[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getTarifasDe(categoria.id)
      .then(setTarifas)
      .catch((err) => setError(getErrorMessage(err, 'No se pudo cargar el historial.')));
  }, [categoria.id]);

  return (
    <Modal title={`Historial de tarifas · ${categoria.nombre}`} onClose={onCerrar} size="lg">
      {error && <p className="text-sm text-danger">{error}</p>}
      {!tarifas && !error && <p className="text-sm text-muted">Cargando…</p>}
      {tarifas && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="py-2 font-medium">Desde</th>
              <th className="py-2 font-medium">Rige</th>
              <th className="py-2 font-medium">Turno</th>
              <th className="py-2 font-medium">Extra</th>
              <th className="py-2 font-medium">Tope</th>
              <th className="py-2 text-right font-medium">Estado</th>
            </tr>
          </thead>
          <tbody>
            {tarifas.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="py-2">{formatDateTime(t.vigente_desde)}</td>
                <td className="py-2 text-muted">{t.franja ?? 'General'}</td>
                <td className="py-2 tabular-nums">
                  {formatMinutos(t.estadia_base_min)} · {formatMoney(t.tarifa_base)}
                </td>
                <td className="py-2 tabular-nums">
                  {formatMinutos(t.fraccion_min)} · {formatMoney(t.tarifa_fraccion)}
                </td>
                <td className="py-2 tabular-nums">{t.tope ? formatMoney(t.tope) : '—'}</td>
                <td className={`py-2 text-right ${t.vigente ? 'font-medium text-libre' : 'text-muted'}`}>{t.vigente ? 'Vigente' : 'Anterior'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
  );
};

export default SeccionCategorias;
