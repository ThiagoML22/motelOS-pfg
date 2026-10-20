import React, { useState } from 'react';
import { Arqueo, Guardia } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney } from '../utils/format';
import { NOMBRE_FRANJA, aImporte, redondear } from '../utils/caja';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

interface CierreSupervisadoModalProps {
  guardia: Guardia;
  onClose: () => void;
  onCerrada: (arqueo: Arqueo) => void;
}

const MIN_OBSERVACION = 10;

// Guardia abandonada: la gerencia cuenta la gaveta y confirma el arqueo, también a ciegas (RN-RES-03).
// El arqueo queda en la caja del conserje y registra quién lo confirmó y por qué.
const CierreSupervisadoModal: React.FC<CierreSupervisadoModalProps> = ({ guardia, onClose, onCerrada }) => {
  const { toast } = useToast();
  const [efectivo, setEfectivo] = useState('');
  const [posnet, setPosnet] = useState('');
  const [mercadoPago, setMercadoPago] = useState('');
  const [observacion, setObservacion] = useState('');
  const [enviando, setEnviando] = useState(false);

  const valores = [aImporte(efectivo), aImporte(posnet), aImporte(mercadoPago)];
  const validos = valores.every((v) => v !== null) && observacion.trim().length >= MIN_OBSERVACION;
  const total = valores.every((v) => v !== null) ? redondear(valores.reduce<number>((s, v) => s + (v ?? 0), 0)) : null;

  const confirmar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validos) return;
    setEnviando(true);
    try {
      const arqueo = await api.cierreSupervisado(guardia.id, {
        efectivo: valores[0] ?? 0,
        posnet: valores[1] ?? 0,
        mercado_pago: valores[2] ?? 0,
        observacion: observacion.trim(),
      });
      toast(`Guardia de ${guardia.operador_nombre} cerrada: ${arqueo.categoria.toLowerCase()}.`, 'success');
      onCerrada(arqueo);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo cerrar la guardia.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  const campo = (id: string, label: string, valor: string, setValor: (v: string) => void, autofocus = false) => (
    <Field label={label} htmlFor={id} error={aImporte(valor) === null ? 'Importe inválido (hasta dos decimales).' : undefined}>
      <input
        id={id}
        inputMode="decimal"
        placeholder="0"
        data-autofocus={autofocus || undefined}
        className={`${inputClass} h-11 tabular-nums`}
        value={valor}
        onChange={(e) => setValor(e.target.value)}
      />
    </Field>
  );

  return (
    <Modal
      title={`Cierre supervisado · ${guardia.operador_nombre}`}
      subtitle={`Guardia ${NOMBRE_FRANJA[guardia.franja] ?? guardia.franja}, abierta el ${formatDateTime(guardia.abierta_en)}`}
      onClose={() => !enviando && onClose()}
      footer={
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm text-muted">
            Total contado: <span className="font-semibold tabular-nums text-ink">{total === null ? '—' : formatMoney(total)}</span>
          </span>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={onClose} disabled={enviando}>
              Cancelar
            </Button>
            <Button type="submit" form="form-cierre-supervisado" disabled={!validos || enviando}>
              {enviando ? 'Confirmando…' : 'Confirmar y cerrar guardia'}
            </Button>
          </div>
        </div>
      }
    >
      <p className="mb-4 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
        Use este cierre solo si el conserje dejó la guardia abierta. Cuente la gaveta y los comprobantes: el sistema
        no muestra el total hasta que confirme. El arqueo queda a nombre de {guardia.operador_nombre} y confirmado por
        usted.
      </p>
      <form id="form-cierre-supervisado" onSubmit={confirmar} className="space-y-4">
        <div className="grid grid-cols-3 gap-3">
          {campo('sup-efectivo', 'Efectivo ($)', efectivo, setEfectivo, true)}
          {campo('sup-posnet', 'POSNET ($)', posnet, setPosnet)}
          {campo('sup-mp', 'Mercado Pago ($)', mercadoPago, setMercadoPago)}
        </div>
        <Field
          label="Motivo del cierre supervisado"
          htmlFor="sup-observacion"
          hint={`Obligatorio, al menos ${MIN_OBSERVACION} caracteres. Queda registrado en el arqueo.`}
        >
          <textarea
            id="sup-observacion"
            rows={3}
            maxLength={300}
            className={inputClass}
            value={observacion}
            onChange={(e) => setObservacion(e.target.value)}
          />
        </Field>
      </form>
    </Modal>
  );
};

export default CierreSupervisadoModal;
