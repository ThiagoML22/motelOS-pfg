import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight, ArrowRightLeft, ChevronDown, Pencil, Repeat2, Shirt, Wrench } from 'lucide-react';
import { Arreglo, ConteoHistorial, TableroOperacion, TraspasoHistorial } from '../types';
import { api, EVENTO_RECONECTADO, getErrorMessage } from '../services/api';
import { aImporte, NOMBRE_FRANJA } from '../utils/caja';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import { FilaArreglo, FormResolverArreglo } from './ArreglosHabitacion';
import { textoDiferencia } from './RecuentoRopa';
import ResumenTraspaso from './ResumenTraspaso';
import Button from './ui/Button';
import { EsqueletoTabla } from './ui/Carga';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

type Seccion = 'arreglos' | 'ropa' | 'traspasos' | 'traslados';

const SECCIONES: { id: Seccion; label: string; icon: React.ElementType }[] = [
  { id: 'arreglos', label: 'Arreglos', icon: Wrench },
  { id: 'ropa', label: 'Ropa', icon: Shirt },
  { id: 'traspasos', label: 'Traspasos', icon: Repeat2 },
  { id: 'traslados', label: 'Traslados', icon: ArrowRightLeft },
];

const Tarjeta: React.FC<{ titulo: string; detalle?: string; children: React.ReactNode }> = ({ titulo, detalle, children }) => (
  <section className="rounded-lg border border-line bg-surface p-5">
    <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
    {detalle && <p className="mt-0.5 text-xs text-muted">{detalle}</p>}
    <div className="mt-3">{children}</div>
  </section>
);

const Dato: React.FC<{ nombre: string; valor: React.ReactNode; alerta?: boolean }> = ({ nombre, valor, alerta }) => (
  <div className="px-4 py-3">
    <p className="text-xs text-muted">{nombre}</p>
    <p className={`mt-0.5 text-xl font-semibold tabular-nums ${alerta ? 'text-danger' : 'text-ink'}`}>{valor}</p>
  </div>
);

const Vacio: React.FC<{ children: React.ReactNode }> = ({ children }) => <p className="text-sm text-muted">{children}</p>;

// --- Arreglos --------------------------------------------------------------------------------------------------------

const CostoModal: React.FC<{ arreglo: Arreglo; onClose: () => void; onListo: () => Promise<void> }> = ({ arreglo, onClose, onListo }) => {
  const { toast } = useToast();
  const [texto, setTexto] = useState(arreglo.costo === null ? '' : String(arreglo.costo));
  const [enviando, setEnviando] = useState(false);
  const importe = aImporte(texto);

  const guardar = async () => {
    setEnviando(true);
    try {
      await api.costoArreglo(arreglo.id, texto.trim() ? importe : null);
      toast('Costo actualizado.', 'success');
      await onListo();
      onClose();
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo guardar el costo.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Modal
      title="Costo del arreglo"
      subtitle={`${arreglo.numero === null ? '' : `${formatRoomNumber(arreglo.numero)} · `}${arreglo.rubro_nombre}`}
      onClose={() => !enviando && onClose()}
      footer={
        <div className="flex justify-end gap-3">
          <Button variant="secondary" disabled={enviando} onClick={onClose}>
            Cancelar
          </Button>
          <Button disabled={enviando || importe === null} onClick={() => void guardar()}>
            Guardar
          </Button>
        </div>
      }
    >
      <Field
        label="Costo ($)"
        htmlFor="costo-gerencia"
        hint="Informativo: no mueve la caja."
        error={importe === null ? 'Importe inválido (hasta dos decimales).' : undefined}
      >
        <input
          id="costo-gerencia"
          data-autofocus
          inputMode="decimal"
          className={`${inputClass} tabular-nums`}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
        />
      </Field>
    </Modal>
  );
};

const SeccionArreglos: React.FC<{ tablero: TableroOperacion; onCambio: () => Promise<void> }> = ({ tablero, onCambio }) => {
  const { arreglos } = tablero;
  const [editando, setEditando] = useState<Arreglo | null>(null);
  const [resolviendo, setResolviendo] = useState<Arreglo | null>(null);
  const [habitacion, setHabitacion] = useState<{ numero: number | null; lista: Arreglo[] } | null>(null);
  const { toast } = useToast();

  const verHabitacion = async (habitacionId: number, numero: number | null) => {
    try {
      setHabitacion({ numero, lista: await api.getArreglos({ habitacionId }) });
    } catch (e) {
      toast(getErrorMessage(e, 'No se pudo cargar el historial.'), 'error');
    }
  };

  const conCosto = (a: Arreglo) => (
    <Button size="sm" variant="secondary" onClick={() => setEditando(a)}>
      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
      {a.costo === null ? 'Cargar costo' : 'Corregir costo'}
    </Button>
  );

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Dato nombre="Sin resolver" valor={arreglos.sin_resolver.length} alerta={arreglos.sin_resolver.length > 0} />
        <Dato nombre={`Gastado en ${arreglos.dias} días`} valor={formatMoney(arreglos.costo_total)} />
        <Dato nombre="Resueltos sin costo cargado" valor={arreglos.sin_costo} />
      </div>

      <Tarjeta titulo="Sin resolver">
        {arreglos.sin_resolver.length === 0 ? (
          <Vacio>No hay arreglos pendientes.</Vacio>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line">
            {arreglos.sin_resolver.map((a) => (
              <FilaArreglo
                key={a.id}
                arreglo={a}
                conHabitacion
                acciones={
                  <Button size="sm" onClick={() => setResolviendo(a)}>
                    Resolver
                  </Button>
                }
              />
            ))}
          </ul>
        )}
      </Tarjeta>

      <div className="grid gap-5 lg:grid-cols-2">
        <Tarjeta titulo="Por rubro" detalle={`Resueltos en los últimos ${arreglos.dias} días.`}>
          {arreglos.por_rubro.length === 0 ? (
            <Vacio>Todavía no hay arreglos resueltos.</Vacio>
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line">
                {arreglos.por_rubro.map((r) => (
                  <tr key={r.rubro}>
                    <td className="py-2 text-ink">{r.nombre}</td>
                    <td className="py-2 text-right tabular-nums text-muted">{r.cantidad}</td>
                    <td className="py-2 text-right tabular-nums text-ink">{formatMoney(r.costo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Tarjeta>
        <Tarjeta titulo="Por habitación" detalle="Tocá una para ver todo su historial.">
          {arreglos.por_habitacion.length === 0 ? (
            <Vacio>Todavía no hay arreglos resueltos.</Vacio>
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line">
                {arreglos.por_habitacion.map((h) => (
                  <tr key={h.habitacion_id}>
                    <td className="py-2">
                      <button
                        type="button"
                        onClick={() => void verHabitacion(h.habitacion_id, h.numero)}
                        className="press font-medium text-accent hover:underline"
                      >
                        {h.numero === null ? 'Dada de baja' : formatRoomNumber(h.numero)}
                      </button>
                    </td>
                    <td className="py-2 text-right tabular-nums text-muted">{h.cantidad}</td>
                    <td className="py-2 text-right tabular-nums text-ink">{formatMoney(h.costo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Tarjeta>
      </div>

      <Tarjeta titulo="Resueltos" detalle={`Los de los últimos ${arreglos.dias} días.`}>
        {arreglos.resueltos.length === 0 ? (
          <Vacio>Todavía no hay arreglos resueltos.</Vacio>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line">
            {arreglos.resueltos.map((a) => (
              <FilaArreglo key={a.id} arreglo={a} conHabitacion acciones={conCosto(a)} />
            ))}
          </ul>
        )}
      </Tarjeta>

      {editando && <CostoModal arreglo={editando} onClose={() => setEditando(null)} onListo={onCambio} />}

      {resolviendo && (
        <Modal title="Resolver el arreglo" onClose={() => setResolviendo(null)}>
          <FormResolverArreglo
            arreglo={resolviendo}
            enMantenimiento={arreglos.en_mantenimiento.includes(resolviendo.habitacion_id)}
            onListo={async () => {
              setResolviendo(null);
              await onCambio();
            }}
            onCancelar={() => setResolviendo(null)}
          />
        </Modal>
      )}

      {habitacion && (
        <Modal
          title={habitacion.numero === null ? 'Historial de arreglos' : formatRoomNumber(habitacion.numero)}
          subtitle="Historial de arreglos"
          onClose={() => setHabitacion(null)}
        >
          <ul className="divide-y divide-line rounded-md border border-line">
            {habitacion.lista.map((a) => (
              <FilaArreglo key={a.id} arreglo={a} />
            ))}
          </ul>
        </Modal>
      )}
    </div>
  );
};

// --- Ropa ------------------------------------------------------------------------------------------------------------

const MOMENTO: Record<ConteoHistorial['momento'], string> = { APERTURA: 'Apertura', CIERRE: 'Cierre' };

const CeldaDiferencia: React.FC<{ valor: number | null }> = ({ valor }) =>
  valor === null ? (
    <span className="text-subtle">Primer recuento</span>
  ) : valor === 0 ? (
    <span className="text-muted">Coincide</span>
  ) : (
    <span className="font-medium text-danger">{textoDiferencia(valor)}</span>
  );

const SeccionRopa: React.FC<{ tablero: TableroOperacion }> = ({ tablero }) => {
  const { ropa } = tablero;
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-2">
        {ropa.resumen.map((r) => (
          <Tarjeta key={r.prenda} titulo={r.etiqueta} detalle={r.total === null ? 'Sin recuentos todavía.' : 'Según el último recuento.'}>
            <div className="grid grid-cols-3 gap-y-3 sm:grid-cols-5">
              {[
                ['Total', r.total],
                ['Limpias', r.limpias],
                ['Sucias', r.sucias],
                ['En habitaciones', r.en_habitaciones],
                ['En lavandería', r.en_lavanderia],
              ].map(([nombre, valor]) => (
                <div key={nombre as string}>
                  <p className="text-xs leading-tight text-muted">{nombre}</p>
                  <p className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{valor ?? '—'}</p>
                </div>
              ))}
            </div>
            {r.faltantes > 0 && (
              <p className="mt-3 flex items-center gap-1.5 text-sm font-medium text-danger">
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                {r.faltantes} sin explicar en todo el historial
              </p>
            )}
          </Tarjeta>
        ))}
      </div>

      <Tarjeta titulo="Diferencias" detalle="Entre un recuento y el siguiente, descontando lo que entró o salió del motel.">
        {ropa.diferencias.length === 0 ? (
          <Vacio>Los recuentos coinciden.</Vacio>
        ) : (
          <ul className="divide-y divide-line">
            {ropa.diferencias.map((d) => (
              <li key={d.id} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2 text-sm">
                <span className="text-ink">
                  <span className="font-medium">{d.etiqueta}:</span> <CeldaDiferencia valor={d.diferencia} />
                  <span className="text-muted">
                    {' '}
                    · {d.anterior_por === d.operador ? `en la guardia de ${d.operador}` : `entre ${d.anterior_por} y ${d.operador}`}
                  </span>
                </span>
                <span className="text-xs text-muted">{formatDateTime(d.creado_en)}</span>
              </li>
            ))}
          </ul>
        )}
      </Tarjeta>

      <Tarjeta titulo="Recuentos">
        {ropa.conteos.length === 0 ? (
          <Vacio>Todavía no se hizo ningún recuento.</Vacio>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th scope="col" className="py-2 font-medium">Cuándo</th>
                  <th scope="col" className="py-2 font-medium">Quién</th>
                  <th scope="col" className="py-2 font-medium">Qué</th>
                  <th scope="col" className="py-2 text-right font-medium">Limpias</th>
                  <th scope="col" className="py-2 text-right font-medium">Sucias</th>
                  <th scope="col" className="py-2 text-right font-medium">En hab.</th>
                  <th scope="col" className="py-2 text-right font-medium">Total</th>
                  <th scope="col" className="py-2 text-right font-medium">Control</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {ropa.conteos.map((c) => (
                  <tr key={c.id}>
                    <td className="py-2 text-muted">
                      {formatDateTime(c.creado_en)} · {MOMENTO[c.momento]}
                    </td>
                    <td className="py-2 text-ink">{c.operador}</td>
                    <td className="py-2 text-ink">{c.etiqueta}</td>
                    <td className="py-2 text-right tabular-nums">{c.limpias}</td>
                    <td className="py-2 text-right tabular-nums">{c.sucias}</td>
                    <td className="py-2 text-right tabular-nums">{c.en_habitaciones}</td>
                    <td className="py-2 text-right font-medium tabular-nums">{c.total}</td>
                    <td className="py-2 text-right">
                      <CeldaDiferencia valor={c.diferencia} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>

      <Tarjeta titulo="Movimientos" detalle="Lo que el personal anotó que entró o salió del motel.">
        {ropa.movimientos.length === 0 ? (
          <Vacio>No hay movimientos registrados.</Vacio>
        ) : (
          <ul className="divide-y divide-line">
            {ropa.movimientos.map((m) => (
              <li key={m.id} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2 text-sm">
                <span className="text-ink">
                  {m.tipo}: <span className="tabular-nums">{m.signo > 0 ? '+' : '−'}{m.cantidad}</span> {m.prenda.toLowerCase()}
                  <span className="text-muted"> · {m.operador}</span>
                </span>
                <span className="text-xs text-muted">{formatDateTime(m.creado_en)}</span>
              </li>
            ))}
          </ul>
        )}
      </Tarjeta>
    </div>
  );
};

// --- Traspasos -------------------------------------------------------------------------------------------------------

const FilaTraspaso: React.FC<{ traspaso: TraspasoHistorial }> = ({ traspaso: t }) => {
  const [abierto, setAbierto] = useState(false);
  const diferencias = t.resumen.ropa_recibida.filter((r) => r.diferencia);
  return (
    <li>
      <button
        type="button"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
        className="flex w-full items-center justify-between gap-3 py-3 text-left"
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-x-1.5 text-sm font-medium text-ink">
            {t.dejo ?? 'Primera guardia'}
            <ArrowRight className="h-3.5 w-3.5 text-muted" aria-label="dejó a" />
            {t.recibio}
            {t.sin_conteo && (
              <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">Sin conteo</span>
            )}
            {diferencias.map((r) => (
              <span key={r.prenda} className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">
                {r.etiqueta}: {textoDiferencia(r.diferencia ?? 0)}
              </span>
            ))}
          </span>
          <span className="block text-xs text-muted">
            {formatDateTime(t.creado_en)}
            {t.franja ? ` · guardia ${NOMBRE_FRANJA[t.franja] ?? t.franja}` : ''}
          </span>
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-muted transition-transform ${abierto ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {abierto && (
        <div className="mb-3 animate-fade-in rounded-md bg-surface-2 px-3 py-2">
          <ResumenTraspaso foto={t.resumen} />
          {t.resumen.novedades.length > 0 && (
            <ul className="mt-2 space-y-1 border-t border-line pt-2 text-sm text-ink">
              {t.resumen.novedades.map((n, i) => (
                <li key={i}>
                  {n.texto} <span className="text-muted">· {n.autor}</span>
                </li>
              ))}
            </ul>
          )}
          {t.resumen.ropa_recibida.length > 0 && (
            <p className="mt-2 border-t border-line pt-2 text-sm text-muted">
              Ropa contada al recibir:{' '}
              {t.resumen.ropa_recibida.map((r) => `${r.etiqueta.toLowerCase()} ${r.total}`).join(' · ')}
            </p>
          )}
        </div>
      )}
    </li>
  );
};

const SeccionTraspasos: React.FC<{ tablero: TableroOperacion }> = ({ tablero }) => (
  <Tarjeta titulo="Cambios de guardia" detalle="Lo que cada conserje confirmó haber recibido. No se puede modificar.">
    {tablero.traspasos.length === 0 ? (
      <Vacio>Todavía no hay traspasos.</Vacio>
    ) : (
      <ul className="divide-y divide-line">
        {tablero.traspasos.map((t) => (
          <FilaTraspaso key={t.id} traspaso={t} />
        ))}
      </ul>
    )}
  </Tarjeta>
);

const SeccionTraslados: React.FC<{ tablero: TableroOperacion }> = ({ tablero }) => (
  <Tarjeta titulo="Turnos trasladados" detalle="Cada uno conservó su hora, su tarifa y su cuenta.">
    {tablero.traslados.length === 0 ? (
      <Vacio>Todavía no se trasladó ningún turno.</Vacio>
    ) : (
      <ul className="divide-y divide-line">
        {tablero.traslados.map((t) => (
          <li key={t.id} className="flex flex-wrap items-baseline justify-between gap-x-4 py-2 text-sm">
            <span className="flex flex-wrap items-center gap-x-1.5 text-ink">
              {t.desde === null ? '—' : formatRoomNumber(t.desde)}
              <ArrowRight className="h-3.5 w-3.5 text-muted" aria-label="a" />
              {t.hacia === null ? '—' : formatRoomNumber(t.hacia)}
              <span className="text-muted">
                · {t.motivo} · {t.operador}
              </span>
            </span>
            <span className="text-xs text-muted">{formatDateTime(t.creado_en)}</span>
          </li>
        ))}
      </ul>
    )}
  </Tarjeta>
);

// La gerencia ve acá lo que pasa en la operación diaria. Los conserjes lo cargan desde la ventanilla.
const OperacionView: React.FC = () => {
  const { toast } = useToast();
  const [seccion, setSeccion] = useState<Seccion>('arreglos');
  const [tablero, setTablero] = useState<TableroOperacion | null>(null);
  const [fallo, setFallo] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setTablero(await api.getTableroOperacion());
      setFallo(false);
    } catch (e) {
      setFallo(true);
      toast(getErrorMessage(e, 'No se pudo cargar la operación.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
    const alReconectar = () => void cargar();
    window.addEventListener(EVENTO_RECONECTADO, alReconectar);
    return () => window.removeEventListener(EVENTO_RECONECTADO, alReconectar);
  }, [cargar]);

  return (
    <div className="w-full animate-fade-in">
      <div className="mb-5">
        <h1 className="text-xl font-semibold text-ink">Operación</h1>
        <p className="mt-0.5 text-sm text-muted">Arreglos, ropa, cambios de guardia y traslados de turno.</p>
      </div>

      <div role="tablist" aria-label="Secciones de la operación" className="mb-5 flex flex-wrap gap-1.5">
        {SECCIONES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={seccion === id}
            onClick={() => setSeccion(id)}
            className={`press hit flex h-11 items-center gap-2 rounded-md border px-4 text-sm ${
              seccion === id
                ? 'border-accent bg-accent-soft font-medium text-accent'
                : 'border-line-strong bg-surface text-muted hover:text-ink'
            }`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {!tablero && !fallo && <EsqueletoTabla filas={6} etiqueta="Cargando la operación…" />}
      {!tablero && fallo && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
          <p className="text-sm text-muted">No se pudo obtener la operación.</p>
          <Button variant="secondary" onClick={() => void cargar()}>
            Reintentar
          </Button>
        </div>
      )}
      {tablero && seccion === 'arreglos' && <SeccionArreglos tablero={tablero} onCambio={cargar} />}
      {tablero && seccion === 'ropa' && <SeccionRopa tablero={tablero} />}
      {tablero && seccion === 'traspasos' && <SeccionTraspasos tablero={tablero} />}
      {tablero && seccion === 'traslados' && <SeccionTraslados tablero={tablero} />}
    </div>
  );
};

export default OperacionView;
