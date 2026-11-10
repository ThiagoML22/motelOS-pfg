import React, { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search, Sparkles } from 'lucide-react';

export interface Comando {
  id: string;
  titulo: string;
  detalle?: string;
  grupo: string;
  icono: React.ElementType;
  // Palabras extra para encontrarlo («oscuro» encuentra «Cambiar el tema»).
  claves?: string;
  accion: () => void;
}

const normalizar = (texto: string) =>
  texto
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase();

interface PaletaComandosProps {
  comandos: Comando[];
  onClose: () => void;
  // Si se escribe algo que no es un comando, la gerencia puede preguntárselo al asistente.
  onPreguntar?: (texto: string) => void;
}

// Ctrl+K (⌘K en Mac): ir a cualquier sección, abrir una habitación por su número o hacer una acción, sin el mouse.
const PaletaComandos: React.FC<PaletaComandosProps> = ({ comandos, onClose, onPreguntar }) => {
  const [texto, setTexto] = useState('');
  const [activo, setActivo] = useState(0);
  const entrada = useRef<HTMLInputElement>(null);
  const lista = useRef<HTMLUListElement>(null);

  const filtrados = useMemo(() => {
    const buscado = normalizar(texto.trim());
    const base = buscado
      ? comandos.filter((c) => normalizar(`${c.titulo} ${c.detalle ?? ''} ${c.claves ?? ''}`).includes(buscado))
      : comandos;
    const extra: Comando[] =
      onPreguntar && texto.trim().length > 3
        ? [
            {
              id: 'preguntar',
              titulo: `Preguntarle a Mot: «${texto.trim()}»`,
              grupo: 'Inteligencia',
              icono: Sparkles,
              accion: () => onPreguntar(texto.trim()),
            },
          ]
        : [];
    return [...base.slice(0, 40), ...extra];
  }, [texto, comandos, onPreguntar]);

  useEffect(() => {
    entrada.current?.focus();
  }, []);

  useEffect(() => setActivo(0), [texto]);

  useEffect(() => {
    lista.current?.querySelector(`[data-indice="${activo}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [activo]);

  const ejecutar = (comando: Comando | undefined) => {
    if (!comando) return;
    onClose();
    comando.accion();
  };

  const teclas = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActivo((i) => Math.min(i + 1, filtrados.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActivo((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      ejecutar(filtrados[activo]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  let grupoAnterior = '';
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center px-4 pt-[12vh]" role="dialog" aria-modal="true" aria-label="Buscar y hacer">
      <div className="absolute inset-0 animate-fade-in bg-ink/40" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full max-w-xl animate-pop-in overflow-hidden rounded-xl border border-line bg-surface shadow-panel" onKeyDown={teclas}>
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search className="h-4 w-4 text-muted" aria-hidden="true" />
          <input
            ref={entrada}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Buscar una sección, una habitación («7») o una acción…"
            aria-label="Buscar"
            role="combobox"
            aria-expanded="true"
            aria-controls="paleta-resultados"
            aria-activedescendant={filtrados[activo] ? `paleta-${filtrados[activo].id}` : undefined}
            className="h-14 flex-1 bg-transparent text-sm text-ink placeholder:text-subtle focus:outline-none"
          />
          <kbd className="rounded border border-line px-1.5 py-0.5 text-[10px] text-muted">Esc</kbd>
        </div>
        <ul ref={lista} id="paleta-resultados" role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
          {filtrados.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted">Nada coincide con «{texto}».</li>}
          {filtrados.map((c, i) => {
            const encabezado = c.grupo !== grupoAnterior ? c.grupo : null;
            grupoAnterior = c.grupo;
            const Icono = c.icono;
            return (
              <React.Fragment key={c.id}>
                {encabezado && (
                  <li role="presentation" className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-subtle">
                    {encabezado}
                  </li>
                )}
                <li
                  id={`paleta-${c.id}`}
                  role="option"
                  aria-selected={i === activo}
                  data-indice={i}
                  onMouseMove={() => setActivo(i)}
                  onClick={() => ejecutar(c)}
                  className={`flex cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-sm ${
                    i === activo ? 'bg-accent-soft text-accent' : 'text-ink'
                  }`}
                >
                  <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate">{c.titulo}</span>
                  {c.detalle && <span className="shrink-0 text-xs text-muted">{c.detalle}</span>}
                  {i === activo && <CornerDownLeft className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                </li>
              </React.Fragment>
            );
          })}
        </ul>
        <div className="flex items-center gap-4 border-t border-line px-4 py-2 text-[11px] text-subtle">
          <span>↑↓ para moverse</span>
          <span>Enter para elegir</span>
          <span className="ml-auto">Ctrl K abre y cierra</span>
        </div>
      </div>
    </div>
  );
};

export default PaletaComandos;
