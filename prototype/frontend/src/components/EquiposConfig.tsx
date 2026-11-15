import React, { useCallback, useEffect, useState } from 'react';
import { Ban, Check, Globe, KeyRound, Monitor, MonitorSmartphone, ShieldAlert, ShieldCheck, Smartphone, Wifi } from 'lucide-react';
import { EquipoVentanilla, IntentoAcceso, PanelEquipos } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';
import { EsqueletoTabla } from './ui/Carga';

const campo = `${inputClass} h-11`;

const esCelular = (descripcion: string) => /celular|tableta/.test(descripcion);

const IconoEquipo: React.FC<{ descripcion: string; className?: string }> = ({ descripcion, className = 'h-5 w-5' }) => {
  const Icono = esCelular(descripcion) ? Smartphone : Monitor;
  return <Icono className={className} aria-hidden="true" />;
};

const ESTADOS: Record<EquipoVentanilla['estado'], { etiqueta: string; clase: string }> = {
  PENDIENTE: { etiqueta: 'Esperando tu decisión', clase: 'bg-warn-soft text-warn' },
  AUTORIZADO: { etiqueta: 'Autorizado', clase: 'bg-libre-soft text-libre' },
  BLOQUEADO: { etiqueta: 'Bloqueado', clase: 'bg-danger-soft text-danger' },
};

interface Confirmar {
  titulo: string;
  texto: string;
  accion: () => Promise<void>;
}

// Equipos autorizados (migración 019): desde qué equipos entra el conserje y quién intentó entrar desde otros. La
// gerencia entra desde donde quiera. Cada equipo se reconoce por una marca propia del navegador (una cookie que la
// página no puede leer), no por la IP: en el Wi-Fi del motel el celular tendría una IP de la misma red.
const EquiposConfig: React.FC = () => {
  const { toast } = useToast();
  const [panel, setPanel] = useState<PanelEquipos | null>(null);
  const [error, setError] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [autorizando, setAutorizando] = useState<EquipoVentanilla | 'este' | null>(null);
  const [nombre, setNombre] = useState('');
  const [confirmar, setConfirmar] = useState<Confirmar | null>(null);
  const [redes, setRedes] = useState('');

  const cargar = useCallback(async () => {
    try {
      const datos = await api.getEquipos();
      setPanel(datos);
      setRedes(datos.redes ?? '');
      setError(false);
    } catch (err) {
      setError(true);
      toast(getErrorMessage(err, 'No se pudieron traer los equipos.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
    // Un conserje puede intentar entrar mientras la gerencia mira el panel.
    const sondeo = setInterval(() => void cargar(), 15000);
    return () => clearInterval(sondeo);
  }, [cargar]);

  const ejecutar = async (accion: () => Promise<unknown>, exito: string, falla: string): Promise<boolean> => {
    setOcupado(true);
    try {
      await accion();
      toast(exito, 'success');
      await cargar();
      return true;
    } catch (err) {
      toast(getErrorMessage(err, falla), 'error');
      return false;
    } finally {
      setOcupado(false);
    }
  };

  if (error && !panel) {
    return (
      <div className="flex flex-col items-center gap-3 py-12">
        <p className="text-sm text-muted">No se pudieron traer los equipos.</p>
        <Button variant="secondary" onClick={() => void cargar()}>
          Reintentar
        </Button>
      </div>
    );
  }
  if (!panel) return <EsqueletoTabla etiqueta="Cargando equipos…" />;

  const autorizados = panel.equipos.filter((e) => e.estado === 'AUTORIZADO');
  const pendientes = panel.equipos.filter((e) => e.estado === 'PENDIENTE');
  const bloqueados = panel.equipos.filter((e) => e.estado === 'BLOQUEADO');
  const este = panel.equipos.find((e) => e.id === panel.este_equipo_id);

  const abrirAutorizar = (equipo: EquipoVentanilla | 'este') => {
    setNombre(equipo === 'este' ? 'PC Ventanilla' : equipo.nombre ?? (esCelular(equipo.descripcion) ? '' : 'PC Ventanilla'));
    setAutorizando(equipo);
  };

  const autorizar = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!autorizando) return;
    const ok = await ejecutar(
      () => (autorizando === 'este' ? api.autorizarEsteEquipo(nombre) : api.autorizarEquipo(autorizando.id, nombre)),
      `«${nombre.trim()}» autorizado: desde ahí pueden entrar los conserjes.`,
      'No se pudo autorizar el equipo.',
    );
    if (ok) setAutorizando(null);
  };

  const bloquear = (equipo: EquipoVentanilla) =>
    setConfirmar({
      titulo: equipo.estado === 'AUTORIZADO' ? 'Quitar la autorización' : 'Bloquear el equipo',
      texto:
        equipo.estado === 'AUTORIZADO'
          ? `Desde «${equipo.nombre}» ya no van a poder entrar los conserjes, y si hay una sesión abierta ahí se corta ahora.`
          : `Desde ${equipo.descripcion} no van a poder entrar los conserjes. Si fue un error, después lo podés autorizar.`,
      accion: async () => {
        await ejecutar(() => api.bloquearEquipo(equipo.id), 'Equipo bloqueado.', 'No se pudo bloquear el equipo.');
      },
    });

  const cambiarControl = (control: boolean) =>
    void ejecutar(
      () => api.ajustesEquipos({ control }),
      control ? 'Listo: el conserje entra solo desde los equipos autorizados.' : 'El conserje puede entrar desde cualquier equipo.',
      'No se pudo cambiar el control de equipos.',
    );

  const guardarRedes = (e: React.FormEvent) => {
    e.preventDefault();
    void ejecutar(
      () => api.ajustesEquipos({ redes }),
      redes.trim() ? 'Redes guardadas.' : 'Sin restricción de red.',
      'No se pudieron guardar las redes.',
    );
  };

  return (
    <div className="space-y-6">
      {/* El control */}
      <div className="flex flex-col gap-3 rounded-lg border border-line p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-full ${panel.control ? 'bg-libre-soft text-libre' : 'bg-surface-2 text-muted'}`}>
            {panel.control ? <ShieldCheck className="h-5 w-5" aria-hidden="true" /> : <MonitorSmartphone className="h-5 w-5" aria-hidden="true" />}
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-ink">¿Desde dónde entra el conserje?</h2>
            <p className="mt-0.5 text-sm text-muted">
              {panel.control
                ? `Solo desde ${autorizados.length === 1 ? 'el equipo autorizado' : `los ${autorizados.length} equipos autorizados`}. Si intenta desde otro, no entra y te avisamos.`
                : 'Desde cualquier equipo. Los equipos que usa quedan anotados abajo para que los autorices antes de activar el control.'}{' '}
              La gerencia entra desde donde quiera.
            </p>
          </div>
        </div>
        <div role="radiogroup" aria-label="Desde dónde entra el conserje" className="grid shrink-0 grid-cols-2 rounded-md border border-line-strong p-0.5">
          {[
            { valor: false, label: 'Cualquier equipo' },
            { valor: true, label: 'Solo autorizados' },
          ].map(({ valor, label }) => (
            <button
              key={label}
              type="button"
              role="radio"
              aria-checked={panel.control === valor}
              disabled={ocupado || panel.control === valor}
              onClick={() => cambiarControl(valor)}
              className={`press hit flex h-9 items-center justify-center whitespace-nowrap rounded px-3.5 text-sm ${
                panel.control === valor ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {!panel.control && autorizados.length === 0 && (
        <p className="-mt-3 text-xs text-muted">Para activarlo, primero autorizá al menos un equipo (la PC de la ventanilla).</p>
      )}

      {/* Este equipo */}
      <div className="flex flex-col gap-3 rounded-lg border border-dashed border-line-strong p-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink">
          {este?.estado === 'AUTORIZADO' ? (
            <>
              <Check className="mr-1.5 inline h-4 w-4 text-libre" aria-hidden="true" />
              Este equipo está autorizado como <span className="font-medium">«{este.nombre}»</span>.
            </>
          ) : (
            <>
              ¿Estás en la PC de la ventanilla? <span className="text-muted">Autorizala desde acá, sin que el conserje tenga que intentar entrar.</span>
            </>
          )}
        </p>
        {este?.estado !== 'AUTORIZADO' && (
          <Button variant="secondary" className="h-11 shrink-0" disabled={ocupado} onClick={() => abrirAutorizar('este')}>
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Autorizar este equipo
          </Button>
        )}
      </div>

      {/* Pendientes */}
      {pendientes.length > 0 && (
        <section aria-labelledby="eq-pendientes">
          <h3 id="eq-pendientes" className="mb-2 text-sm font-semibold text-ink">
            Esperando tu decisión <span className="font-normal text-muted">· {pendientes.length}</span>
          </h3>
          <ul className="space-y-2">
            {pendientes.map((e) => (
              <FilaEquipo key={e.id} equipo={e} esEste={e.id === panel.este_equipo_id}>
                <Button className="h-11" disabled={ocupado} onClick={() => abrirAutorizar(e)}>
                  Autorizar
                </Button>
                <Button variant="ghost" className="h-11" disabled={ocupado} onClick={() => bloquear(e)}>
                  Bloquear
                </Button>
              </FilaEquipo>
            ))}
          </ul>
        </section>
      )}

      {/* Autorizados */}
      <section aria-labelledby="eq-autorizados">
        <h3 id="eq-autorizados" className="mb-2 text-sm font-semibold text-ink">
          Autorizados <span className="font-normal text-muted">· {autorizados.length}</span>
        </h3>
        {autorizados.length === 0 ? (
          <p className="rounded-md border border-line px-4 py-3 text-sm text-muted">Todavía no autorizaste ningún equipo.</p>
        ) : (
          <ul className="space-y-2">
            {autorizados.map((e) => (
              <FilaEquipo key={e.id} equipo={e} esEste={e.id === panel.este_equipo_id}>
                <Button variant="ghost" className="h-11" disabled={ocupado} onClick={() => bloquear(e)}>
                  Quitar autorización
                </Button>
              </FilaEquipo>
            ))}
          </ul>
        )}
      </section>

      {/* Intentos */}
      <section aria-labelledby="eq-intentos">
        <h3 id="eq-intentos" className="mb-2 text-sm font-semibold text-ink">
          Intentos de entrar desde otros equipos <span className="font-normal text-muted">· últimos 30 días</span>
        </h3>
        {panel.intentos.length === 0 ? (
          <p className="rounded-md border border-line px-4 py-3 text-sm text-muted">Nadie intentó entrar desde un equipo no autorizado.</p>
        ) : (
          <table className="tabla-movil sin-margen w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="py-2 font-medium">Cuándo</th>
                <th className="py-2 font-medium">Quién</th>
                <th className="py-2 font-medium">Clave</th>
                <th className="py-2 font-medium">Desde</th>
                <th className="py-2 font-medium">Equipo</th>
              </tr>
            </thead>
            <tbody>
              {panel.intentos.map((i) => (
                <FilaIntento key={i.id} intento={i} />
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Red */}
      <form onSubmit={guardarRedes} className="space-y-3 rounded-lg border border-line p-4">
        <div className="flex items-start gap-3">
          <Wifi className="mt-0.5 h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
          <div>
            <h3 className="text-sm font-semibold text-ink">Red de la ventanilla (opcional)</h3>
            <p className="mt-0.5 text-sm text-muted">
              Además del equipo, el conserje tiene que estar en una de estas redes. Sirve si el Wi-Fi de los clientes es otra
              red; si es la misma, no agrega nada.
            </p>
          </div>
        </div>
        <Field
          label="Redes"
          htmlFor="redes"
          hint={`Separadas por comas. Ejemplo: 192.168.0.0/24. Vacío: sin restricción.${panel.ip_actual ? ` Tu IP ahora: ${panel.ip_actual}.` : ''}`}
        >
          <input id="redes" className={campo} value={redes} maxLength={200} placeholder="192.168.0.0/24" onChange={(e) => setRedes(e.target.value)} />
        </Field>
        <Button type="submit" variant="secondary" className="h-11" disabled={ocupado || redes.trim() === (panel.redes ?? '')}>
          Guardar redes
        </Button>
      </form>

      {/* Bloqueados */}
      {bloqueados.length > 0 && (
        <details className="group rounded-lg border border-line">
          <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-ink">
            Bloqueados <span className="font-normal text-muted">· {bloqueados.length}</span>
          </summary>
          <ul className="space-y-2 px-4 pb-4">
            {bloqueados.map((e) => (
              <FilaEquipo key={e.id} equipo={e} esEste={e.id === panel.este_equipo_id}>
                <Button variant="secondary" className="h-11" disabled={ocupado} onClick={() => abrirAutorizar(e)}>
                  Autorizar
                </Button>
              </FilaEquipo>
            ))}
          </ul>
        </details>
      )}

      <p className="flex items-start gap-2 text-xs text-muted">
        <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Cada equipo se reconoce por una marca propia de su navegador, no por la IP. Si se borran los datos del navegador, el
        equipo aparece como nuevo y hay que autorizarlo otra vez. Los intentos se borran a los 90 días.
      </p>

      {autorizando && (
        <Modal
          title={autorizando === 'este' ? 'Autorizar este equipo' : 'Autorizar el equipo'}
          subtitle={autorizando === 'este' ? 'El equipo desde el que estás ahora' : `${autorizando.descripcion}${autorizando.ultima_ip ? ` · IP ${autorizando.ultima_ip}` : ''}`}
          onClose={() => setAutorizando(null)}
        >
          <form onSubmit={autorizar} className="space-y-4">
            {autorizando !== 'este' && esCelular(autorizando.descripcion) && (
              <p className="flex items-start gap-2 rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                Es un celular. Autorizalo solo si de verdad se usa para atender la ventanilla.
              </p>
            )}
            <Field label="Nombre del equipo" htmlFor="nombre_equipo" hint="Para reconocerlo en la lista, como «PC Ventanilla».">
              <input id="nombre_equipo" data-autofocus required maxLength={40} className={campo} value={nombre} onChange={(e) => setNombre(e.target.value)} />
            </Field>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" className="h-11" onClick={() => setAutorizando(null)}>
                Cancelar
              </Button>
              <Button type="submit" className="h-11" disabled={ocupado || !nombre.trim()}>
                Autorizar
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {confirmar && (
        <Modal
          title={confirmar.titulo}
          onClose={() => setConfirmar(null)}
          footer={
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setConfirmar(null)}>
                Cancelar
              </Button>
              <Button
                variant="danger"
                disabled={ocupado}
                onClick={async () => {
                  await confirmar.accion();
                  setConfirmar(null);
                }}
              >
                Confirmar
              </Button>
            </div>
          }
        >
          <p className="text-sm text-ink">{confirmar.texto}</p>
        </Modal>
      )}
    </div>
  );
};

const FilaEquipo: React.FC<{ equipo: EquipoVentanilla; esEste: boolean; children: React.ReactNode }> = ({ equipo: e, esEste, children }) => {
  const estado = ESTADOS[e.estado];
  return (
    <li className="flex flex-col gap-3 rounded-md border border-line p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        <span className="relative grid h-10 w-10 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
          <IconoEquipo descripcion={e.descripcion} />
          {e.en_uso && (
            <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full bg-libre ring-2 ring-surface" title="En uso ahora" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-ink">
            {e.nombre ?? e.descripcion}
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${estado.clase}`}>{estado.etiqueta}</span>
            {e.en_uso && <span className="text-xs font-normal text-libre">En uso ahora</span>}
            {esEste && <span className="text-xs font-normal text-muted">(este equipo)</span>}
          </p>
          <p className="mt-0.5 text-xs text-muted">
            {e.nombre && <>{e.descripcion} · </>}
            {e.ultimo_uso ? `Último uso ${formatDateTime(e.ultimo_uso)}` : `Visto por primera vez ${formatDateTime(e.creado_en)}`}
            {e.ultimo_operador && <> por {e.ultimo_operador}</>}
            {e.ultima_ip && <> · IP {e.ultima_ip}</>}
          </p>
          {e.decidido_por && e.decidido_en && (
            <p className="text-xs text-subtle">
              {e.estado === 'AUTORIZADO' ? 'Autorizado' : 'Bloqueado'} por {e.decidido_por} el {formatDateTime(e.decidido_en)}
            </p>
          )}
        </div>
      </div>
      <div className="flex shrink-0 justify-end gap-2">{children}</div>
    </li>
  );
};

const FilaIntento: React.FC<{ intento: IntentoAcceso }> = ({ intento: i }) => (
  <tr className="border-t border-line">
    <td className="principal py-2 tabular-nums">{formatDateTime(i.creado_en)}</td>
    <td className="py-2" data-etiqueta="Quién">
      {i.operador ? (
        <>
          {i.operador} <span className="font-mono text-xs text-muted">{i.usuario}</span>
        </>
      ) : (
        <span className="text-muted">Usuario que no existe</span>
      )}
    </td>
    <td className="py-2" data-etiqueta="Clave">
      {i.clave_correcta ? (
        <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn" title="Era la persona: sabía la clave">
          Correcta
        </span>
      ) : (
        <span className="rounded-full bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger" title="Alguien probó una clave">
          Equivocada
        </span>
      )}
    </td>
    <td className="py-2" data-etiqueta="Desde">
      <span className="inline-flex items-center gap-1.5">
        {i.motivo === 'RED' ? <Globe className="h-3.5 w-3.5 text-muted" aria-hidden="true" /> : <IconoEquipo descripcion={i.descripcion} className="h-3.5 w-3.5 text-muted" />}
        {i.descripcion}
      </span>
      {i.ip && <span className="block text-xs text-muted">IP {i.ip}{i.motivo === 'RED' && ' · fuera de la red'}</span>}
    </td>
    <td className="py-2" data-etiqueta="Equipo">
      {i.equipo_estado ? (
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${ESTADOS[i.equipo_estado].clase}`}>
          {i.equipo_nombre ?? ESTADOS[i.equipo_estado].etiqueta}
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-xs text-muted">
          <Ban className="h-3.5 w-3.5" aria-hidden="true" />
          Sin registrar
        </span>
      )}
    </td>
  </tr>
);

export default EquiposConfig;
