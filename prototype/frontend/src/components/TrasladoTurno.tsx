import React, { useState } from 'react';
import { Wrench } from 'lucide-react';
import { Categoria, HabitacionConDetalles, MotivoTraslado, RubroArreglo } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatRoomNumber } from '../utils/format';
import { RUBROS } from './ArreglosHabitacion';
import { ChipCategoria } from './CategoriasConfig';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import { useToast } from './ui/Toast';

const MOTIVOS: { value: MotivoTraslado; label: string }[] = [
  { value: 'FALLA', label: 'Una falla' },
  { value: 'CLIENTE', label: 'Pidió el cliente' },
  { value: 'OTRO', label: 'Otro motivo' },
];

interface TrasladoTurnoProps {
  room: HabitacionConDetalles;
  habitaciones: HabitacionConDetalles[];
  categorias: Categoria[];
  onListo: () => Promise<void>;
  onVolver: () => void;
}

// El turno pasa entero a otra habitación libre: su hora, su tarifa, su cuenta y el QR del cliente siguen iguales.
const TrasladoTurno: React.FC<TrasladoTurnoProps> = ({ room, habitaciones, categorias, onListo, onVolver }) => {
  const { toast } = useToast();
  const [destino, setDestino] = useState<number | null>(null);
  const [motivo, setMotivo] = useState<MotivoTraslado>('CLIENTE');
  const [rubro, setRubro] = useState<RubroArreglo>('AIRE');
  const [descripcion, setDescripcion] = useState('');
  const [enviando, setEnviando] = useState(false);

  const libres = habitaciones.filter((h) => h.estado === 'Libre');
  const elegida = libres.find((h) => h.id === destino);
  const falla = motivo === 'FALLA';

  const enviar = async () => {
    const turnoId = room.turno_activo?.id;
    if (!turnoId || !elegida) return;
    setEnviando(true);
    try {
      const hecho = await api.trasladarTurno(turnoId, {
        habitacion_id: elegida.id,
        motivo,
        ...(falla ? { rubro, descripcion: descripcion.trim() } : {}),
      });
      const queda = hecho.origen_queda === 'Mantenimiento' ? 'mantenimiento, con su arreglo abierto' : 'limpieza';
      toast(`Turno trasladado a ${formatRoomNumber(elegida.numero)}. ${formatRoomNumber(room.numero)} pasa a ${queda}.`, 'success');
      await onListo();
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo trasladar el turno.'), 'error');
      setEnviando(false);
    }
  };

  if (libres.length === 0) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted">No hay habitaciones libres para trasladar el turno.</p>
        <Button variant="secondary" className="w-full" onClick={onVolver}>
          Volver
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">A qué habitación</h3>
        <div role="radiogroup" aria-label="Habitación de destino" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {libres.map((h) => {
            const categoria = categorias.find((c) => c.id === h.categoria_id);
            return (
              <button
                key={h.id}
                type="button"
                role="radio"
                aria-checked={destino === h.id}
                onClick={() => setDestino(h.id)}
                className={`press flex flex-col items-start gap-1 rounded-md border px-3 py-2 text-left text-sm ${
                  destino === h.id
                    ? 'border-accent bg-accent-soft font-medium text-accent'
                    : 'border-line-strong bg-surface text-ink hover:border-accent/50'
                }`}
              >
                <span className="flex items-center gap-1.5">
                  {formatRoomNumber(h.numero)}
                  {(h.arreglos_abiertos ?? 0) > 0 && (
                    <span title="Tiene arreglos sin resolver">
                      <Wrench className="h-3.5 w-3.5 text-warn" aria-hidden="true" />
                      <span className="sr-only">Tiene arreglos sin resolver</span>
                    </span>
                  )}
                </span>
                {categoria && <ChipCategoria categoria={categoria} />}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-subtle">Por qué</h3>
        <div role="radiogroup" aria-label="Motivo del traslado" className="grid grid-cols-3 gap-2">
          {MOTIVOS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={motivo === value}
              onClick={() => setMotivo(value)}
              className={`press rounded-md border px-2 py-2.5 text-sm ${
                motivo === value
                  ? 'border-accent bg-accent-soft font-medium text-accent'
                  : 'border-line-strong bg-surface text-muted hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {falla && (
        <div className="grid gap-4 sm:grid-cols-[1fr_1.4fr]">
          <Field label="De qué es" htmlFor="rubro-traslado">
            <select id="rubro-traslado" className={inputClass} value={rubro} onChange={(e) => setRubro(e.target.value as RubroArreglo)}>
              {RUBROS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Qué falló" htmlFor="descripcion-traslado">
            <input
              id="descripcion-traslado"
              maxLength={200}
              placeholder="No enfría"
              className={inputClass}
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
            />
          </Field>
        </div>
      )}

      <p className="text-sm text-muted">
        El turno sigue igual: la hora, la tarifa con la que entró, la cuenta y el QR del cliente.{' '}
        {falla
          ? `${formatRoomNumber(room.numero)} queda en mantenimiento con el arreglo abierto.`
          : `${formatRoomNumber(room.numero)} pasa a limpieza.`}
      </p>

      {/* En pantallas bajas el formulario se desplaza: confirmar queda siempre a la vista. */}
      <div className="sticky bottom-0 -mb-2 flex gap-3 border-t border-line bg-surface pb-2 pt-3">
        <Button variant="secondary" className="flex-1" disabled={enviando} onClick={onVolver}>
          Volver
        </Button>
        <Button
          className="flex-[2]"
          disabled={enviando || !elegida || (falla && !descripcion.trim())}
          onClick={() => void enviar()}
        >
          {elegida ? `Trasladar a ${formatRoomNumber(elegida.numero)}` : 'Elegí una habitación'}
        </Button>
      </div>
    </div>
  );
};

export default TrasladoTurno;
