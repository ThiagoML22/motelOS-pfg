import React, { useEffect, useState } from 'react';
import { BrainCircuit, CheckCircle2, Eye, EyeOff, KeyRound, LogIn, Lock, ShieldCheck } from 'lucide-react';
import { MarcaPublica, Sesion } from '../types';
import { api, getErrorMessage } from '../services/api';
import { aplicarMarca } from '../utils/marca';
import { useNow } from '../hooks/useNow';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';
import ThemeToggle from './ui/ThemeToggle';

interface LoginViewProps {
  onIngreso: (sesion: Sesion) => void;
  aviso?: string | null;
}

// Multiinquilino: la ventanilla recuerda el código del último establecimiento (es del puesto, no de la persona).
const CLAVE_ESTABLECIMIENTO = 'motelos.establecimiento';
const CODIGO_PLATAFORMA = 'plataforma';

const leerEstablecimiento = (): string => {
  try {
    return localStorage.getItem(CLAVE_ESTABLECIMIENTO) ?? '';
  } catch {
    return '';
  }
};

const recordarEstablecimiento = (codigo: string) => {
  try {
    localStorage.setItem(CLAVE_ESTABLECIMIENTO, codigo);
  } catch {
    // sin almacenamiento local, se vuelve a escribir la próxima vez
  }
};

// Estrellas del cielo del panel: posiciones fijas (generador determinístico) para que no salten entre renders.
const ESTRELLAS = (() => {
  let semilla = 7;
  const azar = () => {
    semilla = (semilla * 9301 + 49297) % 233280;
    return semilla / 233280;
  };
  return Array.from({ length: 46 }, (_, i) => ({
    id: i,
    x: azar() * 100,
    y: azar() * 70,
    tam: 1 + azar() * 2,
    demora: azar() * 4,
    duracion: 2.5 + azar() * 3,
  }));
})();

const VENTAJAS = [
  { icono: Lock, texto: 'Caja ciega y arqueo por guardia, con comprobante en PDF.' },
  { icono: ShieldCheck, texto: 'Cada operación queda a nombre de quien la hizo.' },
  { icono: BrainCircuit, texto: 'Pronósticos y alertas calculados en el propio motel.' },
];

const PanelNocturno: React.FC<{ marca: MarcaPublica | null; esPlataforma: boolean }> = ({ marca, esPlataforma }) => {
  const now = useNow(1000);
  const fecha = new Date(now);
  return (
    <aside className="cielo relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-12" aria-hidden="true">
      {ESTRELLAS.map((e) => (
        <span
          key={e.id}
          className="cielo-estrella"
          style={{
            left: `${e.x}%`,
            top: `${e.y}%`,
            width: e.tam,
            height: e.tam,
            animationDelay: `${e.demora}s`,
            animationDuration: `${e.duracion}s`,
          }}
        />
      ))}
      <span className="estrella-fugaz" />
      <span className="cielo-luna" />

      <div className="relative">
        <img src="/logo.png" alt="" className="h-8 object-contain brightness-0 invert" />
      </div>

      <div className="relative max-w-md text-white">
        <p className="text-sm font-medium uppercase tracking-[0.2em] text-white/60">
          {esPlataforma ? 'Plataforma' : marca ? 'Bienvenido a' : 'MotelOS'}
        </p>
        <h2 className="mt-2 text-4xl font-semibold leading-tight">
          {esPlataforma ? 'Equipo de MotelOS' : (marca?.nombre ?? 'La ventanilla de tu motel, en orden.')}
        </h2>
        {marca?.eslogan && !esPlataforma && <p className="mt-3 text-lg text-white/80">{marca.eslogan}</p>}
        <ul className="mt-8 space-y-3">
          {VENTAJAS.map(({ icono: Icono, texto }) => (
            <li key={texto} className="flex items-center gap-3 text-sm text-white/80">
              <span className="grid h-8 w-8 place-items-center rounded-full bg-white/10 ring-1 ring-white/15">
                <Icono className="h-4 w-4" />
              </span>
              {texto}
            </li>
          ))}
        </ul>
      </div>

      <div className="relative flex items-end justify-between text-white">
        <div>
          <p className="font-mono text-5xl font-light tabular-nums">
            {String(fecha.getHours()).padStart(2, '0')}:{String(fecha.getMinutes()).padStart(2, '0')}
          </p>
          <p className="mt-1 text-sm capitalize text-white/60">
            {fecha.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <p className="text-xs text-white/40">Guardias de 06:00, 14:00 y 22:00</p>
      </div>
    </aside>
  );
};

// RNF-04: cada conserje entra con su usuario; todo lo que hace queda a su nombre.
const LoginView: React.FC<LoginViewProps> = ({ onIngreso, aviso }) => {
  const [establecimiento, setEstablecimiento] = useState(leerEstablecimiento);
  const [usuario, setUsuario] = useState('');
  const [clave, setClave] = useState('');
  const [verClave, setVerClave] = useState(false);
  const [mayusculas, setMayusculas] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [marca, setMarca] = useState<MarcaPublica | null>(null);
  const [buscando, setBuscando] = useState(false);

  const codigo = establecimiento.trim().toLowerCase();
  const esPlataforma = codigo === CODIGO_PLATAFORMA;

  // Al escribir el código se reconoce el motel: su nombre, su eslogan y su color de marca (migración 009).
  useEffect(() => {
    if (!codigo || esPlataforma) {
      setMarca(null);
      aplicarMarca(null);
      return;
    }
    setBuscando(true);
    let vigente = true;
    const espera = setTimeout(() => {
      api
        .getMarca(codigo)
        .then((encontrada) => {
          if (!vigente) return;
          setMarca(encontrada);
          aplicarMarca(encontrada?.color_marca ?? null);
        })
        .catch(() => vigente && setMarca(null))
        .finally(() => vigente && setBuscando(false));
    }, 300);
    return () => {
      vigente = false;
      clearTimeout(espera);
    };
  }, [codigo, esPlataforma]);

  const ingresar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      const sesion = await api.login(codigo, usuario, clave);
      recordarEstablecimiento(codigo);
      onIngreso(sesion);
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo iniciar sesión.'));
      setClave('');
    } finally {
      setEnviando(false);
    }
  };

  const detectarMayusculas = (e: React.KeyboardEvent<HTMLInputElement>) => setMayusculas(e.getModifierState('CapsLock'));

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      <PanelNocturno marca={marca} esPlataforma={esPlataforma} />

      <div className="relative flex items-center justify-center px-4 py-12">
        <ThemeToggle className="absolute right-4 top-4" />
        <div className="w-full max-w-sm animate-pop-in">
          <img src="/logo.png" alt="MotelOS" className="logo mb-8 h-9 object-contain lg:hidden" />
          <h1 className="text-2xl font-semibold text-ink">Ingresar</h1>
          <p className="mt-1 text-sm text-muted">Cada operación queda registrada a su nombre.</p>

          {aviso && (
            <p role="status" className="mt-5 rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent">
              {aviso}
            </p>
          )}

          <form onSubmit={ingresar} className="mt-6 space-y-4" noValidate>
            <Field label="Establecimiento" htmlFor="establecimiento" hint={codigo ? undefined : 'Código del motel. Vacío: el de esta instalación.'}>
              <input
                id="establecimiento"
                autoCapitalize="none"
                spellCheck={false}
                maxLength={30}
                placeholder="motelcc"
                className={`${inputClass} h-11`}
                value={establecimiento}
                onChange={(e) => setEstablecimiento(e.target.value)}
              />
            </Field>
            {codigo && (
              <div className="-mt-2 min-h-[1.5rem] text-xs" aria-live="polite">
                {esPlataforma ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 font-medium text-accent">
                    <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                    Plataforma: alta y suspensión de moteles
                  </span>
                ) : marca ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 font-medium text-accent">
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                    {marca.nombre}
                  </span>
                ) : (
                  !buscando && <span className="text-subtle">No reconocemos ese código todavía: revisalo antes de ingresar.</span>
                )}
              </div>
            )}
            <Field label="Usuario" htmlFor="usuario">
              <input
                id="usuario"
                data-autofocus
                autoFocus
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                maxLength={40}
                className={`${inputClass} h-11`}
                value={usuario}
                onChange={(e) => setUsuario(e.target.value)}
              />
            </Field>
            <Field label="Clave" htmlFor="clave">
              <div className="relative">
                <input
                  id="clave"
                  type={verClave ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  maxLength={128}
                  className={`${inputClass} h-11 pr-11`}
                  value={clave}
                  onChange={(e) => setClave(e.target.value)}
                  onKeyUp={detectarMayusculas}
                  onKeyDown={detectarMayusculas}
                />
                <button
                  type="button"
                  onClick={() => setVerClave((v) => !v)}
                  aria-label={verClave ? 'Ocultar la clave' : 'Mostrar la clave'}
                  aria-pressed={verClave}
                  className="press absolute inset-y-0 right-0 grid w-11 place-items-center rounded-r-md text-muted hover:text-ink"
                >
                  {verClave ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>
            </Field>
            {mayusculas && (
              <p role="status" className="-mt-2 text-xs font-medium text-warn">
                Bloq Mayús está activado.
              </p>
            )}
            {error && (
              <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}
            <Button type="submit" className="h-11 w-full" disabled={enviando || !usuario.trim() || !clave}>
              <LogIn className="h-4 w-4" aria-hidden="true" />
              {enviando ? 'Ingresando…' : 'Ingresar'}
            </Button>
          </form>
          <p className="mt-6 text-xs text-subtle">¿Olvidó su clave? La gerencia puede restablecerla desde Configuración.</p>
        </div>
      </div>
    </main>
  );
};

export default LoginView;
