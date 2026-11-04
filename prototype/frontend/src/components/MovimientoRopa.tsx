import React, { useState } from 'react';
import { Shirt } from 'lucide-react';
import { Prenda, TipoMovimientoRopa } from '../types';
import { api, getErrorMessage } from '../services/api';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';

const TIPOS: { value: TipoMovimientoRopa; label: string }[] = [
  { value: 'LAVANDERIA_SALE', label: 'Sale a la lavandería' },
  { value: 'LAVANDERIA_VUELVE', label: 'Vuelve de la lavandería' },
  { value: 'COMPRA', label: 'Compra' },
  { value: 'BAJA', label: 'Baja por rotura' },
];

// La ropa que entra o sale del motel se anota: así en el próximo recuento no aparece como faltante.
const MovimientoRopa: React.FC = () => {
  const { toast } = useToast();
  const [abierto, setAbierto] = useState(false);
  const [prenda, setPrenda] = useState<Prenda>('TOALLAS');
  const [tipo, setTipo] = useState<TipoMovimientoRopa>('LAVANDERIA_SALE');
  const [cantidad, setCantidad] = useState('');
  const [enviando, setEnviando] = useState(false);
  const valor = /^\d{1,6}$/.test(cantidad.trim()) ? parseInt(cantidad.trim(), 10) : 0;

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    try {
      await api.movimientoRopa({ prenda, tipo, cantidad: valor });
      toast('Movimiento de ropa registrado.', 'success');
      setAbierto(false);
      setCantidad('');
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo registrar el movimiento.'), 'error');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <>
      <Button variant="secondary" onClick={() => setAbierto(true)}>
        <Shirt className="h-4 w-4" aria-hidden="true" />
        Movimiento de ropa
      </Button>
      {abierto && (
        <Modal
          title="Movimiento de ropa"
          subtitle="Toallas y sábanas que entran o salen del motel."
          onClose={() => !enviando && setAbierto(false)}
          footer={
            <div className="flex justify-end gap-3">
              <Button variant="secondary" disabled={enviando} onClick={() => setAbierto(false)}>
                Cancelar
              </Button>
              <Button type="submit" form="form-movimiento-ropa" disabled={enviando || valor < 1}>
                Registrar
              </Button>
            </div>
          }
        >
          <form id="form-movimiento-ropa" onSubmit={(e) => void enviar(e)} className="space-y-4">
            <Field label="Qué" htmlFor="prenda-movimiento">
              <select id="prenda-movimiento" className={inputClass} value={prenda} onChange={(e) => setPrenda(e.target.value as Prenda)}>
                <option value="TOALLAS">Toallas</option>
                <option value="SABANAS">Sábanas</option>
              </select>
            </Field>
            <Field label="Movimiento" htmlFor="tipo-movimiento">
              <select
                id="tipo-movimiento"
                className={inputClass}
                value={tipo}
                onChange={(e) => setTipo(e.target.value as TipoMovimientoRopa)}
              >
                {TIPOS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Cantidad" htmlFor="cantidad-movimiento">
              <input
                id="cantidad-movimiento"
                data-autofocus
                inputMode="numeric"
                className={`${inputClass} tabular-nums`}
                value={cantidad}
                onChange={(e) => setCantidad(e.target.value)}
              />
            </Field>
          </form>
        </Modal>
      )}
    </>
  );
};

export default MovimientoRopa;
