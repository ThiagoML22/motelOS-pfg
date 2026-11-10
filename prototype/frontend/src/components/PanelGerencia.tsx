import React, { useCallback, useEffect, useState } from 'react';
import { BarChart3, DoorOpen, FileDown, RefreshCw, Tags } from 'lucide-react';
import { ArqueoDetalle, Guardia, MetricasCaja, ResumenCategoria } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney, formatRoomNumber } from '../utils/format';
import { CATEGORIA_META, NOMBRE_FRANJA, formatPorcentaje } from '../utils/caja';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';
import CierreSupervisadoModal from './CierreSupervisadoModal';
import HistorialArqueos from './HistorialArqueos';
import { EsqueletoTabla } from './ui/Carga';

// Línea de base de la AE1: 1 de cada 10 recambios con faltante o sobrante.
const TDC_LINEA_DE_BASE = 0.1;

type Rango = 'hoy' | '7' | '30' | 'todo';

const isoLocal = (fecha: Date): string =>
  `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, '0')}-${String(fecha.getDate()).padStart(2, '0')}`;

const desdeRango = (rango: Rango): string | undefined => {
  if (rango === 'todo') return undefined;
  const fecha = new Date();
  if (rango !== 'hoy') fecha.setDate(fecha.getDate() - (Number(rango) - 1));
  return isoLocal(fecha);
};

const MEDIO: Record<string, string> = { EFECTIVO: 'Efectivo', POSNET: 'POSNET', MERCADO_PAGO: 'Mercado Pago' };

// RF-09: la métrica por guardia y por operador que la gerencia hoy arma a mano (H-18), y la TDC medida
// por el sistema. Solo muestra arqueos confirmados: el total de una guardia abierta no se ve (RN-RES-03).
interface PanelGerenciaProps {
  onCambioGuardia: () => Promise<void>;
}

const PanelGerencia: React.FC<PanelGerenciaProps> = ({ onCambioGuardia }) => {
  const { toast } = useToast();
  const [rango, setRango] = useState<Rango>('30');
  const [operadorId, setOperadorId] = useState<number | ''>('');
  const [metricas, setMetricas] = useState<MetricasCaja | null>(null);
  const [porCategoria, setPorCategoria] = useState<ResumenCategoria[]>([]);
  // Cambia en cada recarga del panel: el historial de arqueos vuelve a pedir sus meses.
  const [version, setVersion] = useState(0);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [detalle, setDetalle] = useState<ArqueoDetalle | null>(null);
  const [guardiaAbierta, setGuardiaAbierta] = useState<Guardia | null>(null);
  const [supervisando, setSupervisando] = useState(false);

  const cargar = useCallback(async () => {
    const desde = desdeRango(rango);
    try {
      const [m, g, c] = await Promise.all([api.getMetricas({ desde }), api.getGuardiaActual(), api.getPorCategoria({ desde })]);
      setPorCategoria(c);
      setMetricas(m);
      setVersion((v) => v + 1);
      setGuardiaAbierta(g);
      setEstado('ok');
    } catch (err) {
      setEstado('error');
      toast(getErrorMessage(err, 'No se pudo cargar el panel de caja.'), 'error');
    }
  }, [rango, toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const abrirDetalle = async (id: number) => {
    try {
      setDetalle(await api.getArqueo(id));
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo abrir el arqueo.'), 'error');
    }
  };

  const general = metricas?.general;

  return (
    <div className="w-full animate-fade-in">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Control de caja</h1>
          <p className="mt-0.5 text-sm text-muted">Arqueos confirmados por guardia y por conserje</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div role="group" aria-label="Período" className="flex gap-1.5">
            {(
              [
                ['hoy', 'Hoy'],
                ['7', '7 días'],
                ['30', '30 días'],
                ['todo', 'Todo'],
              ] as [Rango, string][]
            ).map(([valor, etiqueta]) => (
              <button
                key={valor}
                type="button"
                aria-pressed={rango === valor}
                onClick={() => setRango(valor)}
                className={`press hit rounded-md border px-3 py-1.5 text-sm ${
                  rango === valor
                    ? 'border-accent bg-accent-soft font-medium text-accent'
                    : 'border-line-strong bg-surface text-muted hover:text-ink'
                }`}
              >
                {etiqueta}
              </button>
            ))}
          </div>
          <div className="w-48">
            <Field label="Conserje" htmlFor="filtro-operador">
              <select
                id="filtro-operador"
                className={inputClass}
                value={operadorId}
                onChange={(e) => setOperadorId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="">Todos</option>
                {metricas?.por_operador.map((m) => (
                  <option key={m.operador_id ?? 0} value={m.operador_id ?? ''}>
                    {m.operador_nombre}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Button variant="secondary" onClick={() => void cargar()} aria-label="Actualizar">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {estado === 'cargando' && <EsqueletoTabla etiqueta="Cargando arqueos…" />}
      {estado === 'error' && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
          <p className="text-sm text-muted">No se pudo obtener la información de caja.</p>
          <Button variant="secondary" onClick={() => void cargar()}>
            Reintentar
          </Button>
        </div>
      )}

      {estado === 'ok' && guardiaAbierta && !guardiaAbierta.es_propia && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface px-4 py-3">
          <p className="flex items-center gap-2 text-sm text-ink">
            <DoorOpen className="h-4 w-4 text-accent" aria-hidden="true" />
            Guardia abierta de <span className="font-medium">{guardiaAbierta.operador_nombre}</span>
            <span className="text-muted">
              · {NOMBRE_FRANJA[guardiaAbierta.franja] ?? guardiaAbierta.franja} · desde{' '}
              {formatDateTime(guardiaAbierta.abierta_en)}
            </span>
          </p>
          <Button variant="secondary" size="sm" onClick={() => setSupervisando(true)}>
            Cierre supervisado
          </Button>
        </div>
      )}

      {estado === 'ok' && general && (
        <>
          <div className="mb-5 grid grid-cols-2 divide-x divide-line overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-4">
            <div className="px-4 py-3">
              <p className="text-xs text-muted">Arqueos</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums text-ink">{general.arqueos}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-xs text-muted">TDC del período</p>
              <p
                className={`mt-0.5 text-xl font-semibold tabular-nums ${
                  general.arqueos > 0 && general.tdc > TDC_LINEA_DE_BASE ? 'text-danger' : 'text-ink'
                }`}
              >
                {general.arqueos > 0 ? formatPorcentaje(general.tdc) : '—'}
              </p>
              <p className="text-xs text-subtle">Línea de base: {formatPorcentaje(TDC_LINEA_DE_BASE)}</p>
            </div>
            <div className="px-4 py-3">
              <p className="text-xs text-muted">Faltantes</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums text-danger">{formatMoney(general.total_faltante)}</p>
              <p className="text-xs text-subtle">
                {general.faltantes} {general.faltantes === 1 ? 'arqueo' : 'arqueos'}
              </p>
            </div>
            <div className="px-4 py-3">
              <p className="text-xs text-muted">Sobrantes</p>
              <p className="mt-0.5 text-xl font-semibold tabular-nums text-warn">{formatMoney(general.total_sobrante)}</p>
              <p className="text-xs text-subtle">
                {general.sobrantes} {general.sobrantes === 1 ? 'arqueo' : 'arqueos'}
              </p>
            </div>
          </div>

          {metricas.por_operador.length > 0 && (
            <section aria-labelledby="titulo-por-conserje" className="mb-6">
              <h2 id="titulo-por-conserje" className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
                <BarChart3 className="h-4 w-4 text-muted" aria-hidden="true" />
                Por conserje
              </h2>
              <div className="overflow-x-auto rounded-lg border border-line bg-surface">
                <table className="w-full min-w-[40rem] text-left text-sm">
                  <thead>
                    <tr className="border-b border-line bg-surface-2 text-xs font-medium uppercase tracking-wide text-subtle">
                      <th scope="col" className="px-4 py-2.5">Conserje</th>
                      <th scope="col" className="px-4 py-2.5 text-right">Arqueos</th>
                      <th scope="col" className="px-4 py-2.5 text-right">Correctos</th>
                      <th scope="col" className="px-4 py-2.5 text-right">Faltantes</th>
                      <th scope="col" className="px-4 py-2.5 text-right">Sobrantes</th>
                      <th scope="col" className="px-4 py-2.5 text-right">TDC</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {metricas.por_operador.map((m) => (
                      <tr key={m.operador_id ?? 0}>
                        <td className="px-4 py-2.5 font-medium text-ink">{m.operador_nombre}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{m.arqueos}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{m.correctos}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-danger">
                          {m.faltantes} · {formatMoney(m.total_faltante)}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums text-warn">
                          {m.sobrantes} · {formatMoney(m.total_sobrante)}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatPorcentaje(m.tdc)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {porCategoria.length > 0 && (
            <section aria-labelledby="titulo-por-categoria" className="mb-6">
              <h2 id="titulo-por-categoria" className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
                <Tags className="h-4 w-4 text-muted" aria-hidden="true" />
                Por categoría de habitación
                <span className="font-normal text-subtle">· turnos cobrados en guardias ya arqueadas</span>
              </h2>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3">
                {porCategoria.map((c) => {
                  const total = porCategoria.reduce((s, x) => s + x.ingresos, 0) || 1;
                  const parte = c.ingresos / total;
                  return (
                    <article key={c.categoria_id} className="rounded-lg border border-line bg-surface p-4">
                      <div className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-2 font-semibold text-ink">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: c.color }} aria-hidden="true" />
                          {c.nombre}
                        </span>
                        <span className="text-xs text-muted">
                          Ocupadas {c.ocupadas}/{c.habitaciones}
                        </span>
                      </div>
                      <p className="mt-2 text-xl font-semibold tabular-nums text-ink">{formatMoney(c.ingresos)}</p>
                      <div className="mt-1 h-1.5 rounded-full bg-line" aria-hidden="true">
                        <div className="h-1.5 rounded-full" style={{ width: `${parte * 100}%`, backgroundColor: c.color }} />
                      </div>
                      <dl className="mt-3 grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <dt className="text-muted">Turnos</dt>
                          <dd className="font-medium tabular-nums text-ink">{c.turnos}</dd>
                        </div>
                        <div>
                          <dt className="text-muted">Ticket</dt>
                          <dd className="font-medium tabular-nums text-ink">{formatMoney(c.ticket_promedio)}</dd>
                        </div>
                        <div>
                          <dt className="text-muted">Estadía</dt>
                          <dd className="font-medium tabular-nums text-ink">{c.minutos_promedio} min</dd>
                        </div>
                      </dl>
                    </article>
                  );
                })}
              </div>
            </section>
          )}

          {/* Historial segmentado por mes y por día (independiente del período de arriba; respeta el conserje). */}
          <HistorialArqueos operadorId={operadorId} version={version} onAbrir={(id) => void abrirDetalle(id)} />
        </>
      )}

      {detalle && (
        <Modal
          size="lg"
          title={`Arqueo n.º ${detalle.id} · ${detalle.operador_nombre}`}
          subtitle={`Guardia ${NOMBRE_FRANJA[detalle.franja] ?? detalle.franja} · confirmado el ${formatDateTime(detalle.confirmado_en)}`}
          onClose={() => setDetalle(null)}
        >
          <div className="mb-4 grid grid-cols-3 gap-3 text-sm">
            <div className="rounded-md bg-surface-2 px-3 py-2">
              <p className="text-xs text-muted">Declarado</p>
              <p className="font-semibold tabular-nums">{formatMoney(detalle.total_declarado)}</p>
            </div>
            <div className="rounded-md bg-surface-2 px-3 py-2">
              <p className="text-xs text-muted">Sistema</p>
              <p className="font-semibold tabular-nums">{formatMoney(detalle.total_sistema)}</p>
            </div>
            <div className={`rounded-md px-3 py-2 ${CATEGORIA_META[detalle.categoria].clase}`}>
              <p className="text-xs">{detalle.categoria}</p>
              <p className="font-semibold tabular-nums">{formatMoney(detalle.diferencia)}</p>
            </div>
          </div>
          {detalle.supervisado && (
            <p className="mb-4 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
              Cierre supervisado por {detalle.confirmado_por_nombre}: {detalle.observacion}
            </p>
          )}
          <h3 className="mb-2 text-sm font-semibold text-ink">Cobros imputados a la guardia</h3>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-subtle">
                <th scope="col" className="py-2">Hora</th>
                <th scope="col" className="py-2">Habitación</th>
                <th scope="col" className="py-2">Medio</th>
                <th scope="col" className="py-2">Comprobante</th>
                <th scope="col" className="py-2 text-right">Monto</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {detalle.pagos.map((p, i) => (
                <tr key={i}>
                  <td className="py-2 tabular-nums text-muted">{formatDateTime(p.registrado_en)}</td>
                  <td className="py-2">{formatRoomNumber(p.habitacion_numero)}</td>
                  <td className="py-2">{MEDIO[p.medio_pago] ?? p.medio_pago}</td>
                  <td className="py-2 font-mono text-xs text-muted">{p.comprobante_referencia ?? '—'}</td>
                  <td className="py-2 text-right tabular-nums">{formatMoney(p.monto)}</td>
                </tr>
              ))}
              {detalle.pagos.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-muted">
                    La guardia no registró cobros.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {detalle.fondo_inicial > 0 && (
            <p className="mt-3 text-xs text-subtle">
              El efectivo del sistema incluye el fondo de cambio de {formatMoney(detalle.fondo_inicial)}.
            </p>
          )}
          <div className="mt-4 flex justify-end">
            <Button
              variant="secondary"
              className="h-11"
              onClick={() =>
                void api
                  .descargarComprobante(detalle.id, true)
                  .catch((err) => toast(getErrorMessage(err, 'No se pudo generar el comprobante en PDF.'), 'error'))
              }
            >
              <FileDown className="h-4 w-4" aria-hidden="true" />
              Comprobante en PDF
            </Button>
          </div>
        </Modal>
      )}

      {supervisando && guardiaAbierta && (
        <CierreSupervisadoModal
          guardia={guardiaAbierta}
          onClose={() => setSupervisando(false)}
          onCerrada={(arqueo) => {
            setSupervisando(false);
            void onCambioGuardia();
            void cargar().then(() => abrirDetalle(arqueo.id));
          }}
        />
      )}
    </div>
  );
};

export default PanelGerencia;
