import React, { useState } from 'react';
import { DoorOpen, LogOut, ShieldAlert } from 'lucide-react';
import { Sesion } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import { NOMBRE_FRANJA } from '../utils/caja';
import Button from './ui/Button';
import { useToast } from './ui/Toast';

interface GuardiaViewProps {
  sesion: Sesion;
  onGuardiaAbierta: () => Promise<void>;
  onSalir: () => void;
}

// Sin guardia propia abierta no se opera la ventanilla: cada cobro tiene que caer en una caja que
// después se arquea (RF-08). Si la guardia abierta es de otro conserje, primero debe cerrarla él.
const GuardiaView: React.FC<GuardiaViewProps> = ({ sesion, onGuardiaAbierta, onSalir }) => {
  const { toast } = useToast();
  const [abriendo, setAbriendo] = useState(false);
  const ajena = sesion.guardia && !sesion.guardia.es_propia ? sesion.guardia : null;

  const abrir = async () => {
    setAbriendo(true);
    try {
      const guardia = await api.abrirGuardia();
      toast(`Guardia ${NOMBRE_FRANJA[guardia.franja] ?? guardia.franja} abierta.`, 'success');
      await onGuardiaAbierta();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo abrir la guardia.'), 'error');
      await onGuardiaAbierta();
    } finally {
      setAbriendo(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="w-full max-w-lg animate-pop-in rounded-lg border border-line bg-surface p-8 text-center shadow-lift">
        {ajena ? (
          <>
            <ShieldAlert className="mx-auto h-10 w-10 text-warn" aria-hidden="true" />
            <h1 className="mt-4 text-lg font-semibold text-ink">La ventanilla tiene una guardia abierta</h1>
            <p className="mt-2 text-sm text-muted">
              La guardia de <span className="font-medium text-ink">{ajena.operador_nombre}</span> está abierta desde el{' '}
              {formatDateTime(ajena.abierta_en)}. Para que usted opere, {ajena.operador_nombre} tiene que cerrarla con su
              arqueo de caja.
            </p>
            <div className="mt-6 flex justify-center">
              <Button variant="secondary" onClick={onSalir}>
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Cerrar sesión
              </Button>
            </div>
          </>
        ) : (
          <>
            <DoorOpen className="mx-auto h-10 w-10 text-accent" aria-hidden="true" />
            <h1 className="mt-4 text-lg font-semibold text-ink">Abrir su guardia</h1>
            <p className="mt-2 text-sm text-muted">
              Hola, {sesion.operador.nombre_visible}. Al abrir la guardia, los turnos, consumos y cobros que registre
              quedan en su caja. Al terminar, hará el cierre de caja ciego: declara lo que cuenta sin ver el total del
              sistema.
            </p>
            <div className="mt-6 flex justify-center gap-3">
              <Button variant="secondary" onClick={onSalir}>
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Salir
              </Button>
              <Button onClick={() => void abrir()} disabled={abriendo} data-autofocus>
                <DoorOpen className="h-4 w-4" aria-hidden="true" />
                {abriendo ? 'Abriendo…' : 'Abrir guardia'}
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default GuardiaView;
