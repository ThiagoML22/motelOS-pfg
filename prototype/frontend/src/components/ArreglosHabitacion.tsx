import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Plus, Wrench } from 'lucide-react';
import { Arreglo, HabitacionConDetalles, RubroArreglo, TipoArreglo } from '../types';
import { api, getErrorMessage } from '../services/api';
import { aImporte } from '../utils/caja';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import { useToast } from './ui/Toast';

export const RUBROS: { value: RubroArreglo; label: string }[] = [
  { value: 'AIRE', label: 'Aire o calefacción' },
  { value: 'PLOMERIA', label: 'Plomería' },
  { value: 'ELECTRICIDAD', label: 'Electricidad' },
  { value: 'TV', label: 'TV o Wi-Fi' },
  { value: 'MUEBLES', label: 'Muebles' },
  { value: 'OTRO', label: 'Otro' },
];

const TIPOS: { value: TipoArreglo; label: string }[] = [
  { value: 'FALLA', label: 'Falla' },
  { value: 'MANTENIMIENTO', label: 'Mantenimiento' },
];

export const claseEstadoArreglo = (estado: Arreglo['estado']): string =>
  estado === 'Resuelto'
    ? 'bg-surface-2 text-muted'
    : estado === 'En curso'
      ? 'bg-accent-soft text-accent'
      : 'bg-warn-soft text-warn';

interface FormResolverProps {
  arreglo: Arreglo;
  // La habitación sigue fuera de servicio hasta que se decida habilitarla.
  enMantenimiento: boolean;
  onListo: (actualizado: Arreglo) => void | Promise<void>;
  onCancelar: () => void;
}

export const FormResolverArreglo: React.FC<FormResolverProps> = ({ arreglo, enMantenimiento, onListo, onCancelar }) => {
  const { toast } = useToast();
  const [reparadoPor, setReparadoPor] = useState('');
  const [trabajo, setTrabajo] = useState('');
  const [costo, setCosto] = useState('');
  const [habilitar, setHabilitar] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const importe = aImporte(costo);

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    try {
      const resuelto = await api.resolverArreglo(arreglo.id, {
        reparado_por: reparadoPor.trim(),
        trabajo: trabajo.trim() || null,
        costo: costo.trim() ? importe : null,
        habilitar,
      });
      toast('Arreglo resuelto.', 'success');
      await onListo(resuelto);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo resolver el arreglo.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form onSubmit={(e) => void enviar(e)} className="space-y-4">
      <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-ink">
        {arreglo.rubro_nombre}: {arreglo.descripcion}
      </p>
      <Field label="Quién lo reparó" htmlFor="reparado-por" hint="La persona o el servicio.">
        <input
          id="reparado-por"
          data-autofocus
          maxLength={80}
          className={inputClass}
          value={reparadoPor}
          onChange={(e) => setReparadoPor(e.target.value)}
        />
      </Field>
      <Field label="Qué se hizo (opcional)" htmlFor="trabajo">
        <input id="trabajo" maxLength={200} className={inputClass} value={trabajo} onChange={(e) => setTrabajo(e.target.value)} />
      </Field>
      <Field
        label="Costo (opcional, $)"
        htmlFor="costo-arreglo"
        hint="Es informativo: no mueve la caja, y solo lo ve la gerencia."
        error={importe === null ? 'Importe inválido (hasta dos decimales).' : undefined}
      >
        <input
          id="costo-arreglo"
          inputMode="decimal"
          placeholder="0"
          className={`${inputClass} tabular-nums`}
          value={costo}
          onChange={(e) => setCosto(e.target.value)}
        />
      </Field>
      {enMantenimiento && (
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={habilitar} onChange={(e) => setHabilitar(e.target.checked)} />
          Dejar la habitación disponible
        </label>
      )}
      <div className="flex gap-3">
        <Button type="button" variant="secondary" className="flex-1" disabled={enviando} onClick={onCancelar}>
          Volver
        </Button>
        <Button type="submit" className="flex-1" disabled={enviando || !reparadoPor.trim() || importe === null}>
          Marcar como resuelto
        </Button>
      </div>
    </form>
  );
};

interface FormReportarProps {
  room: HabitacionConDetalles;
  onListo: () => void | Promise<void>;
  onCancelar: () => void;
}

const FormReportar: React.FC<FormReportarProps> = ({ room, onListo, onCancelar }) => {
  const { toast } = useToast();
  const [tipo, setTipo] = useState<TipoArreglo>('FALLA');
  const [rubro, setRubro] = useState<RubroArreglo>('AIRE');
  const [descripcion, setDescripcion] = useState('');
  const [fuera, setFuera] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const ocupada = room.estado === 'Ocupada';

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    try {
      await api.reportarArreglo({
        habitacion_id: room.id,
        tipo,
        rubro,
        descripcion: descripcion.trim(),
        fuera_de_servicio: fuera,
      });
      toast(fuera ? 'Quedó registrado y la habitación pasó a mantenimiento.' : 'Quedó registrado.', 'success');
      await onListo();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo registrar.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form onSubmit={(e) => void enviar(e)} className="space-y-4">
      <div role="radiogroup" aria-label="Tipo" className="grid grid-cols-2 gap-2">
        {TIPOS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={tipo === value}
            onClick={() => setTipo(value)}
            className={`press rounded-md border px-3 py-2.5 text-sm ${
              tipo === value
                ? 'border-accent bg-accent-soft font-medium text-accent'
                : 'border-line-strong bg-surface text-muted hover:text-ink'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <Field label="De qué es" htmlFor="rubro-arreglo">
        <select id="rubro-arreglo" className={inputClass} value={rubro} onChange={(e) => setRubro(e.target.value as RubroArreglo)}>
          {RUBROS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Qué pasa" htmlFor="descripcion-arreglo">
        <input
          id="descripcion-arreglo"
          data-autofocus
          maxLength={200}
          placeholder={tipo === 'FALLA' ? 'No enfría' : 'Limpieza de filtros'}
          className={inputClass}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />
      </Field>
      {ocupada ? (
        <p className="text-sm text-muted">La habitación está ocupada: para sacarla de servicio, primero trasladá el turno.</p>
      ) : (
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={fuera} onChange={(e) => setFuera(e.target.checked)} />
          Dejarla fuera de servicio hasta que se arregle
        </label>
      )}
      <div className="flex gap-3">
        <Button type="button" variant="secondary" className="flex-1" disabled={enviando} onClick={onCancelar}>
          Volver
        </Button>
        <Button type="submit" className="flex-1" disabled={enviando || !descripcion.trim()}>
          Registrar
        </Button>
      </div>
    </form>
  );
};

export const FilaArreglo: React.FC<{ arreglo: Arreglo; acciones?: React.ReactNode; conHabitacion?: boolean }> = ({
  arreglo: a,
  acciones,
  conHabitacion,
}) => (
  <li className="px-3 py-2.5">
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">
          {conHabitacion && a.numero !== null && <span className="tabular-nums">{formatRoomNumber(a.numero)} · </span>}
          {a.rubro_nombre}
          <span className="font-normal text-muted"> · {a.tipo_nombre}</span>
        </p>
        <p className="text-sm text-ink">{a.descripcion}</p>
        <p className="mt-0.5 text-xs text-muted">
          {formatDateTime(a.abierto_en)} · {a.abierto_por}
        </p>
        {a.estado === 'Resuelto' && (
          <p className="mt-1 text-xs text-muted">
            Lo reparó {a.reparado_por}
            {a.trabajo ? `: ${a.trabajo}` : ''}
            {a.resuelto_en ? ` · ${formatDateTime(a.resuelto_en)}` : ''}
            {a.costo !== null && <span className="font-medium tabular-nums text-ink"> · {formatMoney(a.costo)}</span>}
          </p>
        )}
      </div>
      <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${claseEstadoArreglo(a.estado)}`}>{a.estado}</span>
    </div>
    {acciones && <div className="mt-2 flex flex-wrap gap-2">{acciones}</div>}
  </li>
);

interface ArreglosHabitacionProps {
  room: HabitacionConDetalles;
  onCambio: () => Promise<void>;
  onVolver: () => void;
}

// El historial de arreglos de una habitación: lo que falta resolver primero, porque va ordenado del más nuevo al más viejo.
const ArreglosHabitacion: React.FC<ArreglosHabitacionProps> = ({ room, onCambio, onVolver }) => {
  const { toast } = useToast();
  const [arreglos, setArreglos] = useState<Arreglo[] | null>(null);
  const [modo, setModo] = useState<'lista' | 'nuevo' | Arreglo>('lista');
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setArreglos(await api.getArreglos({ habitacionId: room.id }));
    } catch (e) {
      setArreglos([]);
      toast(getErrorMessage(e, 'No se pudieron cargar los arreglos.'), 'error');
    }
  }, [room.id, toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const alTerminar = async () => {
    setModo('lista');
    await cargar();
    await onCambio();
  };

  const empezar = async (arreglo: Arreglo) => {
    setEnviando(true);
    try {
      await api.empezarArreglo(arreglo.id);
      await alTerminar();
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo actualizar el arreglo.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  if (modo === 'nuevo') return <FormReportar room={room} onListo={alTerminar} onCancelar={() => setModo('lista')} />;
  if (modo !== 'lista') {
    return (
      <FormResolverArreglo
        arreglo={modo}
        enMantenimiento={room.estado === 'Mantenimiento'}
        onListo={alTerminar}
        onCancelar={() => setModo('lista')}
      />
    );
  }

  return (
    <div className="space-y-4">
      {arreglos === null ? (
        <p className="text-sm text-muted">Cargando…</p>
      ) : arreglos.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted">
          <CheckCircle2 className="h-4 w-4 text-libre" aria-hidden="true" />
          Sin arreglos registrados.
        </p>
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line">
          {arreglos.map((a) => (
            <FilaArreglo
              key={a.id}
              arreglo={a}
              acciones={
                a.estado !== 'Resuelto' && (
                  <>
                    {a.estado === 'Abierto' && (
                      <Button size="sm" variant="secondary" disabled={enviando} onClick={() => void empezar(a)}>
                        Ya lo están viendo
                      </Button>
                    )}
                    <Button size="sm" disabled={enviando} onClick={() => setModo(a)}>
                      Resolver
                    </Button>
                  </>
                )
              }
            />
          ))}
        </ul>
      )}
      <div className="flex gap-3">
        <Button variant="secondary" className="flex-1" onClick={onVolver}>
          Volver
        </Button>
        <Button className="flex-1" onClick={() => setModo('nuevo')}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Registrar
        </Button>
      </div>
    </div>
  );
};

export const BotonArreglos: React.FC<{ abiertos: number; onClick: () => void }> = ({ abiertos, onClick }) => (
  <button type="button" onClick={onClick} className="press inline-flex items-center gap-1.5 text-sm font-medium text-accent hover:underline">
    <Wrench className="h-4 w-4" aria-hidden="true" />
    Arreglos
    {abiertos > 0 && (
      <span className="rounded-full bg-warn-soft px-1.5 text-xs font-medium tabular-nums text-warn">{abiertos}</span>
    )}
  </button>
);

export default ArreglosHabitacion;
