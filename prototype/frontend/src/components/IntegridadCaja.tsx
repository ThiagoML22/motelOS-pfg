import React, { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, Search, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react';
import { IntegridadComprobantes, VerificacionComprobante } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney } from '../utils/format';
import { NOMBRE_FRANJA } from '../utils/caja';
import Button from './ui/Button';
import { inputClass } from './ui/Field';
import { useToast } from './ui/Toast';

const ESLABONES = 48;
// La cadena se recorre a la vista aunque el cálculo termine antes: se entiende qué está pasando.
const RECORRIDO_MS = 800;

interface IntegridadCajaProps {
  // El código de un comprobante que llegó por su QR.
  codigoInicial?: string | null;
  // Cambia en cada recarga del panel: se vuelve a verificar.
  version: number;
  onAbrir: (arqueoId: number) => void;
}

// Comprobantes verificables: recalcula la huella de cada arqueo y marca el eslabón que ya no coincide. Es evidencia de que
// algo cambió después de firmarse, no una traba.
const IntegridadCaja: React.FC<IntegridadCajaProps> = ({ codigoInicial, version, onAbrir }) => {
  const { toast } = useToast();
  const [resultado, setResultado] = useState<IntegridadComprobantes | null>(null);
  const [verificando, setVerificando] = useState(false);
  const [vuelta, setVuelta] = useState(0);
  const [codigo, setCodigo] = useState(codigoInicial ?? '');
  const [comprobante, setComprobante] = useState<VerificacionComprobante | null>(null);
  const yaVerifico = useRef(false);

  const verificar = useCallback(async () => {
    setVerificando(true);
    setVuelta((v) => v + 1);
    try {
      const [datos] = await Promise.all([api.getIntegridad(), new Promise((r) => setTimeout(r, RECORRIDO_MS))]);
      setResultado(datos);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo verificar la cadena.'), 'error');
    } finally {
      setVerificando(false);
    }
  }, [toast]);

  useEffect(() => {
    void verificar();
  }, [verificar, version]);

  const buscar = useCallback(
    async (texto: string) => {
      if (!texto.trim()) return;
      try {
        setComprobante(await api.verificarComprobante(texto.trim()));
      } catch (err) {
        toast(getErrorMessage(err, 'No se pudo verificar el comprobante.'), 'error');
      }
    },
    [toast],
  );

  useEffect(() => {
    if (codigoInicial && !yaVerifico.current) {
      yaVerifico.current = true;
      void buscar(codigoInicial);
    }
  }, [codigoInicial, buscar]);

  const hayAlterados = (resultado?.alterados.length ?? 0) > 0;
  const rotos = new Set(
    (resultado?.alterados ?? []).map((a) => Math.min(Math.floor(((a.secuencia - 1) / (resultado?.total || 1)) * ESLABONES), ESLABONES - 1)),
  );

  return (
    <section aria-labelledby="titulo-integridad" className="mb-6 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="titulo-integridad" className="flex items-center gap-2 text-sm font-semibold text-ink">
          {hayAlterados ? <ShieldAlert className="h-4 w-4 text-danger" aria-hidden="true" /> : <ShieldCheck className="h-4 w-4 text-libre" aria-hidden="true" />}
          Integridad de los comprobantes
        </h2>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void buscar(codigo);
          }}
        >
          <div className="w-52">
            <input
              value={codigo}
              onChange={(e) => {
                setCodigo(e.target.value);
                setComprobante(null);
              }}
              maxLength={80}
              placeholder="Código del papel"
              aria-label="Código del comprobante"
              className={`${inputClass} !h-8 !py-0 font-mono text-xs`}
            />
          </div>
          <Button type="submit" variant="secondary" size="sm" disabled={!codigo.trim()} aria-label="Verificar este comprobante">
            <Search className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
          <Button variant="secondary" size="sm" onClick={() => void verificar()} disabled={verificando}>
            {verificando ? 'Verificando…' : 'Verificar ahora'}
          </Button>
        </form>
      </div>

      {/* La cadena: se enciende eslabón por eslabón; el que no coincide queda rojo. */}
      <div key={vuelta} className="mt-3 flex h-3 gap-[2px]" role="img" aria-label={hayAlterados ? 'Cadena con comprobantes alterados' : 'Cadena de comprobantes'}>
        {Array.from({ length: ESLABONES }, (_, i) => (
          <span
            key={i}
            className={`h-full flex-1 origin-bottom animate-eslabon rounded-[2px] transition-colors duration-300 ${
              verificando || !resultado ? 'bg-line-strong' : rotos.has(i) ? 'bg-danger' : 'bg-libre'
            }`}
            style={{ animationDelay: `${(i / ESLABONES) * RECORRIDO_MS * 0.85}ms` }}
          />
        ))}
      </div>

      {resultado && !verificando && (
        <div className="mt-2 animate-fade-in">
          {hayAlterados ? (
            <>
              <p className="text-sm font-medium text-danger">
                {resultado.alterados.length === 1 ? '1 comprobante no coincide' : `${resultado.alterados.length} comprobantes no coinciden`} con su
                huella.
              </p>
              <ul className="mt-2 space-y-1.5">
                {resultado.alterados.slice(0, 5).map((a) => (
                  <li key={a.secuencia} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-danger-soft px-3 py-2 text-sm">
                    <span className="min-w-0 text-ink">
                      <span className="font-medium">Arqueo n.º {a.arqueo_id}</span> · {a.operador_nombre}
                      {a.confirmado_en && ` · ${formatDateTime(a.confirmado_en)}`}
                      <span className="block text-xs text-muted">{a.motivo}</span>
                    </span>
                    <Button variant="secondary" size="sm" onClick={() => onAbrir(a.arqueo_id)}>
                      Ver el arqueo
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-muted">
              {resultado.total === 0 ? (
                'Todavía no hay comprobantes sellados.'
              ) : (
                <>
                  Los <span className="font-medium tabular-nums text-ink">{resultado.total}</span> comprobantes coinciden con su huella.
                </>
              )}
              {resultado.sin_sello > 0 && ` ${resultado.sin_sello} son anteriores a la cadena y no tienen huella.`}
            </p>
          )}
        </div>
      )}

      {comprobante && (
        <div
          role="status"
          className={`mt-3 flex animate-pop-in items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm ${
            comprobante.coincide ? 'border-libre/40 bg-libre-soft' : 'border-danger/40 bg-danger-soft'
          }`}
        >
          {comprobante.coincide ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-libre" aria-hidden="true" />
          ) : (
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
          )}
          <div className="min-w-0 flex-1">
            <p className="font-medium text-ink">{comprobante.detalle}</p>
            {comprobante.encontrado && comprobante.arqueo_id !== undefined && (
              <p className="mt-0.5 text-xs text-muted">
                Arqueo n.º {comprobante.arqueo_id} · {comprobante.operador_nombre}
                {comprobante.franja && ` · ${NOMBRE_FRANJA[comprobante.franja] ?? comprobante.franja}`}
                {comprobante.confirmado_en && ` · ${formatDateTime(comprobante.confirmado_en)}`}
                {comprobante.total_declarado !== undefined && ` · ${formatMoney(comprobante.total_declarado)} declarados`}
                {comprobante.categoria && ` · ${comprobante.categoria}`}
              </p>
            )}
          </div>
          {comprobante.arqueo_id !== undefined && (
            <Button variant="secondary" size="sm" onClick={() => onAbrir(comprobante.arqueo_id as number)}>
              Ver
            </Button>
          )}
        </div>
      )}
    </section>
  );
};

export default IntegridadCaja;
