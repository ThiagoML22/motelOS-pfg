import React, { useCallback, useEffect, useState } from 'react';
import { Building2, LogOut, Pause, Play, Plus, RefreshCw } from 'lucide-react';
import { EstablecimientoAlta, EstablecimientoResumen, Sesion } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

const campo = `${inputClass} h-11`;

const ALTA_VACIA = {
  codigo: '',
  nombre: '',
  domicilio: '',
  telefono: '',
  habitaciones: '10',
  tarifa_base: '8000',
  estadia_base_min: '120',
  fraccion_min: '30',
  tarifa_fraccion: '2500',
  fondo_cambio: '25000',
  gerente_usuario: 'gerencia',
  gerente_nombre: '',
  gerente_clave: '',
};

interface PlataformaViewProps {
  sesion: Sesion;
  onSalir: () => void;
}

// Multiinquilino: la plataforma da de alta establecimientos con su gerencia inicial, los suspende y ve un resumen
// de cada uno (cantidades, nunca turnos, cobros ni patentes). No opera ningún motel.
const PlataformaView: React.FC<PlataformaViewProps> = ({ sesion, onSalir }) => {
  const { toast } = useToast();
  const [lista, setLista] = useState<EstablecimientoResumen[]>([]);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [alta, setAlta] = useState<typeof ALTA_VACIA | null>(null);
  const [suspender, setSuspender] = useState<EstablecimientoResumen | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setLista(await api.getEstablecimientos());
      setEstado('ok');
    } catch (err) {
      setEstado('error');
      toast(getErrorMessage(err, 'No se pudo cargar la lista de establecimientos.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
    const intervalo = setInterval(() => void cargar(), 30000);
    return () => clearInterval(intervalo);
  }, [cargar]);

  const set = (clave: keyof typeof ALTA_VACIA) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setAlta((prev) => (prev ? { ...prev, [clave]: e.target.value } : prev));

  const crear = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!alta) return;
    setOcupado(true);
    const n = (v: string) => Number(v.replace(',', '.'));
    const datos: EstablecimientoAlta = {
      ...alta,
      codigo: alta.codigo.trim().toLowerCase(),
      domicilio: alta.domicilio.trim() || undefined,
      telefono: alta.telefono.trim() || undefined,
      habitaciones: n(alta.habitaciones),
      tarifa_base: n(alta.tarifa_base),
      estadia_base_min: n(alta.estadia_base_min),
      fraccion_min: n(alta.fraccion_min),
      tarifa_fraccion: n(alta.tarifa_fraccion),
      fondo_cambio: n(alta.fondo_cambio),
      gerente_usuario: alta.gerente_usuario.trim().toLowerCase(),
    };
    try {
      const nuevo = await api.altaEstablecimiento(datos);
      toast(
        `${nuevo.nombre} quedó listo. Su gerencia ingresa con el código «${nuevo.codigo}» y el usuario ${datos.gerente_usuario}.`,
        'success',
      );
      setAlta(null);
      await cargar();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo dar de alta el establecimiento.'), 'error');
    } finally {
      setOcupado(false);
    }
  };

  const cambiarEstado = async (est: EstablecimientoResumen, activo: boolean) => {
    setOcupado(true);
    try {
      await api.setEstablecimientoActivo(est.id, activo);
      toast(activo ? `${est.nombre} reactivado.` : `${est.nombre} suspendido: sus sesiones se cortaron.`, 'success');
      setSuspender(null);
      await cargar();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo cambiar el estado.'), 'error');
    } finally {
      setOcupado(false);
    }
  };

  const activos = lista.filter((e) => e.activo);
  const totales = {
    habitaciones: activos.reduce((s, e) => s + e.habitaciones, 0),
    ocupadas: activos.reduce((s, e) => s + e.ocupadas, 0),
    cobrado: activos.reduce((s, e) => s + e.cobrado_ultimas_24h, 0),
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4 sm:px-6">
          <img src="/logo.png" alt="MotelOS" className="h-7 object-contain" />
          <span className="rounded-md bg-accent-soft px-2 py-1 text-xs font-semibold uppercase tracking-wide text-accent">
            Plataforma
          </span>
          <span className="ml-auto hidden text-sm font-medium text-ink sm:inline">{sesion.operador.nombre_visible}</span>
          <button
            type="button"
            onClick={onSalir}
            aria-label="Cerrar sesión"
            title="Cerrar sesión"
            className="press hit rounded-md p-2 text-muted hover:bg-surface-2 hover:text-ink"
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-ink">Establecimientos</h1>
            <p className="mt-0.5 text-sm text-muted">
              Cada motel ve solo sus datos. La plataforma ve cantidades, no la operación de ninguno.
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" className="h-11" onClick={() => void cargar()} aria-label="Actualizar">
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button className="h-11" onClick={() => setAlta({ ...ALTA_VACIA })}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              Nuevo establecimiento
            </Button>
          </div>
        </div>

        {estado === 'cargando' && <p className="py-16 text-center text-sm text-muted">Cargando establecimientos…</p>}
        {estado === 'error' && (
          <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
            <p className="text-sm text-muted">No se pudo obtener la lista.</p>
            <Button variant="secondary" onClick={() => void cargar()}>
              Reintentar
            </Button>
          </div>
        )}

        {estado === 'ok' && (
          <>
            <div className="mb-5 grid grid-cols-2 divide-x divide-line overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-4">
              <Dato titulo="Establecimientos activos" valor={`${activos.length} de ${lista.length}`} />
              <Dato titulo="Habitaciones" valor={String(totales.habitaciones)} />
              <Dato titulo="Ocupadas ahora" valor={String(totales.ocupadas)} />
              <Dato titulo="Cobrado en 24 h" valor={formatMoney(totales.cobrado)} />
            </div>

            <div className="grid grid-cols-[repeat(auto-fill,minmax(20rem,1fr))] gap-4">
              {lista.map((e) => (
                <article
                  key={e.id}
                  className={`rounded-lg border bg-surface p-5 ${e.activo ? 'border-line' : 'border-danger/40 opacity-75'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="flex items-center gap-2 truncate text-base font-semibold text-ink">
                        <Building2 className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                        {e.nombre}
                      </h2>
                      <p className="mt-0.5 text-xs text-muted">
                        Código <span className="font-mono text-ink">{e.codigo}</span> · desde {formatDateTime(e.creado_en)}
                      </p>
                      {e.domicilio && <p className="mt-0.5 truncate text-xs text-subtle">{e.domicilio}</p>}
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                        e.activo ? 'bg-libre/15 text-libre' : 'bg-danger-soft text-danger'
                      }`}
                    >
                      {e.activo ? 'Activo' : 'Suspendido'}
                    </span>
                  </div>

                  <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
                    <Cifra titulo="Habitaciones" valor={`${e.ocupadas}/${e.habitaciones}`} pie="ocupadas" />
                    <Cifra titulo="Usuarios" valor={String(e.usuarios)} pie="activos" />
                    <Cifra titulo="Turnos 24 h" valor={String(e.turnos_ultimas_24h)} pie={formatMoney(e.cobrado_ultimas_24h)} />
                  </dl>
                  <p className="mt-3 text-xs text-muted">
                    {e.guardia_abierta ? 'Ventanilla atendida (guardia abierta)' : 'Sin guardia abierta'}
                  </p>

                  <div className="mt-4 flex justify-end">
                    {e.activo ? (
                      <Button variant="secondary" className="h-11" disabled={ocupado} onClick={() => setSuspender(e)}>
                        <Pause className="h-4 w-4" aria-hidden="true" />
                        Suspender
                      </Button>
                    ) : (
                      <Button variant="secondary" className="h-11" disabled={ocupado} onClick={() => void cambiarEstado(e, true)}>
                        <Play className="h-4 w-4" aria-hidden="true" />
                        Reactivar
                      </Button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </>
        )}
      </main>

      {alta && (
        <Modal
          title="Nuevo establecimiento"
          onClose={() => setAlta(null)}
          footer={
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setAlta(null)} disabled={ocupado}>
                Cancelar
              </Button>
              <Button type="submit" form="form-establecimiento" disabled={ocupado}>
                Dar de alta
              </Button>
            </div>
          }
        >
          <form id="form-establecimiento" onSubmit={crear} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Código de ingreso" htmlFor="codigo" hint="3 a 30: minúsculas, números o guiones.">
                <input id="codigo" data-autofocus required pattern="[a-z0-9-]{3,30}" placeholder="luna" className={`${campo} font-mono`} value={alta.codigo} onChange={set('codigo')} />
              </Field>
              <Field label="Nombre" htmlFor="nombre">
                <input id="nombre" required placeholder="Motel Luna" className={campo} value={alta.nombre} onChange={set('nombre')} />
              </Field>
              <Field label="Domicilio" htmlFor="domicilio">
                <input id="domicilio" className={campo} value={alta.domicilio} onChange={set('domicilio')} />
              </Field>
              <Field label="Teléfono" htmlFor="telefono">
                <input id="telefono" className={campo} value={alta.telefono} onChange={set('telefono')} />
              </Field>
            </div>

            <fieldset className="grid grid-cols-3 gap-3">
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">Configuración inicial</legend>
              <Field label="Habitaciones" htmlFor="habitaciones">
                <input id="habitaciones" inputMode="numeric" required className={campo} value={alta.habitaciones} onChange={set('habitaciones')} />
              </Field>
              <Field label="Estadía base ($)" htmlFor="tarifa_base">
                <input id="tarifa_base" inputMode="decimal" required className={campo} value={alta.tarifa_base} onChange={set('tarifa_base')} />
              </Field>
              <Field label="Minutos base" htmlFor="estadia_base_min">
                <input id="estadia_base_min" inputMode="numeric" required className={campo} value={alta.estadia_base_min} onChange={set('estadia_base_min')} />
              </Field>
              <Field label="Fracción ($)" htmlFor="tarifa_fraccion">
                <input id="tarifa_fraccion" inputMode="decimal" required className={campo} value={alta.tarifa_fraccion} onChange={set('tarifa_fraccion')} />
              </Field>
              <Field label="Minutos de fracción" htmlFor="fraccion_min">
                <input id="fraccion_min" inputMode="numeric" required className={campo} value={alta.fraccion_min} onChange={set('fraccion_min')} />
              </Field>
              <Field label="Fondo de cambio ($)" htmlFor="fondo_cambio">
                <input id="fondo_cambio" inputMode="decimal" required className={campo} value={alta.fondo_cambio} onChange={set('fondo_cambio')} />
              </Field>
            </fieldset>

            <fieldset className="grid grid-cols-3 gap-3">
              <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-subtle">Gerencia inicial</legend>
              <Field label="Usuario" htmlFor="gerente_usuario">
                <input id="gerente_usuario" required autoCapitalize="none" className={campo} value={alta.gerente_usuario} onChange={set('gerente_usuario')} />
              </Field>
              <Field label="Nombre visible" htmlFor="gerente_nombre">
                <input id="gerente_nombre" required className={campo} value={alta.gerente_nombre} onChange={set('gerente_nombre')} />
              </Field>
              <Field label="Clave inicial" htmlFor="gerente_clave" hint="10 caracteres o más.">
                <input id="gerente_clave" type="password" required minLength={10} autoComplete="new-password" className={campo} value={alta.gerente_clave} onChange={set('gerente_clave')} />
              </Field>
            </fieldset>
            <p className="text-xs text-subtle">
              La gerencia inicial la crea la base con una función que solo funciona sobre un establecimiento vacío: la
              aplicación no puede agregar gerentes a un motel que ya opera.
            </p>
          </form>
        </Modal>
      )}

      {suspender && (
        <Modal
          title={`Suspender ${suspender.nombre}`}
          onClose={() => setSuspender(null)}
          footer={
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setSuspender(null)}>
                Cancelar
              </Button>
              <Button variant="danger" disabled={ocupado} onClick={() => void cambiarEstado(suspender, false)}>
                Suspender
              </Button>
            </div>
          }
        >
          <p className="text-sm text-ink">
            Sus usuarios pierden la sesión en el acto y no pueden volver a ingresar hasta que se lo reactive. No se borra
            ningún dato.
            {suspender.guardia_abierta && ' Atención: tiene una guardia abierta en este momento.'}
          </p>
        </Modal>
      )}
    </div>
  );
};

const Dato: React.FC<{ titulo: string; valor: string }> = ({ titulo, valor }) => (
  <div className="px-4 py-3">
    <p className="text-xs text-muted">{titulo}</p>
    <p className="mt-0.5 text-xl font-semibold tabular-nums text-ink">{valor}</p>
  </div>
);

const Cifra: React.FC<{ titulo: string; valor: string; pie: string }> = ({ titulo, valor, pie }) => (
  <div>
    <dt className="text-xs text-muted">{titulo}</dt>
    <dd className="text-lg font-semibold tabular-nums text-ink">{valor}</dd>
    <dd className="text-xs text-subtle">{pie}</dd>
  </div>
);

export default PlataformaView;
