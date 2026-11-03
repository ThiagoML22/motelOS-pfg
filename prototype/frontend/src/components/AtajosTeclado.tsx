import React from 'react';
import Modal from './ui/Modal';

export interface Atajo {
  teclas: string[];
  descripcion: string;
}

// Las teclas sueltas no se toman mientras se escribe en un campo ni con un diálogo abierto.
export const escribiendo = (e: KeyboardEvent) => {
  const destino = e.target as HTMLElement | null;
  if (destino?.closest('input, textarea, select, [contenteditable="true"]')) return true;
  return Boolean(document.querySelector('[aria-modal="true"]'));
};

const Tecla: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <kbd className="inline-flex min-w-[1.75rem] items-center justify-center rounded-md border border-line-strong border-b-2 bg-surface-2 px-1.5 py-0.5 font-sans text-xs font-medium text-ink">
    {children}
  </kbd>
);

// «?» muestra las teclas rápidas de la ventanilla, agrupadas.
const AtajosTeclado: React.FC<{ grupos: { titulo: string; atajos: Atajo[] }[]; onClose: () => void }> = ({ grupos, onClose }) => (
  <Modal title="Atajos de teclado" subtitle="Funcionan cuando no estás escribiendo en un campo." onClose={onClose}>
    <div className="space-y-5">
      {grupos.map((g) => (
        <section key={g.titulo}>
          <h3 className="mb-2 text-[11px] font-medium uppercase tracking-wide text-subtle">{g.titulo}</h3>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {g.atajos.map((a, i) => (
              <li
                key={a.descripcion}
                className="flex animate-tarjeta-in items-center justify-between gap-4 px-3 py-2.5 text-sm"
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <span className="text-ink">{a.descripcion}</span>
                <span className="flex shrink-0 items-center gap-1 text-xs text-subtle">
                  {a.teclas.map((t, j) => (
                    <React.Fragment key={t}>
                      {j > 0 && <span>o</span>}
                      <Tecla>{t}</Tecla>
                    </React.Fragment>
                  ))}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  </Modal>
);

export default AtajosTeclado;
