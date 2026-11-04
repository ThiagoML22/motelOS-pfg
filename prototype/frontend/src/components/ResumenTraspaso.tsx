import React from 'react';
import { FotoVentanilla } from '../types';
import { formatRoomNumber } from '../utils/format';
import { formatMinutos } from '../utils/turno';

const Chip: React.FC<{ children: React.ReactNode; alerta?: boolean }> = ({ children, alerta }) => (
  <span
    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs tabular-nums ${
      alerta ? 'bg-warn-soft font-medium text-warn' : 'bg-surface-2 text-ink'
    }`}
  >
    {children}
  </span>
);

const Fila: React.FC<{ titulo: string; children: React.ReactNode }> = ({ titulo, children }) => (
  <div className="grid gap-1 py-2 sm:grid-cols-[9.5rem_1fr] sm:gap-3">
    <dt className="text-sm text-muted">{titulo}</dt>
    <dd className="flex min-w-0 flex-wrap gap-1.5 text-sm text-ink">{children}</dd>
  </div>
);

const numero = (n: number | null): string => (n === null ? 'Habitación dada de baja' : formatRoomNumber(n));

// Cómo está la ventanilla en el cambio de guardia. Sale del mismo dato para quien deja, para quien recibe y para la
// gerencia. No lleva importes ni patentes.
const ResumenTraspaso: React.FC<{ foto: FotoVentanilla; className?: string }> = ({ foto, className = '' }) => {
  const nada =
    foto.turnos.length + foto.pedidos.length + foto.limpieza.length + foto.mantenimiento.length + foto.arreglos.length === 0;
  if (nada) return <p className={`text-sm text-muted ${className}`}>Todas las habitaciones libres y nada pendiente.</p>;

  return (
    <dl className={`divide-y divide-line ${className}`}>
      {foto.turnos.length > 0 && (
        <Fila titulo="Turnos en curso">
          {foto.turnos.map((t) => (
            <Chip key={t.numero} alerta={t.excedido}>
              {numero(t.numero)} · {formatMinutos(t.lleva_min)}
            </Chip>
          ))}
        </Fila>
      )}
      {foto.pedidos.length > 0 && (
        <Fila titulo="Pedidos sin resolver">
          {foto.pedidos.map((p, i) => (
            <Chip key={i} alerta>
              {numero(p.numero)} · {p.cantidad ? `${p.cantidad} × ` : ''}
              {p.descripcion}
            </Chip>
          ))}
        </Fila>
      )}
      {foto.limpieza.length > 0 && (
        <Fila titulo="En limpieza">
          {foto.limpieza.map((n) => (
            <Chip key={n}>{numero(n)}</Chip>
          ))}
        </Fila>
      )}
      {foto.mantenimiento.length > 0 && (
        <Fila titulo="En mantenimiento">
          {foto.mantenimiento.map((n) => (
            <Chip key={n}>{numero(n)}</Chip>
          ))}
        </Fila>
      )}
      {foto.arreglos.length > 0 && (
        <Fila titulo="Arreglos abiertos">
          <ul className="w-full space-y-1">
            {foto.arreglos.map((a, i) => (
              <li key={i} className="min-w-0">
                <span className="font-medium">{numero(a.numero)}</span> · {a.rubro}: {a.descripcion}
                {a.estado === 'En curso' && <span className="text-muted"> (en curso)</span>}
              </li>
            ))}
          </ul>
        </Fila>
      )}
    </dl>
  );
};

export default ResumenTraspaso;
