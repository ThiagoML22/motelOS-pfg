import React, { useCallback, useEffect, useState } from 'react';
import { Link2, Printer, RefreshCw } from 'lucide-react';
import { QRHabitacion } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatRoomNumber } from '../utils/format';
import Button from './ui/Button';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';
import { EsqueletoTabla } from './ui/Carga';

type Impresion = 'todos' | number | null;

// QR fijo de cada habitación (migración 020): se imprime una vez y se pega en la habitación. El primer celular que lo
// escanea durante una estadía se queda con ella; los demás ven solo la carta. Si un QR se filtra o se daña, la gerencia
// genera uno nuevo y el impreso deja de servir.
const QRHabitacionesConfig: React.FC<{ motel?: string }> = ({ motel }) => {
  const { toast } = useToast();
  const [qrs, setQrs] = useState<QRHabitacion[] | null>(null);
  const [imprimir, setImprimir] = useState<Impresion>(null);
  const [regenerar, setRegenerar] = useState<QRHabitacion | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const cargar = useCallback(async () => {
    try {
      setQrs(await api.getQRHabitaciones());
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudieron cargar los QR.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Se marca qué imprimir, se deja que React lo pinte y recién ahí se abre el diálogo de impresión.
  useEffect(() => {
    if (imprimir === null) return;
    const listo = () => setImprimir(null);
    window.addEventListener('afterprint', listo);
    const abrir = setTimeout(() => window.print(), 50);
    return () => {
      clearTimeout(abrir);
      window.removeEventListener('afterprint', listo);
    };
  }, [imprimir]);

  // El mismo enlace que lleva el QR impreso, para probarlo desde una computadora. Abrirlo acá, con la sesión de la
  // gerencia, no tiene sentido: se copia para abrirlo en otro navegador o en una ventana de incógnito.
  const copiar = async (q: QRHabitacion) => {
    try {
      await navigator.clipboard.writeText(q.direccion);
      toast(`Enlace de la ${formatRoomNumber(q.numero).toLowerCase()} copiado.`, 'success');
    } catch {
      toast('No se pudo copiar el enlace.', 'error');
    }
  };

  const confirmarRegenerar = async () => {
    if (!regenerar) return;
    setOcupado(true);
    try {
      const nuevo = await api.regenerarQR(regenerar.id);
      setQrs((actuales) => actuales?.map((q) => (q.id === nuevo.id ? nuevo : q)) ?? null);
      toast(`QR nuevo para la ${formatRoomNumber(nuevo.numero).toLowerCase()}. Imprimilo y reemplazá el viejo.`, 'success');
      setRegenerar(null);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo generar el QR nuevo.'), 'error');
    } finally {
      setOcupado(false);
    }
  };

  if (qrs === null) return <EsqueletoTabla etiqueta="Cargando los QR…" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-2xl text-sm text-muted">
          <p>
            Imprimilos una vez y pegá cada uno en su habitación. Con el QR, el cliente ve su tiempo y su cuenta y pide sin
            llamar, sin ticket y sin pasar por la ventanilla.
          </p>
          <p className="mt-1">
            El primer celular que lo escanea durante la estadía se queda con ella; desde ese celular se suman los demás. Quien
            lo escanee después, o con una foto vieja, ve solo la carta.
          </p>
        </div>
        <Button onClick={() => setImprimir('todos')} disabled={qrs.length === 0}>
          <Printer className="h-4 w-4" aria-hidden="true" />
          Imprimir todos
        </Button>
      </div>

      {qrs.length === 0 ? (
        <p className="rounded-md bg-surface-2 px-3 py-6 text-center text-sm text-muted">No hay habitaciones activas.</p>
      ) : (
        <ul {...(imprimir === 'todos' ? { 'data-print-area': '' } : {})} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {qrs.map((q) => (
            <li
              key={q.id}
              data-qr-tarjeta
              {...(imprimir === q.id ? { 'data-print-area': '' } : {})}
              className="flex flex-col items-center rounded-lg border border-line bg-surface p-3 text-center"
            >
              {motel && <p className="text-xs font-medium uppercase tracking-wider text-muted">{motel}</p>}
              <p className="text-base font-semibold text-ink">{formatRoomNumber(q.numero)}</p>
              <img src={q.qr} alt={`QR de la ${formatRoomNumber(q.numero).toLowerCase()}`} className="mt-2 aspect-square w-full max-w-[11rem] rounded-md bg-white p-1" />
              <p className="mt-2 text-xs text-ink">Escaneá para ver tu tiempo y tu cuenta, y pedir sin llamar.</p>
              <p className="text-[11px] text-muted">Sin cuenta ni datos personales.</p>
              <div data-no-print className="mt-2 flex w-full flex-wrap justify-center gap-1.5 border-t border-line pt-2">
                <button type="button" onClick={() => setImprimir(q.id)} className="press flex items-center gap-1 rounded px-2 py-1 text-xs text-muted hover:text-ink">
                  <Printer className="h-3.5 w-3.5" aria-hidden="true" />
                  Imprimir
                </button>
                <button type="button" onClick={() => void copiar(q)} className="press flex items-center gap-1 rounded px-2 py-1 text-xs text-muted hover:text-ink">
                  <Link2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Copiar enlace
                </button>
                <button type="button" onClick={() => setRegenerar(q)} className="press flex items-center gap-1 rounded px-2 py-1 text-xs text-muted hover:text-danger">
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  QR nuevo
                </button>
              </div>
              {q.version > 1 && <p data-no-print className="mt-1 text-[11px] text-subtle">Versión {q.version}</p>}
            </li>
          ))}
        </ul>
      )}

      {regenerar && (
        <Modal
          title={`QR nuevo para la ${formatRoomNumber(regenerar.numero).toLowerCase()}`}
          onClose={() => setRegenerar(null)}
          footer={
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setRegenerar(null)}>
                Cancelar
              </Button>
              <Button variant="danger" disabled={ocupado} onClick={() => void confirmarRegenerar()}>
                Generar QR nuevo
              </Button>
            </div>
          }
        >
          <p className="text-sm text-ink">
            El QR pegado ahora en la habitación deja de servir apenas lo confirmes: hay que imprimir el nuevo y reemplazarlo.
            Usalo si el QR se dañó o si se filtró una foto. Los celulares que ya están viendo su estadía no se cortan.
          </p>
        </Modal>
      )}
    </div>
  );
};

export default QRHabitacionesConfig;
