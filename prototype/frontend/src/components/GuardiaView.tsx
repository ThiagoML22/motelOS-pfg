import React, { useEffect, useState } from 'react';
import { AlertTriangle, DoorOpen, LogOut, NotebookPen, ShieldAlert, Shirt } from 'lucide-react';
import { Novedad, PantallaTraspaso, Sesion } from '../types';
import { ListaNovedades, recientes } from './NovedadesPanel';
import RecuentoRopa, { aConteos, ropaDesde, ropaVacia } from './RecuentoRopa';
import ResumenTraspaso from './ResumenTraspaso';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime, formatMoney } from '../utils/format';
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
  const [novedades, setNovedades] = useState<Novedad[]>([]);
  const [traspaso, setTraspaso] = useState<PantallaTraspaso | null>(null);
  const [ropa, setRopa] = useState(ropaVacia);
  const ajena = sesion.guardia && !sesion.guardia.es_propia ? sesion.guardia : null;
  const porEstado = traspaso?.ropa_por_estado ?? true;
  const conteos = aConteos(ropa, porEstado);

  // Antes de abrir, el conserje lee lo que dejaron las guardias anteriores (migración 009) y ve lo que recibe.
  useEffect(() => {
    api
      .getNovedades(20)
      .then((lista) => setNovedades(recientes(lista)))
      .catch(() => setNovedades([]));
    api
      .getTraspaso()
      .then((pantalla) => {
        setTraspaso(pantalla);
        setRopa(ropaDesde(pantalla.ropa, pantalla.ropa_por_estado));
      })
      .catch(() => setTraspaso(null));
  }, []);

  const abrir = async () => {
    setAbriendo(true);
    try {
      const guardia = await api.abrirGuardia(conteos ?? undefined);
      // Acta del 19/10/2026, punto 5: cada caja empieza con el fondo de cambio, y el conserje lo ve al abrirla.
      const fondo = guardia.fondo_inicial > 0 ? ` con un fondo de cambio de ${formatMoney(guardia.fondo_inicial)}` : '';
      toast(`Guardia ${NOMBRE_FRANJA[guardia.franja] ?? guardia.franja} abierta${fondo}.`, 'success');
      await onGuardiaAbierta();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo abrir la guardia.'), 'error');
      await onGuardiaAbierta();
    } finally {
      setAbriendo(false);
    }
  };

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-5 py-10">
      <div
        className={`w-full animate-pop-in rounded-lg border border-line bg-surface p-6 shadow-lift sm:p-8 ${
          ajena ? 'max-w-lg text-center' : 'max-w-2xl'
        }`}
      >
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
            <div className="flex items-start gap-3">
              <DoorOpen className="mt-0.5 h-7 w-7 shrink-0 text-accent" aria-hidden="true" />
              <div>
                <h1 className="text-lg font-semibold text-ink">Abrir su guardia</h1>
                <p className="mt-1 text-sm text-muted">
                  Hola, {sesion.operador.nombre_visible}. Al abrir la guardia, los turnos, consumos y cobros que registre
                  quedan en su caja, que empieza con el fondo de cambio. Al terminar, hará el cierre de caja ciego: declara
                  lo que cuenta sin ver el total del sistema.
                </p>
              </div>
            </div>

            {traspaso && (
              <section aria-labelledby="titulo-recibe" className="mt-6">
                <h2 id="titulo-recibe" className="text-sm font-semibold text-ink">
                  Lo que recibe
                  {traspaso.saliente && (
                    <span className="font-normal text-muted">
                      {' '}
                      de {traspaso.saliente.operador}, que cerró el {formatDateTime(traspaso.saliente.cerrada_en)}
                    </span>
                  )}
                </h2>
                <ResumenTraspaso foto={traspaso} className="mt-2" />
              </section>
            )}

            <section aria-labelledby="titulo-ropa-recibe" className="mt-6">
              <h2 id="titulo-ropa-recibe" className="flex items-center gap-2 text-sm font-semibold text-ink">
                <Shirt className="h-4 w-4 text-muted" aria-hidden="true" />
                Toallas y sábanas
              </h2>
              {traspaso?.saliente?.sin_conteo && (
                <p className="mt-2 flex items-start gap-2 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  La guardia anterior se cerró sin recuento: estos números son de un recuento más viejo.
                </p>
              )}
              <p className="mt-1 mb-3 text-xs text-muted">
                {traspaso?.ropa?.length
                  ? `Le dejaron esta cantidad, contada por ${traspaso.ropa[0].contado_por}. Cuente toda la ropa del motel y corrija lo que no coincida.`
                  : 'Es el primer recuento: cuente toda la ropa del motel.'}
                {porEstado && ' «En uso» son las que están puestas en las habitaciones.'}
              </p>
              <RecuentoRopa valores={ropa} onCambiar={setRopa} porEstado={porEstado} dejada={traspaso?.ropa} idBase="apertura" />
            </section>

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" onClick={onSalir}>
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Salir
              </Button>
              <Button onClick={() => void abrir()} disabled={abriendo || !conteos} data-autofocus>
                <DoorOpen className="h-4 w-4" aria-hidden="true" />
                {abriendo ? 'Abriendo…' : 'Recibí y abrir guardia'}
              </Button>
            </div>
          </>
        )}
      </div>
      {novedades.length > 0 && (
        <section className={`w-full animate-fade-in ${ajena ? 'max-w-lg' : 'max-w-2xl'}`} aria-labelledby="titulo-novedades-anteriores">
          <h2 id="titulo-novedades-anteriores" className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
            <NotebookPen className="h-4 w-4 text-muted" aria-hidden="true" />
            Lo que dejaron las guardias anteriores
          </h2>
          <ListaNovedades novedades={novedades} />
        </section>
      )}
    </div>
  );
};

export default GuardiaView;
