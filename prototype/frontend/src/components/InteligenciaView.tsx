import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertOctagon,
  AlertTriangle,
  BedDouble,
  Bot,
  CalendarDays,
  Info,
  Lightbulb,
  Package,
  RefreshCw,
  Send,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { AlertaIA, RespuestaAsistente, Severidad, SugerenciaTarifa, Tablero } from '../types';
import { api, EVENTO_RECONECTADO, getErrorMessage } from '../services/api';
import { formatMoney, parseUtc } from '../utils/format';
import { formatMinutos } from '../utils/turno';
import Button from './ui/Button';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';
import { BarraPartes, BarrasHorizontales, Columnas, Linea, MapaCalor } from './ui/Graficos';

const porcentaje = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`);
const conSigno = (v: number | null) => {
  if (v === null) return null;
  const redondo = Math.round(v * 100);
  return redondo === 0 ? '0%' : `${redondo > 0 ? '+' : '−'}${Math.abs(redondo)}%`;
};
const dineroCorto = (v: number) =>
  v >= 1_000_000 ? `$${(v / 1_000_000).toLocaleString('es-AR', { maximumFractionDigits: 1 })} M` : v >= 1000 ? `$${Math.round(v / 1000)} mil` : `$${v}`;
const decimal = (v: number) => v.toLocaleString('es-AR', { maximumFractionDigits: 1 });

const ICONO_PUNTO: Record<string, React.ElementType> = {
  calendar: CalendarDays,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  sparkles: Sparkles,
  bed: BedDouble,
  wallet: Wallet,
  alert: AlertTriangle,
  package: Package,
  info: Info,
};

const SEVERIDAD: Record<Severidad, { icono: React.ElementType; etiqueta: string; clase: string }> = {
  alta: { icono: AlertOctagon, etiqueta: 'Importante', clase: 'bg-danger-soft text-danger' },
  media: { icono: AlertTriangle, etiqueta: 'Para revisar', clase: 'bg-warn-soft text-warn' },
  info: { icono: Info, etiqueta: 'Para saber', clase: 'bg-accent-soft text-accent' },
};

const URGENCIA = {
  alta: { etiqueta: 'Urgente', clase: 'bg-danger-soft text-danger' },
  media: { etiqueta: 'Esta semana', clase: 'bg-warn-soft text-warn' },
  baja: { etiqueta: 'Cubierto', clase: 'bg-libre-soft text-libre' },
  sin_movimiento: { etiqueta: 'Sin ventas', clase: 'bg-mant-soft text-mant' },
};

const Tarjeta: React.FC<{ titulo: string; icono?: React.ElementType; extra?: React.ReactNode; children: React.ReactNode; className?: string }> = ({
  titulo,
  icono: Icono,
  extra,
  children,
  className = '',
}) => (
  <section className={`rounded-lg border border-line bg-surface p-4 sm:p-5 ${className}`}>
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
        {Icono && <Icono className="h-4 w-4 text-muted" aria-hidden="true" />}
        {titulo}
      </h2>
      {extra && <div className="text-xs text-muted">{extra}</div>}
    </div>
    {children}
  </section>
);

// Inteligencia local: todo se calcula en el servidor del motel con los turnos de guardias ya arqueadas (RN-RES-03).
const InteligenciaView: React.FC = () => {
  const { toast } = useToast();
  const [tablero, setTablero] = useState<Tablero | null>(null);
  const [estado, setEstado] = useState<'cargando' | 'ok' | 'error'>('cargando');
  const [aplicando, setAplicando] = useState<SugerenciaTarifa | null>(null);

  const cargar = useCallback(async () => {
    try {
      setTablero(await api.getTablero());
      setEstado('ok');
    } catch (err) {
      setEstado((previo) => (previo === 'ok' ? 'ok' : 'error'));
      toast(getErrorMessage(err, 'No se pudo calcular el análisis.'), 'error');
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
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
            <Sparkles className="h-5 w-5 text-accent" aria-hidden="true" />
            Inteligencia
          </h1>
          <p className="mt-0.5 max-w-3xl text-sm text-muted">
            Análisis de los datos del motel calculado en este servidor: nada sale de esta computadora. Mira solo lo ya
            arqueado; la guardia en curso se suma cuando se cierra.
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted">
          {tablero && <span>Calculado a las {parseUtc(tablero.generado_en).toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })}</span>}
          <Button variant="secondary" onClick={() => void cargar()} aria-label="Recalcular">
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {estado === 'cargando' && <p className="py-16 text-center text-sm text-muted">Analizando los datos…</p>}
      {estado === 'error' && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface py-16">
          <p className="text-sm text-muted">No se pudo calcular el análisis.</p>
          <Button variant="secondary" onClick={() => void cargar()}>
            Reintentar
          </Button>
        </div>
      )}

      {estado === 'ok' && tablero && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_24rem]">
          <div className="min-w-0 space-y-5">
            <Resumen tablero={tablero} />
            <Indicadores tablero={tablero} />
            {tablero.alertas.length > 0 && <Alertas alertas={tablero.alertas} />}
            <PronosticoCard tablero={tablero} />
            <div className="grid gap-5 2xl:grid-cols-2">
              <SerieCard tablero={tablero} />
              <DemandaCard tablero={tablero} />
            </div>
            <Sugerencias sugerencias={tablero.sugerencias} onAplicar={setAplicando} />
            <ReposicionCard tablero={tablero} />
            <div className="grid gap-5 lg:grid-cols-2">
              <Tarjeta titulo="Cómo pagan los clientes" icono={Wallet} extra="últimos 30 días">
                {tablero.medios_de_pago.length ? (
                  <BarraPartes
                    partes={tablero.medios_de_pago.map((m) => ({ clave: m.medio, etiqueta: m.etiqueta, parte: m.parte, valor: formatMoney(m.monto) }))}
                  />
                ) : (
                  <p className="text-sm text-muted">Sin cobros en el período.</p>
                )}
              </Tarjeta>
              <Tarjeta titulo="Lo más vendido del minibar" icono={Package} extra="unidades, últimos 30 días">
                {tablero.mas_vendidos.length ? (
                  <BarrasHorizontales
                    filas={tablero.mas_vendidos.map((m) => ({ clave: m.articulo_id, etiqueta: m.descripcion, valor: m.unidades, texto: `${m.unidades} · ${formatMoney(m.importe)}` }))}
                  />
                ) : (
                  <p className="text-sm text-muted">Sin consumos en el período.</p>
                )}
              </Tarjeta>
            </div>
          </div>
          <aside className="xl:sticky xl:top-20 xl:self-start">
            <Asistente />
          </aside>
        </div>
      )}

      {aplicando && aplicando.propuesta && (
        <AplicarTarifa
          sugerencia={aplicando}
          onClose={() => setAplicando(null)}
          onAplicada={() => {
            setAplicando(null);
            void cargar();
          }}
        />
      )}
    </div>
  );
};

const Resumen: React.FC<{ tablero: Tablero }> = ({ tablero }) => (
  <section className="overflow-hidden rounded-lg border border-accent/30 bg-gradient-to-br from-accent-soft via-surface to-surface p-4 sm:p-5">
    <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-accent">
      <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
      Resumen del día
    </p>
    <p className="mt-1.5 text-lg font-semibold text-ink">{tablero.resumen.titular}</p>
    <ul className="mt-3 grid gap-2 md:grid-cols-2">
      {tablero.resumen.puntos.map((p, i) => {
        const Icono = ICONO_PUNTO[p.icono] ?? Info;
        return (
          <li key={i} className="flex gap-2.5 text-sm text-ink">
            <Icono className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
            <span>{p.texto}</span>
          </li>
        );
      })}
    </ul>
  </section>
);

const Indicadores: React.FC<{ tablero: Tablero }> = ({ tablero }) => {
  const k = tablero.indicadores;
  const tiles: { etiqueta: string; valor: string; nota?: string | null; variacion?: number | null }[] = [
    { etiqueta: 'Ocupadas ahora', valor: `${k.ocupadas_ahora} de ${k.habitaciones}` },
    { etiqueta: 'Turnos · 7 días', valor: String(k.turnos_7d), variacion: k.turnos_7d_variacion },
    { etiqueta: 'Ingresos · 7 días', valor: formatMoney(k.ingresos_7d), variacion: k.ingresos_7d_variacion },
    { etiqueta: 'Ticket promedio', valor: formatMoney(k.ticket_7d) },
    { etiqueta: 'Ocupación · 7 días', valor: porcentaje(k.ocupacion_7d) },
    { etiqueta: 'TDC · 30 días', valor: porcentaje(k.tdc_30d), nota: `${k.arqueos_30d} arqueos` },
  ];
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-3 2xl:grid-cols-6">
      {tiles.map((t) => {
        const cambio = t.variacion === undefined ? null : conSigno(t.variacion);
        return (
          <div key={t.etiqueta} className="bg-surface px-4 py-3">
            <p className="text-xs text-muted">{t.etiqueta}</p>
            <p className="mt-0.5 text-xl font-semibold text-ink">{t.valor}</p>
            {cambio && (
              <p className={`flex items-center gap-1 text-xs ${(t.variacion ?? 0) >= 0 ? 'text-libre' : 'text-danger'}`}>
                {(t.variacion ?? 0) >= 0 ? <TrendingUp className="h-3 w-3" aria-hidden="true" /> : <TrendingDown className="h-3 w-3" aria-hidden="true" />}
                {cambio} <span className="text-subtle">vs. semana anterior</span>
              </p>
            )}
            {t.nota && <p className="text-xs text-subtle">{t.nota}</p>}
          </div>
        );
      })}
    </div>
  );
};

const Alertas: React.FC<{ alertas: AlertaIA[] }> = ({ alertas }) => (
  <Tarjeta titulo="Alertas" icono={AlertTriangle} extra="últimos 30 días · detectadas por el sistema">
    <ul className="space-y-2">
      {alertas.map((a, i) => {
        const meta = SEVERIDAD[a.severidad];
        const Icono = meta.icono;
        return (
          <li key={i} className="rounded-md border border-line p-3">
            <div className="flex flex-wrap items-start gap-2">
              <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${meta.clase}`}>
                <Icono className="h-3.5 w-3.5" aria-hidden="true" />
                {meta.etiqueta}
              </span>
              <p className="min-w-0 flex-1 font-medium text-ink">{a.titulo}</p>
            </div>
            <p className="mt-1 text-sm text-muted">{a.detalle}</p>
            {a.evidencia.length > 0 && (
              <p className="mt-1 text-xs text-subtle">{a.evidencia.map((e) => `${e.etiqueta}: ${e.valor}`).join(' · ')}</p>
            )}
            {a.sugerencia && (
              <p className="mt-1.5 flex items-start gap-1.5 text-sm text-ink">
                <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" aria-hidden="true" />
                {a.sugerencia}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  </Tarjeta>
);

const PronosticoCard: React.FC<{ tablero: Tablero }> = ({ tablero }) => {
  const p = tablero.pronostico;
  if (!p.horas.length) {
    return (
      <Tarjeta titulo="Pronóstico de las próximas 24 horas" icono={Sparkles}>
        <p className="text-sm text-muted">Todavía no hay historia suficiente para pronosticar.</p>
      </Tarjeta>
    );
  }
  const etiquetas = p.horas.map((h, i) => (i % 3 === 0 ? h.etiqueta : null));
  return (
    <Tarjeta
      titulo="Pronóstico de las próximas 24 horas"
      icono={Sparkles}
      extra={p.precision ? `Error medio del método en la última semana: ${porcentaje(p.precision.error_medio)}` : undefined}
    >
      <p className="mb-3 text-sm text-ink">
        Se esperan unos <span className="font-semibold">{Math.round(p.total)} turnos</span> (entre {p.minimo} y {p.maximo})
        {p.pico && <> con el pico de llegadas a las <span className="font-semibold">{p.pico.etiqueta}</span></>}.
      </p>
      {p.saturacion.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {p.saturacion.map((s, i) => (
            <span key={i} className="inline-flex items-center gap-1.5 rounded-full bg-warn-soft px-2.5 py-1 text-xs font-medium text-warn">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} aria-hidden="true" />
              {s.categoria} se llenaría de {new Date(s.desde).getHours()} a {new Date(s.hasta).getHours()} h
            </span>
          ))}
        </div>
      )}
      <p className="text-xs font-medium text-muted">Llegadas esperadas por hora</p>
      <Columnas
        alto={150}
        descripcion="Llegadas esperadas por hora en las próximas 24 horas"
        formatoEje={(v) => decimal(v)}
        columnas={p.horas.map((h, i) => ({
          clave: h.hora,
          valor: h.llegadas,
          rango: [h.minimo, h.maximo],
          eje: etiquetas[i],
          detalle: (
            <>
              <p className="font-medium">{h.etiqueta}</p>
              <p>
                {decimal(h.llegadas)} llegadas (entre {decimal(h.minimo)} y {decimal(h.maximo)})
              </p>
              <p className="text-muted">{decimal(h.ocupacion)} habitaciones ocupadas</p>
            </>
          ),
        }))}
      />
      <p className="mt-3 text-xs font-medium text-muted">Habitaciones ocupadas esperadas</p>
      <Linea
        descripcion="Habitaciones ocupadas esperadas por hora"
        valores={p.horas.map((h) => h.ocupacion)}
        etiquetas={etiquetas}
        limite={tablero.indicadores.habitaciones}
        etiquetaLimite={`${tablero.indicadores.habitaciones} habitaciones`}
        detalle={(i) => (
          <>
            <p className="font-medium">{p.horas[i].etiqueta}</p>
            <p>
              {decimal(p.horas[i].ocupacion)} ocupadas · {porcentaje(p.horas[i].ocupacion_pct)}
            </p>
          </>
        )}
      />
      <p className="mt-2 text-xs text-subtle">
        Cómo se calcula: promedio ponderado de la misma hora en las 8 semanas anteriores (lo reciente pesa más), ajustado por
        la tendencia de las últimas dos semanas; la ocupación suma las estadías que siguen según cuánto duran en este motel.
      </p>
    </Tarjeta>
  );
};

const SerieCard: React.FC<{ tablero: Tablero }> = ({ tablero }) => {
  const total = tablero.serie.reduce((s, d) => s + d.ingresos, 0);
  return (
    <Tarjeta titulo="Ingresos por día" icono={TrendingUp} extra={`30 días · ${formatMoney(total)}`}>
      <Columnas
        descripcion="Ingresos cobrados por día en los últimos 30 días"
        formatoEje={dineroCorto}
        columnas={tablero.serie.map((d, i) => {
          const [, mes, dia] = d.fecha.split('-');
          return {
            clave: d.fecha,
            valor: d.ingresos,
            eje: i % 5 === 0 || i === tablero.serie.length - 1 ? `${Number(dia)}/${Number(mes)}` : null,
            detalle: (
              <>
                <p className="font-medium">
                  {d.dia} {Number(dia)}/{Number(mes)}
                </p>
                <p>{formatMoney(d.ingresos)}</p>
                <p className="text-muted">{d.turnos} turnos</p>
              </>
            ),
          };
        })}
      />
      <details className="mt-2 text-xs text-muted">
        <summary className="cursor-pointer select-none">Ver como tabla</summary>
        <div className="mt-2 max-h-48 overflow-y-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="text-subtle">
                <th className="py-1 font-medium">Día</th>
                <th className="py-1 text-right font-medium">Turnos</th>
                <th className="py-1 text-right font-medium">Ingresos</th>
              </tr>
            </thead>
            <tbody className="tabular-nums text-ink">
              {tablero.serie.map((d) => (
                <tr key={d.fecha}>
                  <td className="py-0.5">
                    {d.dia} {d.fecha.slice(8)}/{d.fecha.slice(5, 7)}
                  </td>
                  <td className="py-0.5 text-right">{d.turnos}</td>
                  <td className="py-0.5 text-right">{formatMoney(d.ingresos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Tarjeta>
  );
};

const DemandaCard: React.FC<{ tablero: Tablero }> = ({ tablero }) => {
  const d = tablero.demanda;
  return (
    <Tarjeta titulo="Cuándo llegan los clientes" icono={CalendarDays} extra={`promedio de ${decimal(d.semanas)} semanas`}>
      <MapaCalor
        filas={d.dias}
        valores={d.valores}
        maximo={d.maximo}
        detalle={(f, h) => (
          <>
            <p className="font-medium">
              {d.dias[f]} · {h} h
            </p>
            <p>{decimal(d.valores[f][h])} llegadas promedio</p>
          </>
        )}
      />
      <p className="mt-2 text-sm text-ink">
        El día más fuerte es el <span className="font-medium">{d.dia_mas_fuerte}</span> y el más flojo, el {d.dia_mas_flojo}. El
        pico: {d.pico.dia} a las {d.pico.hora} h ({decimal(d.pico.llegadas)} llegadas por hora).
      </p>
    </Tarjeta>
  );
};

const ACCION = {
  subir: { icono: TrendingUp, clase: 'text-libre' },
  bajar: { icono: TrendingDown, clase: 'text-warn' },
  estadia: { icono: Lightbulb, clase: 'text-accent' },
  mantener: { icono: Info, clase: 'text-muted' },
};

const Sugerencias: React.FC<{ sugerencias: SugerenciaTarifa[]; onAplicar: (s: SugerenciaTarifa) => void }> = ({ sugerencias, onAplicar }) => (
  <Tarjeta titulo="Sugerencias de tarifa por categoría" icono={Lightbulb} extra="últimas 4 semanas">
    <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
      {sugerencias.map((s) => {
        const meta = ACCION[s.accion];
        const Icono = meta.icono;
        return (
          <article key={s.categoria_id} className="flex flex-col rounded-md border border-line p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 font-semibold text-ink">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} aria-hidden="true" />
                {s.categoria}
              </span>
              <span className="text-xs text-muted">
                {s.habitaciones} hab. · {s.turnos} turnos
              </span>
            </div>
            <p className={`mt-2 flex items-center gap-1.5 text-sm font-medium ${meta.clase}`}>
              <Icono className="h-4 w-4" aria-hidden="true" />
              {s.titulo}
            </p>
            <p className="mt-1 text-sm text-muted">{s.explicacion}</p>
            <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
              <div>
                <dt className="text-subtle">Pico fin de semana</dt>
                <dd className="font-medium text-ink">{porcentaje(s.ocupacion_pico)}</dd>
              </div>
              <div>
                <dt className="text-subtle">Días de semana</dt>
                <dd className="font-medium text-ink">{porcentaje(s.ocupacion_valle)}</dd>
              </div>
              <div>
                <dt className="text-subtle">Con sobreturno</dt>
                <dd className="font-medium text-ink">{porcentaje(s.con_sobreturno)}</dd>
              </div>
            </dl>
            {s.propuesta && (
              <div className="mt-auto pt-3">
                {s.impacto_mensual !== null && (
                  <p className="mb-2 text-sm text-ink">
                    Efecto estimado:{' '}
                    <span className={`font-semibold ${s.impacto_mensual >= 0 ? 'text-libre' : 'text-danger'}`}>
                      {s.impacto_mensual >= 0 ? '+' : ''}
                      {formatMoney(s.impacto_mensual)} por mes
                    </span>
                  </p>
                )}
                <Button size="sm" variant="secondary" onClick={() => onAplicar(s)}>
                  Ver y aplicar
                </Button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  </Tarjeta>
);

const AplicarTarifa: React.FC<{ sugerencia: SugerenciaTarifa; onClose: () => void; onAplicada: () => void }> = ({
  sugerencia,
  onClose,
  onAplicada,
}) => {
  const { toast } = useToast();
  const [enviando, setEnviando] = useState(false);
  const { actual, propuesta } = sugerencia;
  if (!propuesta) return null;
  const filas: [string, string, string][] = [
    ['Estadía base', formatMoney(actual.tarifa_base), formatMoney(propuesta.tarifa_base)],
    ['Duración del turno', formatMinutos(actual.estadia_base_min), formatMinutos(propuesta.estadia_base_min)],
    ['Extra', `${formatMoney(actual.tarifa_fraccion)} cada ${actual.fraccion_min} min`, `${formatMoney(propuesta.tarifa_fraccion)} cada ${propuesta.fraccion_min} min`],
    ['Tolerancia', `${actual.tolerancia_min} min`, `${propuesta.tolerancia_min} min`],
    ['Tope', actual.tope ? formatMoney(actual.tope) : 'Sin tope', propuesta.tope ? formatMoney(propuesta.tope) : 'Sin tope'],
  ];
  const aplicar = async () => {
    setEnviando(true);
    try {
      await api.nuevaTarifa({ ...propuesta, categoria_id: sugerencia.categoria_id });
      toast(`Nueva tarifa de ${sugerencia.categoria} vigente desde ahora. Los turnos en curso conservan la suya.`, 'success');
      onAplicada();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo aplicar la tarifa.'), 'error');
      setEnviando(false);
    }
  };
  return (
    <Modal
      title={`${sugerencia.titulo} · ${sugerencia.categoria}`}
      subtitle="Revisá la propuesta antes de aplicarla. Queda en el historial de tarifas y en Actividad."
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => void aplicar()} disabled={enviando}>
            {enviando ? 'Aplicando…' : 'Aplicar nueva tarifa'}
          </Button>
        </div>
      }
    >
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs uppercase tracking-wide text-subtle">
            <th className="py-2 font-medium" />
            <th className="py-2 font-medium">Actual</th>
            <th className="py-2 font-medium">Propuesta</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {filas.map(([etiqueta, antes, despues]) => (
            <tr key={etiqueta}>
              <td className="py-2 text-muted">{etiqueta}</td>
              <td className="py-2 tabular-nums text-ink">{antes}</td>
              <td className={`py-2 tabular-nums ${antes !== despues ? 'font-semibold text-accent' : 'text-ink'}`}>{despues}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {sugerencia.impacto_mensual !== null && (
        <p className="mt-4 text-sm text-ink">
          Efecto estimado: <span className="font-semibold">{formatMoney(sugerencia.impacto_mensual)} por mes</span>.
        </p>
      )}
      {sugerencia.supuesto && <p className="mt-1 text-xs text-subtle">{sugerencia.supuesto}</p>}
    </Modal>
  );
};

const ReposicionCard: React.FC<{ tablero: Tablero }> = ({ tablero }) => {
  const filas = tablero.reposicion.filter((r) => r.urgencia !== 'sin_movimiento' || r.stock === 0);
  const aPedir = filas.filter((r) => r.sugerido > 0);
  return (
    <Tarjeta titulo="Reposición sugerida" icono={Package} extra={`${aPedir.length} artículos para pedir · cubre 14 días`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[36rem] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs font-medium uppercase tracking-wide text-subtle">
              <th className="py-2 pr-3">Artículo</th>
              <th className="py-2 pr-3 text-right">Stock</th>
              <th className="py-2 pr-3 text-right">Venta por día</th>
              <th className="py-2 pr-3 text-right">Alcanza para</th>
              <th className="py-2 pr-3 text-right">Pedir</th>
              <th className="py-2">Estado</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {filas.map((r) => (
              <tr key={r.articulo_id}>
                <td className="py-2 pr-3 text-ink">{r.descripcion}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{r.stock}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{decimal(r.por_dia)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{r.dias_restantes === null ? '—' : `${decimal(r.dias_restantes)} días`}</td>
                <td className="py-2 pr-3 text-right font-medium tabular-nums text-ink">{r.sugerido || '—'}</td>
                <td className="py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${URGENCIA[r.urgencia].clase}`}>
                    {URGENCIA[r.urgencia].etiqueta}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-subtle">
        Ritmo de venta de los últimos 28 días (la última semana pesa el doble); el pedido completa dos semanas y redondea a
        packs de 6.
      </p>
    </Tarjeta>
  );
};

// --- Asistente ------------------------------------------------------------------------------------------------------

const SUGERENCIAS_INICIALES = [
  '¿Cuánto facturamos la semana pasada?',
  '¿Cuántos turnos esperamos mañana?',
  '¿Qué categoría deja más plata?',
  '¿Quién tuvo más faltantes en los últimos 30 días?',
  '¿A qué hora hay más demanda los sábados?',
  '¿Cuál es la habitación menos usada?',
];

interface Mensaje {
  de: 'usuario' | 'asistente';
  texto: string;
  respuesta?: RespuestaAsistente;
}

const Asistente: React.FC = () => {
  const [mensajes, setMensajes] = useState<Mensaje[]>([
    {
      de: 'asistente',
      texto:
        'Hola. Preguntame lo que quieras saber del motel: ingresos, turnos, ocupación, horarios, categorías, caja, stock o lo que se espera para mañana.',
    },
  ]);
  const [texto, setTexto] = useState('');
  const [pensando, setPensando] = useState(false);
  const [sugeridas, setSugeridas] = useState(SUGERENCIAS_INICIALES);
  const lista = useRef<HTMLDivElement>(null);

  useEffect(() => {
    lista.current?.scrollTo({ top: lista.current.scrollHeight, behavior: 'smooth' });
  }, [mensajes, pensando]);

  const preguntar = async (pregunta: string) => {
    const limpia = pregunta.trim();
    if (!limpia || pensando) return;
    setTexto('');
    setMensajes((m) => [...m, { de: 'usuario', texto: limpia }]);
    setPensando(true);
    try {
      const respuesta = await api.preguntar(limpia);
      setMensajes((m) => [...m, { de: 'asistente', texto: respuesta.respuesta, respuesta }]);
      if (respuesta.sugerencias.length) setSugeridas(respuesta.sugerencias);
    } catch (err) {
      setMensajes((m) => [...m, { de: 'asistente', texto: getErrorMessage(err, 'No pude responder ahora. Probá de nuevo.') }]);
    } finally {
      setPensando(false);
    }
  };

  return (
    <section className="flex h-[min(78vh,46rem)] flex-col overflow-hidden rounded-lg border border-line bg-surface" aria-label="Asistente">
      <header className="flex items-center gap-2.5 border-b border-line px-4 py-3">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-accent text-accent-fg">
          <Bot className="h-4 w-4" aria-hidden="true" />
        </span>
        <div>
          <p className="text-sm font-semibold text-ink">Asistente</p>
          <p className="text-xs text-muted">Responde con los datos del motel, sin internet</p>
        </div>
      </header>
      <div ref={lista} className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
        {mensajes.map((m, i) => (
          <div key={i} className={`flex ${m.de === 'usuario' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[92%] rounded-lg px-3 py-2 text-sm ${
                m.de === 'usuario' ? 'rounded-br-sm bg-accent text-accent-fg' : 'rounded-bl-sm bg-surface-2 text-ink'
              }`}
            >
              <p className="whitespace-pre-line">{m.texto}</p>
              {m.respuesta?.tabla && m.respuesta.tabla.filas.length > 0 && (
                <div className="mt-2 overflow-x-auto rounded border border-line bg-surface">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-line text-subtle">
                        {m.respuesta.tabla.columnas.map((c) => (
                          <th key={c} className="px-2 py-1 font-medium">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {m.respuesta.tabla.filas.slice(0, 8).map((fila, j) => (
                        <tr key={j} className="border-b border-line last:border-0">
                          {fila.map((celda, k) => (
                            <td key={k} className="px-2 py-1">
                              {celda}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {(m.respuesta?.periodo || m.respuesta?.detalle) && (
                <p className="mt-1.5 text-[11px] text-muted">
                  {m.respuesta.periodo && <>Período: {m.respuesta.periodo}. </>}
                  {m.respuesta.detalle}
                </p>
              )}
            </div>
          </div>
        ))}
        {pensando && (
          <div className="flex justify-start">
            <div className="flex gap-1 rounded-lg rounded-bl-sm bg-surface-2 px-3 py-3" aria-label="Pensando">
              {[0, 1, 2].map((i) => (
                <span key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${i * 150}ms` }} />
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="border-t border-line px-3 py-3">
        <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
          {sugeridas.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => void preguntar(s)}
              className="press shrink-0 rounded-full border border-line-strong bg-surface px-2.5 py-1 text-xs text-muted hover:border-accent hover:text-accent"
            >
              {s}
            </button>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void preguntar(texto);
          }}
          className="flex gap-2"
        >
          <input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            maxLength={300}
            placeholder="Escribí tu pregunta…"
            aria-label="Pregunta para el asistente"
            className="min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-subtle focus:border-accent focus:ring-1 focus:ring-accent focus-visible:outline-none"
          />
          <Button type="submit" disabled={!texto.trim() || pensando} aria-label="Enviar pregunta">
            <Send className="h-4 w-4" aria-hidden="true" />
          </Button>
        </form>
      </div>
    </section>
  );
};

export default InteligenciaView;
