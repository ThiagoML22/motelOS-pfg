import React, { useState } from 'react';
import { AlertTriangle, ArrowRight, CheckCircle2, Layers, Rows3, Truck, WashingMachine } from 'lucide-react';
import { RecuentoAgrupado, RopaContada, TableroOperacion } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import { FilaMovimiento } from './MovimientoRopa';
import { PRENDAS, textoDiferencia } from './RecuentoRopa';
import Button from './ui/Button';
import { BarraPartes } from './ui/Graficos';
import { useToast } from './ui/Toast';

type Ropa = TableroOperacion['ropa'];

const Tarjeta: React.FC<{ titulo: string; detalle?: string; extra?: React.ReactNode; children: React.ReactNode }> = ({
  titulo,
  detalle,
  extra,
  children,
}) => (
  <section className="rounded-lg border border-line bg-surface p-5">
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
        {detalle && <p className="mt-0.5 text-xs text-muted">{detalle}</p>}
      </div>
      {extra}
    </div>
    <div className="mt-3">{children}</div>
  </section>
);

const Vacio: React.FC<{ children: React.ReactNode }> = ({ children }) => <p className="text-sm text-muted">{children}</p>;

interface Opcion {
  valor: boolean;
  label: string;
  detalle: string;
  icon: React.ElementType;
}

const FORMAS: Opcion[] = [
  { valor: true, label: 'Por estado', detalle: 'Limpias, sucias y en uso, cada una por separado.', icon: Rows3 },
  { valor: false, label: 'Todo junto', detalle: 'Un solo número por prenda.', icon: Layers },
];

const LAVANDERIAS: Opcion[] = [
  {
    valor: true,
    label: 'Propia',
    detalle: 'La ropa se lava en el motel: el conserje anota solo lo que se compra y lo que se tira.',
    icon: WashingMachine,
  },
  {
    valor: false,
    label: 'De afuera',
    detalle: 'Una lavandería se la lleva y la trae: el conserje anota también lo que sale y lo que vuelve.',
    icon: Truck,
  },
];

// Una elección de dos opciones que rige desde ya para los conserjes. Lo ya anotado no cambia.
const Ajuste: React.FC<{
  titulo: string;
  nota: string;
  opciones: Opcion[];
  valor: boolean;
  onElegir: (valor: boolean) => Promise<void>;
}> = ({ titulo, nota, opciones, valor, onElegir }) => {
  const [guardando, setGuardando] = useState(false);
  const elegir = async (nuevo: boolean) => {
    if (nuevo === valor || guardando) return;
    setGuardando(true);
    try {
      await onElegir(nuevo);
    } finally {
      setGuardando(false);
    }
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-3.5 first:pt-0 last:pb-0">
      <div className="min-w-0 sm:flex-1">
        <h3 className="text-sm font-semibold text-ink">{titulo}</h3>
        <p className="mt-0.5 text-xs text-muted">
          {opciones.find((o) => o.valor === valor)?.detalle} {nota}
        </p>
      </div>
      <div
        role="radiogroup"
        aria-label={titulo}
        className="grid w-full shrink-0 grid-cols-2 rounded-md border border-line-strong p-0.5 sm:flex sm:w-auto"
      >
        {opciones.map(({ valor: opcion, label, icon: Icon }) => {
          const elegida = opcion === valor;
          return (
            <button
              key={label}
              type="button"
              role="radio"
              aria-checked={elegida}
              disabled={guardando}
              onClick={() => void elegir(opcion)}
              className={`press hit flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded px-3.5 text-sm ${
                elegida ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'
              }`}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
};

// Cada motel trabaja a su manera: cómo cuentan los conserjes y quién lava. Lo que se controla entre un recuento y el
// siguiente es siempre el total, así que cambiar cualquiera de las dos no corta el control.
const AjustesDeRopa: React.FC<{ ropa: Ropa; onCambio: () => Promise<void> }> = ({ ropa, onCambio }) => {
  const { toast } = useToast();
  const guardar = async (accion: () => Promise<unknown>, aviso: string, error: string) => {
    try {
      await accion();
      toast(aviso, 'success');
      await onCambio();
    } catch (e) {
      toast(getErrorMessage(e, error), 'error');
    }
  };
  return (
    <section className="divide-y divide-line rounded-lg border border-line bg-surface px-5 py-3.5">
      <Ajuste
        titulo="Cómo cuentan los conserjes"
        nota="Un cambio rige desde el próximo recuento; el control de faltantes sigue igual, porque compara el total."
        opciones={FORMAS}
        valor={ropa.por_estado}
        onElegir={(valor) =>
          guardar(
            () => api.formaDeContarRopa(valor),
            valor ? 'Desde el próximo recuento se cuenta por estado.' : 'Desde el próximo recuento se cuenta todo junto.',
            'No se pudo cambiar la forma de contar.',
          )
        }
      />
      <Ajuste
        titulo="Lavandería"
        nota="Los conserjes ven solo las opciones que corresponden; lo ya anotado no cambia."
        opciones={LAVANDERIAS}
        valor={ropa.lavanderia_propia}
        onElegir={(valor) =>
          guardar(
            () => api.lavanderiaPropia(valor),
            valor ? 'Listo: la ropa se lava en el motel.' : 'Listo: la ropa va a una lavandería de afuera.',
            'No se pudo cambiar la lavandería.',
          )
        }
      />
    </section>
  );
};

const TarjetaPrenda: React.FC<{ fila: Ropa['resumen'][number]; dias: number; deAfuera: boolean }> = ({
  fila: r,
  dias,
  deAfuera,
}) => {
  const Icono = PRENDAS.find((p) => p.prenda === r.prenda)?.icon ?? Layers;
  const conPartes = r.limpias !== null && r.sucias !== null && r.en_habitaciones !== null && !!r.total;
  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Icono className="h-4 w-4 text-muted" aria-hidden="true" />
            {r.etiqueta}
          </h2>
          <p className="mt-0.5 text-xs text-muted">
            {r.contado_en ? `Último recuento: ${formatDateTime(r.contado_en)} · ${r.contado_por}` : 'Sin recuentos todavía.'}
          </p>
        </div>
        {deAfuera && r.en_lavanderia > 0 && (
          <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink">
            <Truck className="h-3.5 w-3.5 text-muted" aria-hidden="true" />
            <span className="tabular-nums">{r.en_lavanderia}</span> en lavandería
          </span>
        )}
      </div>

      <p className="mt-3 flex items-baseline gap-2">
        <span className="text-3xl font-semibold tabular-nums text-ink">{r.total ?? '—'}</span>
        <span className="text-sm text-muted">en el motel</span>
      </p>

      {conPartes ? (
        <div className="mt-3">
          <BarraPartes
            partes={[
              { clave: 'limpias', etiqueta: 'Limpias', parte: (r.limpias ?? 0) / (r.total ?? 1), valor: String(r.limpias) },
              { clave: 'sucias', etiqueta: 'Sucias', parte: (r.sucias ?? 0) / (r.total ?? 1), valor: String(r.sucias) },
              { clave: 'en_uso', etiqueta: 'En uso', parte: (r.en_habitaciones ?? 0) / (r.total ?? 1), valor: String(r.en_habitaciones) },
            ]}
          />
        </div>
      ) : (
        r.total !== null && <p className="mt-2 text-sm text-muted">Contadas todas juntas, sin separar por estado.</p>
      )}

      {r.total !== null && (
        <p className={`mt-4 flex items-start gap-1.5 border-t border-line pt-3 text-sm ${r.faltantes_del_mes > 0 ? 'font-medium text-danger' : 'text-muted'}`}>
          {r.faltantes_del_mes > 0 ? (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-libre" aria-hidden="true" />
          )}
          <span>
            {r.faltantes_del_mes > 0
              ? `Faltan ${r.faltantes_del_mes} sin explicar en los últimos ${dias} días`
              : `Sin faltantes en los últimos ${dias} días`}
            {r.faltantes > r.faltantes_del_mes && (
              <span className="font-normal text-muted"> · {r.faltantes} en todo el historial</span>
            )}
          </span>
        </p>
      )}
    </section>
  );
};

const unidades = (n: number, recuentos: number): string =>
  `${n} ${n === 1 ? 'unidad' : 'unidades'} en ${recuentos} ${recuentos === 1 ? 'recuento' : 'recuentos'}`;

const DondeFalto: React.FC<{ datos: Ropa['por_persona'] }> = ({ datos }) => (
  <Tarjeta
    titulo="Dónde faltó"
    detalle={`Últimos ${datos.dias} días, descontando lo que se anotó que entró o salió. Marca dónde mirar: no prueba quién fue.`}
  >
    {datos.en_guardia.length + datos.en_cambio.length === 0 ? (
      <p className="flex items-center gap-2 text-sm text-muted">
        <CheckCircle2 className="h-4 w-4 text-libre" aria-hidden="true" />
        Los recuentos coinciden.
      </p>
    ) : (
      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <h3 className="text-sm font-medium text-ink">Durante una guardia</h3>
          <p className="mt-0.5 text-xs text-muted">Entre lo que contó al abrir y lo que contó al cerrar la misma persona.</p>
          {datos.en_guardia.length === 0 ? (
            <p className="mt-2 text-sm text-muted">Nada.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {datos.en_guardia.map((f) => (
                <li key={f.operador} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                  <span className="text-ink">{f.operador}</span>
                  <span className="tabular-nums text-muted">{unidades(f.unidades, f.recuentos)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-sm font-medium text-ink">En el cambio de guardia</h3>
          <p className="mt-0.5 text-xs text-muted">Entre el cierre de uno y la apertura del otro: no se sabe de cuál de los dos.</p>
          {datos.en_cambio.length === 0 ? (
            <p className="mt-2 text-sm text-muted">Nada.</p>
          ) : (
            <ul className="mt-2 divide-y divide-line">
              {datos.en_cambio.map((f) => (
                <li key={`${f.dejo}-${f.recibio}`} className="flex flex-wrap items-baseline justify-between gap-x-3 py-2 text-sm">
                  <span className="flex items-center gap-1.5 text-ink">
                    {f.dejo}
                    <ArrowRight className="h-3.5 w-3.5 text-muted" aria-label="dejó a" />
                    {f.recibio}
                  </span>
                  <span className="tabular-nums text-muted">{unidades(f.unidades, f.recuentos)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    )}
  </Tarjeta>
);

const MOMENTO: Record<RecuentoAgrupado['momento'], string> = { APERTURA: 'Al abrir', CIERRE: 'Al cerrar' };

type PrendaContada = RecuentoAgrupado['prendas'][number];

const Control: React.FC<{ valor: RopaContada['diferencia'] }> = ({ valor }) =>
  valor === null ? (
    <span className="text-xs text-subtle">primer recuento</span>
  ) : valor === 0 ? (
    <span className="text-xs text-muted">coincide</span>
  ) : (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${valor < 0 ? 'bg-danger-soft text-danger' : 'bg-warn-soft text-warn'}`}>
      {textoDiferencia(valor)}
    </span>
  );

const CeldaPrenda: React.FC<{ prenda?: PrendaContada }> = ({ prenda: p }) =>
  !p ? (
    <td className="py-2.5 pl-4 text-subtle">—</td>
  ) : (
    <td className="py-2.5 pl-4 align-top max-sm:flex-1" data-etiqueta={p.etiqueta}>
      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className="font-semibold tabular-nums text-ink">{p.total}</span>
        <Control valor={p.diferencia} />
      </span>
      {p.limpias !== null && p.sucias !== null && p.en_habitaciones !== null && (
        <span className="mt-0.5 block text-xs tabular-nums text-muted">
          {p.limpias} limpias · {p.sucias} sucias · {p.en_habitaciones} en uso
        </span>
      )}
    </td>
  );

const PRIMEROS = 10;

const Recuentos: React.FC<{ recuentos: RecuentoAgrupado[] }> = ({ recuentos }) => {
  const [soloDiferencias, setSoloDiferencias] = useState(false);
  const [todos, setTodos] = useState(false);
  const filtrados = soloDiferencias ? recuentos.filter((r) => r.prendas.some((p) => p.diferencia)) : recuentos;
  const visibles = todos ? filtrados : filtrados.slice(0, PRIMEROS);

  return (
    <Tarjeta
      titulo="Recuentos"
      detalle="Uno al abrir y otro al cerrar cada guardia. No se pueden modificar."
      extra={
        recuentos.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={soloDiferencias} onChange={(e) => setSoloDiferencias(e.target.checked)} />
            Solo con diferencias
          </label>
        )
      }
    >
      {recuentos.length === 0 ? (
        <Vacio>Todavía no se hizo ningún recuento.</Vacio>
      ) : filtrados.length === 0 ? (
        <Vacio>Ninguno de los últimos recuentos tiene diferencias.</Vacio>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="tabla-movil sin-margen w-full min-w-[36rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th scope="col" className="py-2 font-medium">Cuándo</th>
                  <th scope="col" className="py-2 pl-4 font-medium">Quién contó</th>
                  {PRENDAS.map((p) => (
                    <th key={p.prenda} scope="col" className="py-2 pl-4 font-medium">
                      {p.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {visibles.map((r) => (
                  <tr key={r.clave}>
                    <td className="principal py-2.5 align-top">
                      <span className="block text-ink">
                        {MOMENTO[r.momento]}
                        <span className="font-normal text-muted sm:hidden"> · {r.operador}</span>
                      </span>
                      <span className="block text-xs font-normal text-muted">{formatDateTime(r.creado_en)}</span>
                    </td>
                    <td className="py-2.5 pl-4 align-top text-ink max-sm:hidden">{r.operador}</td>
                    {PRENDAS.map((p) => (
                      <CeldaPrenda key={p.prenda} prenda={r.prendas.find((x) => x.prenda === p.prenda)} />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtrados.length > PRIMEROS && (
            <Button variant="ghost" size="sm" className="mt-2" onClick={() => setTodos((v) => !v)}>
              {todos ? 'Ver menos' : `Ver los ${filtrados.length}`}
            </Button>
          )}
        </>
      )}
    </Tarjeta>
  );
};

// Lo que la gerencia ve de la ropa: cuánta hay, dónde faltó y cada recuento. Y elige cómo se cuenta y quién lava.
const RopaGerencia: React.FC<{ ropa: Ropa; onCambio: () => Promise<void> }> = ({ ropa, onCambio }) => (
  <div className="space-y-5">
    <AjustesDeRopa ropa={ropa} onCambio={onCambio} />

    <div className="grid gap-5 lg:grid-cols-2">
      {ropa.resumen.map((r) => (
        <TarjetaPrenda key={r.prenda} fila={r} dias={ropa.por_persona.dias} deAfuera={!ropa.lavanderia_propia} />
      ))}
    </div>

    <DondeFalto datos={ropa.por_persona} />

    <Recuentos recuentos={ropa.recuentos} />

    <Tarjeta
      titulo="Lo que entró y salió"
      detalle={
        ropa.lavanderia_propia
          ? 'Compras y bajas que anotaron los conserjes en su guardia.'
          : 'Lavandería, compras y bajas que anotaron los conserjes en su guardia.'
      }
    >
      {ropa.movimientos.length === 0 ? (
        <Vacio>No hay movimientos anotados.</Vacio>
      ) : (
        <ul className="divide-y divide-line">
          {ropa.movimientos.slice(0, 10).map((m) => (
            <FilaMovimiento key={m.id} movimiento={m} conQuien />
          ))}
        </ul>
      )}
    </Tarjeta>
  </div>
);

export default RopaGerencia;
