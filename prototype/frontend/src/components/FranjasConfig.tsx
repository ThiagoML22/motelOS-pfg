import React, { useState } from 'react';
import { ArrowLeft, CalendarClock, Pencil, Plus, Trash2 } from 'lucide-react';
import { Categoria, Franja } from '../types';
import { api } from '../services/api';
import { formatMoney } from '../utils/format';
import { formatMinutos } from '../utils/turno';
import {
  COLORES_FRANJA,
  DIAS_CORTOS,
  Regla,
  TODOS_LOS_DIAS,
  horaCorta,
  momentoTexto,
  primerCruce,
  reglaTexto,
} from '../utils/franjas';
import { CamposTarifa, Ejecutar, TarifaForm, resumenTarifa, tarifaDatosDe, tarifaFormDe, tarifaValida } from './CamposTarifa';
import MapaSemana, { BloqueFranja } from './MapaSemana';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';

const campo = `${inputClass} h-11`;

export const bloquesDe = (franjas: Franja[] = []): BloqueFranja[] =>
  franjas.map((f, i) => ({ ...f, color: COLORES_FRANJA[i % COLORES_FRANJA.length] }));

const diferencia = (precio: number, general?: number): string | null => {
  if (!general || precio === general) return null;
  const pct = Math.round((precio / general - 1) * 100);
  return `${pct > 0 ? '+' : '−'}${Math.abs(pct)}%`;
};

// Lo que muestra la tarjeta de la categoría: la semana de un vistazo y las especiales que tiene.
export const ResumenFranjas: React.FC<{ categoria: Categoria; onGestionar: () => void }> = ({ categoria, onGestionar }) => {
  const bloques = bloquesDe(categoria.franjas);
  const ahora = categoria.tarifa_ahora;
  return (
    <div className="mt-3 rounded-md border border-line p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted">Semana</span>
        <button type="button" disabled={!categoria.activa} onClick={onGestionar} className="press text-xs font-medium text-accent hover:underline disabled:opacity-50">
          {bloques.length ? 'Tarifas especiales' : 'Agregar tarifa especial'}
        </button>
      </div>
      <MapaSemana franjas={bloques} compacto />
      {bloques.length > 0 && (
        <ul className="mt-2 space-y-1">
          {bloques.map((f, i) => (
            <li key={f.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="flex min-w-0 items-center gap-1.5 text-muted" title={reglaTexto(f)}>
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: f.color }} aria-hidden="true" />
                <span className="truncate">{f.nombre}</span>
              </span>
              <span className="shrink-0 font-medium tabular-nums text-ink">{formatMoney(categoria.franjas?.[i].tarifa?.tarifa_base ?? 0)}</span>
            </li>
          ))}
        </ul>
      )}
      {ahora?.franja && (
        <p className="mt-2 text-xs font-medium text-accent">
          Ahora rige {ahora.franja}
        </p>
      )}
    </div>
  );
};

// --- Formulario ------------------------------------------------------------------------------------------------------

const ATAJOS: { nombre: string; regla: Regla; factor: number }[] = [
  { nombre: 'Noche de fin de semana', regla: { dias: 16 | 32, desde: '20:00', hasta: '06:00' }, factor: 1.2 },
  { nombre: 'Todas las noches', regla: { dias: TODOS_LOS_DIAS, desde: '20:00', hasta: '06:00' }, factor: 1.15 },
  { nombre: 'De día en la semana', regla: { dias: 1 | 2 | 4 | 8, desde: '08:00', hasta: '18:00' }, factor: 0.85 },
  { nombre: 'Domingo', regla: { dias: 64, desde: '00:00', hasta: '00:00' }, factor: 1 },
];

interface FranjaForm extends Regla {
  nombre: string;
  tarifa: TarifaForm;
}

const redondear = (valor: number) => Math.round(valor / 100) * 100;

const FormularioFranja: React.FC<{
  categoria: Categoria;
  franja: Franja | null;
  form: FranjaForm;
  onChange: (f: FranjaForm) => void;
  conflicto: string | null;
  ocupado: boolean;
  onGuardar: () => void;
  onVolver: () => void;
}> = ({ categoria, franja, form, onChange, conflicto, ocupado, onGuardar, onVolver }) => {
  const todoElDia = horaCorta(form.desde) === horaCorta(form.hasta);
  const elegirAtajo = (a: (typeof ATAJOS)[number]) => {
    const general = categoria.tarifa;
    onChange({
      ...form,
      ...a.regla,
      nombre: form.nombre.trim() ? form.nombre : a.nombre,
      tarifa:
        general && !franja
          ? { ...form.tarifa, tarifa_base: String(redondear(general.tarifa_base * a.factor)), tarifa_fraccion: String(redondear(general.tarifa_fraccion * a.factor)) }
          : form.tarifa,
    });
  };
  const valida = form.nombre.trim().length >= 2 && form.dias > 0 && tarifaValida(tarifaDatosDe(form.tarifa)) && !conflicto;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (valida) onGuardar();
      }}
      className="space-y-4"
    >
      {!franja && (
        <div className="flex flex-wrap gap-1.5">
          {ATAJOS.map((a) => (
            <button key={a.nombre} type="button" onClick={() => elegirAtajo(a)} className="press rounded-full border border-line px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-accent">
              {a.nombre}
            </button>
          ))}
        </div>
      )}

      <Field label="Nombre" htmlFor="franja_nombre">
        <input id="franja_nombre" required maxLength={40} placeholder="Noche de fin de semana" className={campo} value={form.nombre} onChange={(e) => onChange({ ...form, nombre: e.target.value })} />
      </Field>

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted">Días en los que empieza</p>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Días en los que empieza">
          {DIAS_CORTOS.map((d, i) => {
            const activo = Boolean(form.dias & (1 << i));
            return (
              <button
                key={d}
                type="button"
                aria-pressed={activo}
                onClick={() => onChange({ ...form, dias: form.dias ^ (1 << i) })}
                className={`press h-11 w-12 rounded-md border text-sm ${activo ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong text-muted hover:text-ink'}`}
              >
                {d}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-32">
          <Field label="Desde" htmlFor="franja_desde">
            <input id="franja_desde" type="time" required className={campo} value={horaCorta(form.desde)} onChange={(e) => onChange({ ...form, desde: e.target.value })} />
          </Field>
        </div>
        <div className="w-32">
          <Field label="Hasta" htmlFor="franja_hasta">
            <input id="franja_hasta" type="time" required className={campo} value={horaCorta(form.hasta)} onChange={(e) => onChange({ ...form, hasta: e.target.value })} />
          </Field>
        </div>
        <button
          type="button"
          aria-pressed={todoElDia}
          onClick={() => onChange({ ...form, desde: '00:00', hasta: '00:00' })}
          className={`press h-11 rounded-md border px-3 text-sm ${todoElDia ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong text-muted hover:text-ink'}`}
        >
          Todo el día
        </button>
      </div>

      <p className={`text-sm ${conflicto ? 'font-medium text-danger' : 'text-muted'}`} role={conflicto ? 'alert' : undefined}>
        {conflicto ?? (form.dias ? `Rige ${reglaTexto(form)}.` : 'Elegí al menos un día.')}
        {!conflicto && form.dias > 0 && !todoElDia && horaCorta(form.hasta) < horaCorta(form.desde) && ' Sigue después de la medianoche, hasta la mañana del día siguiente.'}
      </p>

      <CamposTarifa form={form.tarifa} onChange={(tarifa) => onChange({ ...form, tarifa })} prefijo="franja" />

      <div className="flex justify-end gap-2">
        <Button variant="secondary" className="h-11" onClick={onVolver}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Volver
        </Button>
        <Button type="submit" className="h-11" disabled={ocupado || !valida}>
          {franja ? 'Guardar cambios' : 'Crear tarifa especial'}
        </Button>
      </div>
    </form>
  );
};

// --- Modal ---------------------------------------------------------------------------------------------------------

export const ModalFranjas: React.FC<{ categoria: Categoria; ocupado: boolean; ejecutar: Ejecutar; onCerrar: () => void }> = ({
  categoria,
  ocupado,
  ejecutar,
  onCerrar,
}) => {
  const franjas = categoria.franjas ?? [];
  const bloques = bloquesDe(franjas);
  const [edicion, setEdicion] = useState<{ franja: Franja | null; form: FranjaForm } | null>(null);

  const nueva = (regla?: Regla) =>
    setEdicion({
      franja: null,
      form: { nombre: '', dias: 16 | 32, desde: '20:00', hasta: '06:00', ...regla, tarifa: tarifaFormDe(categoria.tarifa) },
    });
  const editar = (franja: Franja) =>
    setEdicion({ franja, form: { nombre: franja.nombre, dias: franja.dias, desde: horaCorta(franja.desde), hasta: horaCorta(franja.hasta), tarifa: tarifaFormDe(franja.tarifa) } });

  const conflicto = (() => {
    if (!edicion || !edicion.form.dias) return null;
    for (const f of franjas) {
      if (f.id === edicion.franja?.id) continue;
      const cruce = primerCruce(edicion.form, f);
      if (cruce !== null) return `Se superpone con «${f.nombre}» el ${momentoTexto(cruce)}.`;
    }
    return null;
  })();

  const guardar = async () => {
    if (!edicion) return;
    const { franja, form } = edicion;
    const datos = { nombre: form.nombre.trim(), dias: form.dias, desde: horaCorta(form.desde), hasta: horaCorta(form.hasta), tarifa: tarifaDatosDe(form.tarifa) };
    const ok = await ejecutar(
      () => (franja ? api.cambiarFranja(franja.id, datos) : api.altaFranja({ ...datos, categoria_id: categoria.id })),
      franja ? `Tarifa especial ${datos.nombre} actualizada: rige para los turnos que se abran desde ahora.` : `Tarifa especial ${datos.nombre} creada.`,
      'No se pudo guardar la tarifa especial.',
    );
    if (ok) setEdicion(null);
  };

  const dejarDeUsar = async (f: Franja) => {
    await ejecutar(() => api.bajaFranja(f.id), `${f.nombre} se dejó de usar. Lo cobrado con ella no cambia.`, 'No se pudo dar de baja la tarifa especial.');
  };

  return (
    <Modal
      title={`Tarifas especiales · ${categoria.nombre}`}
      subtitle={categoria.tarifa ? `Fuera de ellas rige la general: ${resumenTarifa(categoria.tarifa)}` : undefined}
      onClose={onCerrar}
      size="lg"
    >
      <div className="space-y-4">
        <MapaSemana
          franjas={edicion?.franja ? bloques.filter((b) => b.id !== edicion.franja?.id) : bloques}
          fantasma={edicion ? { ...edicion.form, error: Boolean(conflicto) } : null}
          onPintar={(regla) => (edicion ? setEdicion({ ...edicion, form: { ...edicion.form, ...regla } }) : nueva(regla))}
        />
        <p className="text-xs text-subtle">
          Arrastrá sobre el mapa para elegir días y horas. El turno toma la tarifa de la hora en que entra y la conserva hasta el cobro.
        </p>

        {edicion ? (
          <FormularioFranja
            categoria={categoria}
            franja={edicion.franja}
            form={edicion.form}
            onChange={(form) => setEdicion({ ...edicion, form })}
            conflicto={conflicto}
            ocupado={ocupado}
            onGuardar={() => void guardar()}
            onVolver={() => setEdicion(null)}
          />
        ) : (
          <>
            {franjas.length === 0 ? (
              <div className="rounded-md bg-surface-2 p-4 text-center text-sm text-muted">
                <CalendarClock className="mx-auto mb-2 h-6 w-6 text-subtle" aria-hidden="true" />
                Sin tarifas especiales: la general rige toda la semana.
              </div>
            ) : (
              <ul className="divide-y divide-line">
                {franjas.map((f, i) => {
                  const variacion = f.tarifa ? diferencia(f.tarifa.tarifa_base, categoria.tarifa?.tarifa_base) : null;
                  return (
                    <li key={f.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 text-sm font-medium text-ink">
                          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: bloques[i].color }} aria-hidden="true" />
                          {f.nombre}
                        </p>
                        <p className="text-xs text-muted">
                          {f.regla}
                          {f.tarifa && ` · ${formatMinutos(f.tarifa.estadia_base_min)} por ${formatMoney(f.tarifa.tarifa_base)}`}
                          {variacion && <span className="ml-1 font-medium text-accent">{variacion}</span>}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        <Button variant="secondary" className="h-10" aria-label={`Editar ${f.nombre}`} onClick={() => editar(f)}>
                          <Pencil className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <Button variant="ghost" className="h-10" disabled={ocupado} aria-label={`Dejar de usar ${f.nombre}`} onClick={() => void dejarDeUsar(f)}>
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="flex justify-end">
              <Button className="h-11" onClick={() => nueva()}>
                <Plus className="h-4 w-4" aria-hidden="true" />
                Nueva tarifa especial
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};
