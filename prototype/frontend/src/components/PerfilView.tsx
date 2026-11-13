import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, CalendarDays, Eye, EyeOff, KeyRound, LogIn, LogOut, Monitor, Moon, Palette, Sun, UserRound } from 'lucide-react';
import { Perfil } from '../types';
import { api, getErrorMessage } from '../services/api';
import { parseUtc } from '../utils/format';
import { alCambiarTema, elegirTema, leerPreferencia, Preferencia } from '../utils/tema';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import { useToast } from './ui/Toast';
import { Avatar } from './TopNav';

const campo = `${inputClass} h-11`;
// En el celular los botones de cada tarjeta van a lo ancho, como en una app.
const boton = 'h-11 max-sm:w-full';
const soloFecha = new Intl.DateTimeFormat('es-AR', { dateStyle: 'short' });
const fechaYHora = new Intl.DateTimeFormat('es-AR', { dateStyle: 'short', timeStyle: 'short', hourCycle: 'h23' });
const LARGO_MINIMO = 10;

const ROL: Record<string, string> = { OPERADOR: 'Conserje', ADMINISTRADOR: 'Gerencia', PLATAFORMA: 'Plataforma' };

// Fortaleza orientativa de la clave: largo y variedad de caracteres. La regla que se exige es solo el largo mínimo.
const fortaleza = (clave: string): { puntos: number; texto: string; color: string } => {
  if (!clave) return { puntos: 0, texto: '', color: 'bg-line' };
  let puntos = clave.length >= LARGO_MINIMO ? 1 : 0;
  if (clave.length >= 14) puntos += 1;
  if (/[a-z]/.test(clave) && /[A-Z]/.test(clave)) puntos += 1;
  if (/\d/.test(clave) && /[^A-Za-z0-9]/.test(clave)) puntos += 1;
  const escala = [
    { texto: 'Muy corta', color: 'bg-danger' },
    { texto: 'Aceptable', color: 'bg-warn' },
    { texto: 'Buena', color: 'bg-warn' },
    { texto: 'Fuerte', color: 'bg-libre' },
    { texto: 'Muy fuerte', color: 'bg-libre' },
  ];
  return { puntos, ...escala[puntos] };
};

interface PerfilViewProps {
  onPerfilActualizado: () => Promise<void> | void;
  onSalir: () => void;
}

// Mi perfil: datos de la cuenta, nombre visible, clave propia y preferencias del puesto (tema).
const PerfilView: React.FC<PerfilViewProps> = ({ onPerfilActualizado, onSalir }) => {
  const { toast } = useToast();
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [nombre, setNombre] = useState('');
  const [clave, setClave] = useState({ actual: '', nueva: '', repetir: '' });
  const [verClaves, setVerClaves] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [tema, setTema] = useState<Preferencia>(leerPreferencia);

  const cargar = useCallback(async () => {
    try {
      const datos = await api.getPerfil();
      setPerfil(datos);
      setNombre(datos.nombre_visible);
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo cargar el perfil.'), 'error');
    }
  }, [toast]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  useEffect(() => alCambiarTema((_modo, preferencia) => setTema(preferencia)), []);

  const guardarNombre = async (e: React.FormEvent) => {
    e.preventDefault();
    setOcupado(true);
    try {
      setPerfil(await api.setNombreVisible(nombre));
      toast('Nombre visible actualizado.', 'success');
      await onPerfilActualizado();
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo cambiar el nombre.'), 'error');
    } finally {
      setOcupado(false);
    }
  };

  const nivel = useMemo(() => fortaleza(clave.nueva), [clave.nueva]);
  const coinciden = clave.nueva === clave.repetir;
  const claveValida = clave.actual && clave.nueva.length >= LARGO_MINIMO && coinciden && clave.nueva !== clave.actual;

  const cambiarClave = async (e: React.FormEvent) => {
    e.preventDefault();
    setOcupado(true);
    try {
      await api.cambiarClave(clave.actual, clave.nueva);
      setClave({ actual: '', nueva: '', repetir: '' });
      toast('Clave cambiada. La sesión sigue abierta; la próxima vez ingrese con la clave nueva.', 'success');
    } catch (err) {
      toast(getErrorMessage(err, 'No se pudo cambiar la clave.'), 'error');
    } finally {
      setOcupado(false);
    }
  };

  const setCampoClave = (k: keyof typeof clave) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setClave((prev) => ({ ...prev, [k]: e.target.value }));

  if (!perfil) return <p className="py-16 text-center text-sm text-muted">Cargando perfil…</p>;

  const tipoClave = verClaves ? 'text' : 'password';

  return (
    <div className="mx-auto w-full max-w-5xl animate-fade-in">
      {/* En el celular, una cabecera centrada como la de una app; en pantallas grandes, en fila. */}
      <section className="mb-4 rounded-lg border border-line bg-surface p-4 sm:mb-5 sm:p-6">
        <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:items-center sm:gap-5 sm:text-left">
          <Avatar nombre={perfil.nombre_visible} grande />
          <div className="min-w-0 max-w-full flex-1">
            <h1 className="break-words text-lg font-semibold leading-tight text-ink sm:text-xl">{perfil.nombre_visible}</h1>
            <div className="mt-1.5 flex flex-wrap items-center justify-center gap-1.5 text-xs sm:justify-start">
              <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">{ROL[perfil.rol]}</span>
              <span className="rounded-full bg-surface-2 px-2 py-0.5 font-mono text-muted">@{perfil.usuario}</span>
              {perfil.establecimiento_nombre && (
                <span className="flex min-w-0 max-w-full items-center gap-1 rounded-full bg-surface-2 px-2 py-0.5 text-muted">
                  <Building2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                  <span className="truncate">{perfil.establecimiento_nombre}</span>
                </span>
              )}
            </div>
            <dl className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-0.5 text-xs text-subtle sm:justify-start">
              <div className="flex items-center gap-1">
                <CalendarDays className="h-3 w-3" aria-hidden="true" />
                <dt>Desde</dt>
                <dd className="tabular-nums">{soloFecha.format(parseUtc(perfil.creado_en))}</dd>
              </div>
              {perfil.ultimo_acceso && (
                <div className="flex items-center gap-1">
                  <LogIn className="h-3 w-3" aria-hidden="true" />
                  <dt>Último ingreso</dt>
                  <dd className="tabular-nums">{fechaYHora.format(parseUtc(perfil.ultimo_acceso))}</dd>
                </div>
              )}
            </dl>
          </div>
        </div>
        {perfil.rol === 'OPERADOR' && (
          <div className="mt-4 border-t border-line pt-3">
            <dl className="grid grid-cols-3 divide-x divide-line text-center">
              <Cifra titulo="Guardias" valor={perfil.guardias_30_dias} />
              <Cifra titulo="Turnos" valor={perfil.turnos_30_dias} />
              <Cifra titulo="Arqueos" valor={perfil.arqueos_30_dias} />
            </dl>
            <p className="mt-2 text-center text-[11px] text-subtle">Últimos 30 días</p>
          </div>
        )}
      </section>

      <div className="grid gap-4 sm:gap-5 lg:grid-cols-2">
        <form onSubmit={guardarNombre} className="space-y-4 rounded-lg border border-line bg-surface p-4 sm:p-5">
          <Titulo icon={UserRound}>Datos de la cuenta</Titulo>
          <Field label="Nombre visible" htmlFor="perfil_nombre" hint="Es el nombre que figura en turnos, cobros, arqueos y en el registro.">
            <input id="perfil_nombre" required maxLength={60} className={campo} value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Usuario" htmlFor="perfil_usuario" hint="El usuario no cambia: identifica a la persona en toda la historia.">
            <input id="perfil_usuario" disabled className={`${campo} font-mono opacity-70`} value={perfil.usuario} />
          </Field>
          <Button type="submit" className={boton} disabled={ocupado || !nombre.trim() || nombre.trim() === perfil.nombre_visible}>
            Guardar nombre
          </Button>
        </form>

        <form onSubmit={cambiarClave} className="space-y-4 rounded-lg border border-line bg-surface p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2">
            <Titulo icon={KeyRound}>Cambiar la clave</Titulo>
            <button
              type="button"
              onClick={() => setVerClaves((v) => !v)}
              className="press hit flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted hover:text-ink"
              aria-pressed={verClaves}
            >
              {verClaves ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
              {verClaves ? 'Ocultar' : 'Mostrar'}
            </button>
          </div>
          <Field label="Clave actual" htmlFor="clave_actual">
            <input id="clave_actual" type={tipoClave} autoComplete="current-password" required className={campo} value={clave.actual} onChange={setCampoClave('actual')} />
          </Field>
          <Field label="Clave nueva" htmlFor="clave_nueva" hint={`Al menos ${LARGO_MINIMO} caracteres.`}>
            <input id="clave_nueva" type={tipoClave} autoComplete="new-password" required minLength={LARGO_MINIMO} className={campo} value={clave.nueva} onChange={setCampoClave('nueva')} />
          </Field>
          {clave.nueva && (
            <div aria-live="polite">
              <div className="flex gap-1">
                {[1, 2, 3, 4].map((n) => (
                  <span key={n} className={`h-1.5 flex-1 rounded-full transition-colors ${n <= nivel.puntos ? nivel.color : 'bg-line'}`} />
                ))}
              </div>
              <p className="mt-1 text-xs text-muted">{nivel.texto}</p>
            </div>
          )}
          <Field
            label="Repetir la clave nueva"
            htmlFor="clave_repetir"
            error={clave.repetir && !coinciden ? 'Las claves no coinciden.' : undefined}
          >
            <input id="clave_repetir" type={tipoClave} autoComplete="new-password" required className={campo} value={clave.repetir} onChange={setCampoClave('repetir')} />
          </Field>
          <Button type="submit" className={boton} disabled={ocupado || !claveValida}>
            Cambiar clave
          </Button>
        </form>

        <section className="space-y-4 rounded-lg border border-line bg-surface p-4 sm:p-5">
          <Titulo icon={Palette}>Apariencia de este puesto</Titulo>
          <div role="radiogroup" aria-label="Tema" className="grid grid-cols-3 gap-2">
            {(
              [
                { id: 'claro', label: 'Claro', icon: Sun },
                { id: 'oscuro', label: 'Oscuro', icon: Moon },
                { id: 'sistema', label: 'Según el sistema', corta: 'Sistema', icon: Monitor },
              ] as { id: Preferencia; label: string; corta?: string; icon: React.ElementType }[]
            ).map(({ id, label, corta, icon: Icon }) => (
              <button
                key={id}
                type="button"
                role="radio"
                aria-checked={tema === id}
                onClick={(e) => {
                  const caja = e.currentTarget.getBoundingClientRect();
                  elegirTema(id, { x: caja.left + caja.width / 2, y: caja.top + caja.height / 2 });
                  setTema(id);
                }}
                aria-label={label}
                className={`press flex h-16 flex-col items-center justify-center gap-1 rounded-md border text-sm sm:h-20 sm:gap-1.5 ${
                  tema === id ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong bg-surface text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                {corta ? (
                  <>
                    <span className="sm:hidden">{corta}</span>
                    <span className="max-sm:hidden">{label}</span>
                  </>
                ) : (
                  label
                )}
              </button>
            ))}
          </div>
          <p className="text-xs text-subtle">
            La preferencia queda guardada en este navegador: la ventanilla la comparte cada guardia.
          </p>
        </section>

        <section className="space-y-4 rounded-lg border border-line bg-surface p-4 sm:p-5">
          <Titulo icon={LogOut}>Sesión</Titulo>
          <p className="text-sm text-muted">
            La sesión dura una guardia (8 h) más una hora de margen y se cierra al salir. Si la gerencia da de baja la cuenta,
            la sesión se corta en el acto.
          </p>
          <Button variant="secondary" className={boton} onClick={onSalir}>
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Cerrar sesión
          </Button>
        </section>
      </div>
    </div>
  );
};

const Titulo: React.FC<{ icon: React.ElementType; children: React.ReactNode }> = ({ icon: Icon, children }) => (
  <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
    <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
    {children}
  </h2>
);

const Cifra: React.FC<{ titulo: string; valor: number }> = ({ titulo, valor }) => (
  <div className="flex flex-col-reverse px-1">
    <dt className="truncate text-xs text-muted">{titulo}</dt>
    <dd className="text-xl font-semibold tabular-nums text-ink sm:text-2xl">{valor}</dd>
  </div>
);

export default PerfilView;
