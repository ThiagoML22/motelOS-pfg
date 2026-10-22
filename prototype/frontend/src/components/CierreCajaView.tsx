import React, { useMemo, useState } from 'react';
import { CheckCircle2, EyeOff, LogOut, Printer, Lock } from 'lucide-react';
import { Arqueo, Sesion } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney } from '../utils/format';
import { CATEGORIA_META, NOMBRE_FRANJA, aImporte, redondear } from '../utils/caja';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

interface CierreCajaViewProps {
  sesion: Sesion;
  // El arqueo confirmado lo guarda la vista que contiene a esta pantalla: así el comprobante sigue a la vista
  // aunque la sesión, al refrescarse, ya informe la guardia como cerrada.
  resultado: Arqueo | null;
  onConfirmado: (arqueo: Arqueo) => void;
  onFinalizar: () => void;
}

// RF-08: cierre de caja ciego. El operador declara lo que tiene en la gaveta y los comprobantes sin ver
// el total del sistema (RN-RES-03); la pantalla no lo pide ni lo recibe hasta que confirma el recuento.
// El efectivo se declara como monto total, sin desglose por billete (acta del 19/10/2026, punto 6).
const CierreCajaView: React.FC<CierreCajaViewProps> = ({ sesion, resultado, onConfirmado, onFinalizar }) => {
  const { toast } = useToast();
  const [efectivoTexto, setEfectivoTexto] = useState('');
  const [posnet, setPosnet] = useState('');
  const [mercadoPago, setMercadoPago] = useState('');
  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const importes = useMemo(() => {
    const efectivo = aImporte(efectivoTexto);
    const posnetValor = aImporte(posnet);
    const mpValor = aImporte(mercadoPago);
    // El efectivo es obligatorio: una gaveta nunca se declara vacía por omisión.
    const validos = efectivoTexto.trim() !== '' && efectivo !== null && posnetValor !== null && mpValor !== null;
    return {
      efectivo,
      posnet: posnetValor,
      mercadoPago: mpValor,
      validos,
      declarado: validos ? redondear((efectivo ?? 0) + (posnetValor ?? 0) + (mpValor ?? 0)) : null,
    };
  }, [efectivoTexto, posnet, mercadoPago]);

  const confirmar = async () => {
    if (!importes.validos) return;
    setEnviando(true);
    try {
      const arqueo = await api.confirmarArqueo({
        efectivo: importes.efectivo ?? 0,
        posnet: importes.posnet ?? 0,
        mercado_pago: importes.mercadoPago ?? 0,
      });
      onConfirmado(arqueo);
      setConfirmando(false);
      toast('Arqueo confirmado. Su guardia quedó cerrada.', 'success');
    } catch (err) {
      setConfirmando(false);
      toast(getErrorMessage(err, 'No se pudo confirmar el arqueo.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  if (resultado) return <ResultadoArqueo arqueo={resultado} onFinalizar={onFinalizar} />;

  const guardia = sesion.guardia;

  return (
    <div className="w-full animate-fade-in">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-ink">Cierre de caja</h1>
          <p className="mt-0.5 text-sm text-muted">
            Guardia {guardia ? NOMBRE_FRANJA[guardia.franja] : ''} · {sesion.operador.nombre_visible}
            {guardia && <> · abierta el {formatDateTime(guardia.abierta_en)}</>}
          </p>
        </div>
      </div>

      <p className="mb-5 flex items-start gap-2 rounded-md border border-accent/30 bg-accent-soft px-4 py-3 text-sm text-accent">
        <EyeOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          Cierre ciego: declare el efectivo total de la gaveta y la suma de los comprobantes. El sistema le muestra
          el total que registró recién después de que confirme su declaración.
        </span>
      </p>

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <section aria-labelledby="titulo-efectivo" className="rounded-lg border border-line bg-surface p-5">
          <h2 id="titulo-efectivo" className="text-sm font-semibold text-ink">
            Efectivo en la gaveta
          </h2>
          <p className="mt-0.5 text-xs text-muted">Monto total en efectivo, sin desglose por billete.</p>
          <div className="mt-4 max-w-sm">
            <Field
              label="Efectivo total ($)"
              htmlFor="efectivo"
              hint={
                guardia && guardia.fondo_inicial > 0
                  ? `Incluye el fondo de cambio de ${formatMoney(guardia.fondo_inicial)} que recibió la caja.`
                  : undefined
              }
              error={aImporte(efectivoTexto) === null ? 'Importe inválido (hasta dos decimales).' : undefined}
            >
              <input
                id="efectivo"
                inputMode="decimal"
                placeholder="0"
                data-autofocus
                autoFocus
                className={`${inputClass} h-12 text-lg tabular-nums`}
                value={efectivoTexto}
                onChange={(e) => setEfectivoTexto(e.target.value)}
              />
            </Field>
          </div>
        </section>

        <section aria-labelledby="titulo-comprobantes" className="flex flex-col rounded-lg border border-line bg-surface p-5">
          <h2 id="titulo-comprobantes" className="text-sm font-semibold text-ink">
            Comprobantes electrónicos
          </h2>
          <p className="mt-0.5 text-xs text-muted">Suma de los cupones de cada medio.</p>
          <div className="mt-4 space-y-4">
            <Field
              label="POSNET ($)"
              htmlFor="posnet"
              error={aImporte(posnet) === null ? 'Importe inválido (hasta dos decimales).' : undefined}
            >
              <input
                id="posnet"
                inputMode="decimal"
                placeholder="0"
                className={`${inputClass} h-11 tabular-nums`}
                value={posnet}
                onChange={(e) => setPosnet(e.target.value)}
              />
            </Field>
            <Field
              label="Mercado Pago ($)"
              htmlFor="mercado-pago"
              error={aImporte(mercadoPago) === null ? 'Importe inválido (hasta dos decimales).' : undefined}
            >
              <input
                id="mercado-pago"
                inputMode="decimal"
                placeholder="0"
                className={`${inputClass} h-11 tabular-nums`}
                value={mercadoPago}
                onChange={(e) => setMercadoPago(e.target.value)}
              />
            </Field>
          </div>

          <div className="mt-auto pt-6">
            <div className="flex items-baseline justify-between border-t border-line pt-4">
              <span className="text-sm text-muted">Total declarado</span>
              <span className="text-2xl font-semibold tabular-nums text-ink">
                {importes.declarado === null ? '—' : formatMoney(importes.declarado)}
              </span>
            </div>
            <Button className="mt-4 w-full" disabled={!importes.validos} onClick={() => setConfirmando(true)}>
              <Lock className="h-4 w-4" aria-hidden="true" />
              Confirmar recuento y cerrar guardia
            </Button>
          </div>
        </section>
      </div>

      {confirmando && importes.validos && (
        <Modal
          title="Confirmar el arqueo"
          subtitle="Una vez confirmado no se puede modificar."
          onClose={() => !enviando && setConfirmando(false)}
          footer={
            <div className="flex justify-end gap-3">
              <Button variant="secondary" onClick={() => setConfirmando(false)} disabled={enviando}>
                Volver a contar
              </Button>
              <Button onClick={() => void confirmar()} disabled={enviando} data-autofocus>
                {enviando ? 'Confirmando…' : 'Confirmar'}
              </Button>
            </div>
          }
        >
          <dl className="space-y-2 text-sm">
            {[
              ['Efectivo', importes.efectivo ?? 0],
              ['POSNET', importes.posnet ?? 0],
              ['Mercado Pago', importes.mercadoPago ?? 0],
            ].map(([nombre, valor]) => (
              <div key={nombre as string} className="flex justify-between">
                <dt className="text-muted">{nombre}</dt>
                <dd className="tabular-nums text-ink">{formatMoney(valor as number)}</dd>
              </div>
            ))}
            <div className="flex justify-between border-t border-line pt-2 font-semibold">
              <dt>Total declarado</dt>
              <dd className="tabular-nums">{formatMoney(importes.declarado ?? 0)}</dd>
            </div>
          </dl>
          <p className="mt-4 text-xs text-muted">
            Al confirmar se cierra su guardia: no podrá registrar más cobros hasta abrir una nueva.
          </p>
        </Modal>
      )}
    </div>
  );
};

const ResultadoArqueo: React.FC<{ arqueo: Arqueo; onFinalizar: () => void }> = ({ arqueo, onFinalizar }) => {
  const meta = CATEGORIA_META[arqueo.categoria];
  const filas: [string, number, number][] = [
    ['Efectivo', arqueo.declarado_efectivo, arqueo.sistema_efectivo],
    ['POSNET', arqueo.declarado_posnet, arqueo.sistema_posnet],
    ['Mercado Pago', arqueo.declarado_mercado_pago, arqueo.sistema_mercado_pago],
  ];

  return (
    <div className="mx-auto w-full max-w-2xl animate-fade-in">
      <div data-print-area className="rounded-lg border border-line bg-surface p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-subtle">Comprobante de arqueo n.º {arqueo.id}</p>
            <h1 className="mt-1 text-lg font-semibold text-ink">
              Guardia {NOMBRE_FRANJA[arqueo.franja] ?? arqueo.franja}
            </h1>
            <p className="mt-0.5 text-sm text-muted">
              {arqueo.operador_nombre} · abierta el {formatDateTime(arqueo.abierta_en)} · confirmada el{' '}
              {formatDateTime(arqueo.confirmado_en)}
            </p>
          </div>
          <span className={`rounded-full px-3 py-1 text-sm font-semibold ${meta.clase}`}>{meta.label}</span>
        </div>

        <table className="mt-6 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-subtle">
              <th scope="col" className="py-2">Medio</th>
              <th scope="col" className="py-2 text-right">Declarado</th>
              <th scope="col" className="py-2 text-right">Sistema</th>
              <th scope="col" className="py-2 text-right">Diferencia</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {filas.map(([medio, declarado, sistema]) => (
              <tr key={medio}>
                <td className="py-2 text-ink">{medio}</td>
                <td className="py-2 text-right tabular-nums">{formatMoney(declarado)}</td>
                <td className="py-2 text-right tabular-nums">{formatMoney(sistema)}</td>
                <td className="py-2 text-right tabular-nums text-muted">{formatMoney(redondear(declarado - sistema))}</td>
              </tr>
            ))}
            <tr className="font-semibold">
              <td className="py-2">Total</td>
              <td className="py-2 text-right tabular-nums">{formatMoney(arqueo.total_declarado)}</td>
              <td className="py-2 text-right tabular-nums">{formatMoney(arqueo.total_sistema)}</td>
              <td className={`py-2 text-right tabular-nums ${arqueo.diferencia < 0 ? 'text-danger' : ''}`}>
                {formatMoney(arqueo.diferencia)}
              </td>
            </tr>
          </tbody>
        </table>
        {arqueo.fondo_inicial > 0 && (
          <p className="mt-2 text-xs text-subtle">
            El efectivo del sistema incluye el fondo de cambio de {formatMoney(arqueo.fondo_inicial)}.
          </p>
        )}
        <p className="mt-4 flex items-center gap-2 text-sm text-muted">
          <CheckCircle2 className="h-4 w-4 text-libre" aria-hidden="true" />
          {meta.descripcion} El arqueo quedó registrado y no se puede modificar.
        </p>
        <p className="mt-10 hidden w-56 border-t border-ink pt-1 text-center text-xs print:block">Firma del operador</p>
      </div>

      <div className="mt-5 flex justify-end gap-3">
        <Button variant="secondary" onClick={() => window.print()}>
          <Printer className="h-4 w-4" aria-hidden="true" />
          Imprimir comprobante
        </Button>
        <Button onClick={onFinalizar}>
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Finalizar y cerrar sesión
        </Button>
      </div>
    </div>
  );
};

export default CierreCajaView;
