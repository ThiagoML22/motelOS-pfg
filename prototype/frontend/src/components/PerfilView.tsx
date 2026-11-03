import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Eye, EyeOff, KeyRound, LogOut, Monitor, Moon, Palette, Sun, UserRound } from 'lucide-react';
import { Perfil } from '../types';
import { api, getErrorMessage } from '../services/api';
import { formatDateTime } from '../utils/format';
import { alCambiarTema, elegirTema, leerPreferencia, Preferencia } from '../utils/tema';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import { useToast } from './ui/Toast';
import { Avatar } from './TopNav';

const campo = `${inputClass} h-11`;
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
      <section className="mb-5 flex flex-wrap items-center gap-5 rounded-lg border border-line bg-surface p-6">
        <Avatar nombre={perfil.nombre_visible} grande />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold text-ink">{perfil.nombre_visible}</h1>
          <p className="mt-0.5 text-sm text-muted">
            <span className="font-mono">@{perfil.usuario}</span> ·{' '}
            <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent">{ROL[perfil.rol]}</span>
            {perfil.establecimiento_nombre && (
              <>
                {' '}
                · {perfil.establecimiento_nombre} <span className="font-mono text-subtle">({perfil.establecimiento_codigo})</span>
              </>
            )}
          </p>
          <p className="mt-1 text-xs text-subtle">
            En el sistema desde {formatDateTime(perfil.creado_en)}
            {perfil.ultimo_acceso && <> · último ingreso {formatDateTime(perfil.ultimo_acceso)}</>}
          </p>
        </div>
        {perfil.rol === 'OPERADOR' && (
          <dl className="grid grid-cols-3 gap-4 text-center">
            <Cifra titulo="Guardias" valor={perfil.guardias_30_dias} />
            <Cifra titulo="Turnos abiertos" valor={perfil.turnos_30_dias} />
            <Cifra titulo="Arqueos" valor={perfil.arqueos_30_dias} />
            <p className="col-span-3 -mt-2 text-xs text-subtle">Últimos 30 días</p>
          </dl>
        )}
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <form onSubmit={guardarNombre} className="space-y-4 rounded-lg border border-line bg-surface p-5">
          <Titulo icon={UserRound}>Datos de la cuenta</Titulo>
          <Field label="Nombre visible" htmlFor="perfil_nombre" hint="Es el nombre que figura en turnos, cobros, arqueos y en el registro.">
            <input id="perfil_nombre" required maxLength={60} className={campo} value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Usuario" htmlFor="perfil_usuario" hint="El usuario no cambia: identifica a la persona en toda la historia.">
            <input id="perfil_usuario" disabled className={`${campo} font-mono opacity-70`} value={perfil.usuario} />
          </Field>
          <Button type="submit" className="h-11" disabled={ocupado || !nombre.trim() || nombre.trim() === perfil.nombre_visible}>
            Guardar nombre
          </Button>
        </form>

        <form onSubmit={cambiarClave} className="space-y-4 rounded-lg border border-line bg-surface p-5">
          <div className="flex items-center justify-between">
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
          <Button type="submit" className="h-11" disabled={ocupado || !claveValida}>
            Cambiar clave
          </Button>
        </form>

        <section className="space-y-4 rounded-lg border border-line bg-surface p-5">
          <Titulo icon={Palette}>Apariencia de este puesto</Titulo>
          <div role="radiogroup" aria-label="Tema" className="grid grid-cols-3 gap-2">
            {(
              [
                { id: 'claro', label: 'Claro', icon: Sun },
                { id: 'oscuro', label: 'Oscuro', icon: Moon },
                { id: 'sistema', label: 'Según el sistema', icon: Monitor },
              ] as { id: Preferencia; label: string; icon: React.ElementType }[]
            ).map(({ id, label, icon: Icon }) => (
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
                className={`press flex h-20 flex-col items-center justify-center gap-1.5 rounded-md border text-sm ${
                  tema === id ? 'border-accent bg-accent-soft font-medium text-accent' : 'border-line-strong bg-surface text-muted hover:text-ink'
                }`}
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                {label}
              </button>
            ))}
          </div>
          <p className="text-xs text-subtle">
            La preferencia queda guardada en este navegador: la ventanilla la comparte cada guardia.
          </p>
        </section>

        <section className="space-y-4 rounded-lg border border-line bg-surface p-5">
          <Titulo icon={LogOut}>Sesión</Titulo>
          <p className="text-sm text-muted">
            La sesión dura una guardia (8 h) más una hora de margen y se cierra al salir. Si la gerencia da de baja la cuenta,
            la sesión se corta en el acto.
          </p>
          <Button variant="secondary" className="h-11" onClick={onSalir}>
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
  <div>
    <dd className="text-2xl font-semibold tabular-nums text-ink">{valor}</dd>
    <dt className="text-xs text-muted">{titulo}</dt>
  </div>
);

export default PerfilView;
