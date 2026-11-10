import React, { useEffect, useRef, useState } from 'react';
import { AlertTriangle, ChevronDown, MessageSquarePlus, NotebookPen } from 'lucide-react';
import { HabitacionConDetalles, Novedad } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatRoomNumber, parseUtc } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

// Novedades de guardia (migración 009): lo que el personal deja escrito para el turno siguiente y para la gerencia.
// Solo se agregan; no se editan ni se borran.

export const recientes = (novedades: Novedad[], horas = 24): Novedad[] => {
  const desde = Date.now() - horas * 3600_000;
  return novedades.filter((n) => parseUtc(n.creado_en).getTime() >= desde);
};

export const ListaNovedades: React.FC<{ novedades: Novedad[]; vacio?: string }> = ({ novedades, vacio }) =>
  novedades.length === 0 ? (
    <p className="text-sm text-muted">{vacio ?? 'Sin novedades.'}</p>
  ) : (
    <ul className="space-y-2">
      {novedades.map((n) => (
        <li
          key={n.id}
          className={`rounded-md border px-3 py-2 text-left text-sm ${n.importante ? 'border-warn/40 bg-warn-soft' : 'border-line bg-surface'}`}
        >
          <p className="flex items-start gap-2 text-ink">
            {n.importante && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-label="Importante" />}
            <span className="min-w-0 flex-1 whitespace-pre-line">{n.texto}</span>
          </p>
          <p className="mt-1 text-xs text-muted">
            {n.operador_nombre}
            {n.franja && ` · guardia de las ${n.franja}`}
            {n.habitacion_numero !== null && ` · ${formatRoomNumber(n.habitacion_numero)}`} · {formatDateTime(n.creado_en)}
          </p>
        </li>
      ))}
    </ul>
  );

interface NuevaNovedadProps {
  habitaciones: HabitacionConDetalles[];
  onClose: () => void;
  onCreada: () => void;
}

export const NuevaNovedadModal: React.FC<NuevaNovedadProps> = ({ habitaciones, onClose, onCreada }) => {
  const { toast } = useToast();
  const [texto, setTexto] = useState('');
  const [importante, setImportante] = useState(false);
  const [habitacionId, setHabitacionId] = useState<number | ''>('');
  const [enviando, setEnviando] = useState(false);

  const guardar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    try {
      await api.crearNovedad({ texto, importante, habitacion_id: habitacionId === '' ? null : habitacionId });
      toast('Novedad registrada: la ve la guardia siguiente y la gerencia.', 'success');
      onCreada();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo registrar la novedad.'), 'error');
      setEnviando(false);
    }
  };

  return (
    <Modal title="Dejar una novedad" subtitle="Queda a su nombre y no se puede borrar." onClose={onClose}>
      <form onSubmit={guardar} className="space-y-4">
        <Field label="Novedad" htmlFor="novedad_texto" hint={`${texto.length}/500`}>
          <textarea
            id="novedad_texto"
            data-autofocus
            rows={4}
            maxLength={500}
            required
            placeholder="Ej.: la 7 tiene la ducha floja; faltan toallas en el depósito."
            className={inputClass}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
          />
        </Field>
        <Field label="Habitación (opcional)" htmlFor="novedad_hab">
          <select
            id="novedad_hab"
            className={`${inputClass} h-11`}
            value={habitacionId}
            onChange={(e) => setHabitacionId(e.target.value === '' ? '' : Number(e.target.value))}
          >
            <option value="">Ninguna en particular</option>
            {habitaciones.map((h) => (
              <option key={h.id} value={h.id}>
                {formatRoomNumber(h.numero)}
              </option>
            ))}
          </select>
        </Field>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-ink">
          <input type="checkbox" className="h-4 w-4" checked={importante} onChange={(e) => setImportante(e.target.checked)} />
          Marcar como importante (se destaca en amarillo y en la campanita de la gerencia)
        </label>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" disabled={enviando || !texto.trim()}>
            {enviando ? 'Guardando…' : 'Guardar novedad'}
          </Button>
        </div>
      </form>
    </Modal>
  );
};

interface NovedadesCardProps {
  novedades: Novedad[];
  onNueva: () => void;
}

// Una sola línea sobre la grilla: la novedad más importante de las últimas 24 horas. «Ver todas» abre la lista completa
// superpuesta, así las habitaciones (lo principal de la ventanilla) no se corren.
export const NovedadesCard: React.FC<NovedadesCardProps> = ({ novedades, onNueva }) => {
  const [abierta, setAbierta] = useState(false);
  const contenedor = useRef<HTMLDivElement>(null);
  const ultimas = recientes(novedades).sort((a, b) => Number(b.importante) - Number(a.importante) || b.id - a.id);
  const primera = ultimas[0];

  useEffect(() => {
    if (!abierta) return;
    const fuera = (e: MouseEvent) => {
      if (!contenedor.current?.contains(e.target as Node)) setAbierta(false);
    };
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setAbierta(false);
    document.addEventListener('mousedown', fuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', fuera);
      document.removeEventListener('keydown', escape);
    };
  }, [abierta]);

  return (
    <section ref={contenedor} className="relative mb-3 flex items-center gap-2 rounded-lg border border-line bg-surface px-2.5 py-1.5" aria-labelledby="titulo-novedades">
      <h2 id="titulo-novedades" className="flex shrink-0 items-center gap-1.5 text-sm font-semibold text-ink">
        <NotebookPen className="h-4 w-4 text-muted" aria-hidden="true" />
        <span className="hidden sm:inline">Novedades</span>
        {ultimas.length > 0 && <span className="text-xs font-normal tabular-nums text-subtle">{ultimas.length}</span>}
      </h2>
      {primera ? (
        <p
          title={primera.texto}
          className={`flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1 text-sm ${primera.importante ? 'bg-warn-soft' : 'bg-surface-2'}`}
        >
          {primera.importante && <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-warn" aria-label="Importante" />}
          <span className="min-w-0 flex-1 truncate text-ink">{primera.texto}</span>
          <span className="hidden shrink-0 text-xs text-muted lg:inline">
            {primera.operador_nombre}
            {primera.habitacion_numero !== null && ` · ${formatRoomNumber(primera.habitacion_numero)}`} ·{' '}
            {parseUtc(primera.creado_en).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })}
          </span>
        </p>
      ) : (
        <p className="min-w-0 flex-1 truncate text-sm text-muted">Sin novedades en las últimas 24 horas.</p>
      )}
      {ultimas.length > 1 && (
        <button
          type="button"
          onClick={() => setAbierta((v) => !v)}
          aria-expanded={abierta}
          className="press inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-accent hover:bg-accent-soft"
        >
          Ver todas
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${abierta ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
      )}
      <Button variant="secondary" size="sm" onClick={onNueva} className="shrink-0" aria-label="Dejar novedad">
        <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">Dejar novedad</span>
      </Button>
      {abierta && (
        <div className="absolute inset-x-0 top-full z-20 mt-2 max-h-[60vh] animate-pop-in overflow-y-auto rounded-lg border border-line bg-surface p-3 shadow-panel">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">Novedades de las últimas 24 horas</p>
          <ListaNovedades novedades={ultimas} />
        </div>
      )}
    </section>
  );
};
