import React, { useEffect, useState } from 'react';
import { History, Pencil, Plus, Power, Receipt } from 'lucide-react';
import { Categoria, HabitacionConfiguracion, Tarifa, TarifaDatos } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import { formatMinutos, simularEstadia } from '../utils/turno';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';

const campo = `${inputClass} h-11`;
const numero = (valor: string): number => Number(valor.replace(',', '.'));

export type Ejecutar = (accion: () => Promise<unknown>, exito: string, error: string) => Promise<boolean>;
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
      className={`inline-flex max-w-full items-center gap-1.5 truncate rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}
      style={{ borderColor: `${categoria.color}66`, color: categoria.color, backgroundColor: `${categoria.color}14` }}
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: categoria.color }} aria-hidden="true" />
      <span className="truncate">{categoria.nombre}</span>
    </span>
  ) : null;

// Una línea legible de la tarifa: "2 h por $ 8.000 · cada 30 min, $ 2.500".
export const resumenTarifa = (t: TarifaDatos): string =>
  `${formatMinutos(t.estadia_base_min)} por ${formatMoney(t.tarifa_base)} · cada ${formatMinutos(t.fraccion_min)}, ${formatMoney(t.tarifa_fraccion)}`;

// --- Formulario de tarifa con simulador ----------------------------------------------------------------------------

export interface TarifaForm {
  tarifa_base: string;
  estadia_base_min: string;
  fraccion_min: string;
  tarifa_fraccion: string;
  tolerancia_min: string;
  tope: string;
}

export const tarifaFormDe = (t?: TarifaDatos | null): TarifaForm => ({
  tarifa_base: String(t?.tarifa_base ?? ''),
  estadia_base_min: String(t?.estadia_base_min ?? 120),
  fraccion_min: String(t?.fraccion_min ?? 30),
  tarifa_fraccion: String(t?.tarifa_fraccion ?? ''),
  tolerancia_min: String(t?.tolerancia_min ?? 0),
  tope: t?.tope ? String(t.tope) : '',
});

export const tarifaDatosDe = (f: TarifaForm): TarifaDatos => ({
  tarifa_base: numero(f.tarifa_base),
  estadia_base_min: numero(f.estadia_base_min),
  fraccion_min: numero(f.fraccion_min),
  tarifa_fraccion: numero(f.tarifa_fraccion),
  tolerancia_min: numero(f.tolerancia_min || '0'),
  tope: f.tope.trim() ? numero(f.tope) : null,
});

const tarifaValida = (t: TarifaDatos): boolean =>
  t.tarifa_base > 0 &&
  t.estadia_base_min > 0 &&
  t.fraccion_min > 0 &&
  t.tarifa_fraccion >= 0 &&
  t.tolerancia_min >= 0 &&
  (t.tope == null || t.tope >= t.tarifa_base);

const Atajos: React.FC<{ valores: number[]; actual: string; onElegir: (v: string) => void; etiqueta: (v: number) => string }> = ({
  valores,
  actual,
  onElegir,
  etiqueta,
}) => (
  <div className="mt-1.5 flex flex-wrap gap-1">
    {valores.map((v) => (
      <button
        key={v}
        type="button"
        onClick={() => onElegir(String(v))}
        className={`press rounded-full border px-2 py-0.5 text-xs ${
          actual === String(v) ? 'border-accent bg-accent-soft text-accent' : 'border-line text-muted hover:text-ink'
        }`}
      >
        {etiqueta(v)}
      </button>
    ))}
  </div>
);

export const CamposTarifa: React.FC<{ form: TarifaForm; onChange: (f: TarifaForm) => void; prefijo: string }> = ({
  form,
  onChange,
  prefijo,
}) => {
  const set = (k: keyof TarifaForm) => (e: React.ChangeEvent<HTMLInputElement>) => onChange({ ...form, [k]: e.target.value });
  const datos = tarifaDatosDe(form);
  const valida = tarifaValida(datos);
  const base = datos.estadia_base_min || 120;
  // Duraciones de ejemplo alrededor de la estadía base, hasta medio día.
  const muestras = Array.from(
    new Set([60, base, base + (datos.fraccion_min || 30), base + 60, base + 120, 360, 720].filter((m) => m > 0)),
  ).sort((a, b) => a - b);
  const montos = muestras.map((m) => (valida ? simularEstadia(datos, m) : 0));
  const maximo = Math.max(...montos, 1);

  return (
    <div className="grid gap-5 md:grid-cols-[1fr_17rem]">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Field label="Duración del turno (min)" htmlFor={`${prefijo}_base_min`}>
              <input id={`${prefijo}_base_min`} inputMode="numeric" required className={campo} value={form.estadia_base_min} onChange={set('estadia_base_min')} />
            </Field>
            <Atajos valores={[60, 90, 120, 180, 240]} actual={form.estadia_base_min} etiqueta={formatMinutos} onElegir={(v) => onChange({ ...form, estadia_base_min: v })} />
          </div>
          <Field label="Precio del turno ($)" htmlFor={`${prefijo}_base`}>
            <input id={`${prefijo}_base`} inputMode="decimal" required className={campo} value={form.tarifa_base} onChange={set('tarifa_base')} />
          </Field>
          <div>
            <Field label="Se cobra extra cada (min)" htmlFor={`${prefijo}_fraccion_min`}>
              <input id={`${prefijo}_fraccion_min`} inputMode="numeric" required className={campo} value={form.fraccion_min} onChange={set('fraccion_min')} />
            </Field>
            <Atajos valores={[15, 30, 60]} actual={form.fraccion_min} etiqueta={formatMinutos} onElegir={(v) => onChange({ ...form, fraccion_min: v })} />
          </div>
          <Field label="Monto de cada extra ($)" htmlFor={`${prefijo}_fraccion`}>
            <input id={`${prefijo}_fraccion`} inputMode="decimal" required className={campo} value={form.tarifa_fraccion} onChange={set('tarifa_fraccion')} />
          </Field>
          <Field label="Tolerancia (min)" htmlFor={`${prefijo}_tolerancia`} hint="Gracia antes del primer extra. El catálogo fija 0.">
            <input id={`${prefijo}_tolerancia`} inputMode="numeric" className={campo} value={form.tolerancia_min} onChange={set('tolerancia_min')} />
          </Field>
          <Field label="Tope de la estadía ($)" htmlFor={`${prefijo}_tope`} hint="Opcional: precio máximo (por ejemplo, pernocte).">
            <input id={`${prefijo}_tope`} inputMode="decimal" placeholder="Sin tope" className={campo} value={form.tope} onChange={set('tope')} />
          </Field>
        </div>
        {!valida && (form.tarifa_base || form.tarifa_fraccion) && (
          <p className="text-xs text-danger">Revise los valores: precios mayores que cero y el tope no menor que el precio del turno.</p>
        )}
      </div>

      <div className="rounded-md border border-line bg-surface-2 p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">Simulador: el cliente paga</p>
        <ul className="space-y-1.5" aria-live="polite">
          {muestras.map((m, i) => (
            <li key={m} className="text-xs">
              <div className="flex justify-between gap-2">
                <span className="text-muted">{formatMinutos(m)}</span>
                <span className="font-medium tabular-nums text-ink">{valida ? formatMoney(montos[i]) : '—'}</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full bg-line">
                <div
                  className={`h-1.5 rounded-full transition-all duration-300 ${m <= base ? 'bg-libre' : 'bg-accent'}`}
                  style={{ width: `${(montos[i] / maximo) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] leading-snug text-subtle">Misma cuenta que hace el servidor al cobrar (sin consumos).</p>
      </div>
    </div>
  );
};

// --- Sección -----------------------------------------------------------------------------------------------------

interface SeccionCategoriasProps {
  categorias: Categoria[];
  habitaciones: HabitacionConfiguracion[];
  ocupado: boolean;
  ejecutar: Ejecutar;
  confirmar: (c: Confirmacion) => void;
}

type Modo = { tipo: 'nueva' } | { tipo: 'editar'; categoria: Categoria } | { tipo: 'tarifa'; categoria: Categoria };

const SeccionCategorias: React.FC<SeccionCategoriasProps> = ({ categorias, habitaciones, ocupado, ejecutar, confirmar }) => {
  const [modo, setModo] = useState<Modo | null>(null);
  const [historial, setHistorial] = useState<Categoria | null>(null);

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
            Cada categoría tiene su tarifa. El turno toma la de su habitación al abrirse y la conserva aunque después cambie.
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
