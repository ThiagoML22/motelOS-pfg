import React, { useState } from 'react';
import { LogIn } from 'lucide-react';
import { Sesion } from '../types';
import { api, getErrorMessage } from '../services/api';
import Button from './ui/Button';
import Field, { inputClass } from './ui/Field';

interface LoginViewProps {
  onIngreso: (sesion: Sesion) => void;
  aviso?: string | null;
}

// RNF-04: cada conserje entra con su usuario; todo lo que hace queda a su nombre.
const LoginView: React.FC<LoginViewProps> = ({ onIngreso, aviso }) => {
  const [usuario, setUsuario] = useState('');
  const [clave, setClave] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const ingresar = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      onIngreso(await api.login(usuario, clave));
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo iniciar sesión.'));
      setClave('');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm animate-pop-in rounded-lg border border-line bg-surface p-8 shadow-lift">
        <img src="/logo.png" alt="MotelOS" className="mx-auto mb-6 h-9 object-contain" />
        <h1 className="text-center text-lg font-semibold text-ink">Ingreso a la ventanilla</h1>
        <p className="mt-1 text-center text-sm text-muted">Cada operación queda registrada a su nombre.</p>

        {aviso && (
          <p role="status" className="mt-5 rounded-md border border-accent/30 bg-accent-soft px-3 py-2 text-sm text-accent">
            {aviso}
          </p>
        )}

        <form onSubmit={ingresar} className="mt-6 space-y-4" noValidate>
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
              className={inputClass}
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
            />
          </Field>
          <Field label="Clave" htmlFor="clave">
            <input
              id="clave"
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
              className={inputClass}
              value={clave}
              onChange={(e) => setClave(e.target.value)}
            />
          </Field>
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={enviando || !usuario.trim() || !clave}>
            <LogIn className="h-4 w-4" aria-hidden="true" />
            {enviando ? 'Ingresando…' : 'Ingresar'}
          </Button>
        </form>
      </div>
    </main>
  );
};

export default LoginView;
