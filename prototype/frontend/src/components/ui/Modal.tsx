import React, { useId } from 'react';
import { X } from 'lucide-react';
import { useDialog } from '../../hooks/useDialog';

interface ModalProps {
  title: string;
  subtitle?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'md' | 'lg';
}

const SIZES = { md: 'max-w-lg', lg: 'max-w-2xl' };

const Modal: React.FC<ModalProps> = ({ title, subtitle, onClose, children, footer, size = 'md' }) => {
  const titleId = useId();
  const ref = useDialog<HTMLDivElement>(onClose);

  return (
    // En el celular el diálogo es una hoja que sube desde abajo, a todo el ancho y al alcance del pulgar.
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4">
      <div className="absolute inset-0 animate-fade-in bg-ink/40 backdrop-blur-[2px]" onClick={onClose} aria-hidden="true" />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`modal-hoja relative flex max-h-[92dvh] w-full flex-col rounded-t-2xl border border-b-0 border-line bg-surface shadow-panel focus:outline-none sm:max-h-[90vh] sm:animate-pop-in sm:rounded-lg sm:border-b ${SIZES[size]}`}
      >
        <span aria-hidden="true" className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-line-strong sm:hidden" />
        <div className="flex items-start justify-between gap-4 border-b border-line px-4 py-3 sm:px-6 sm:py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-base font-semibold text-ink">
              {title}
            </h2>
            {subtitle && <div className="mt-0.5 text-sm text-muted">{subtitle}</div>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="press hit -mr-2 rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>
        <div
          className={`overflow-y-auto px-4 py-4 sm:px-6 sm:py-5 ${footer ? '' : 'max-sm:pb-[calc(1.25rem+env(safe-area-inset-bottom))]'}`}
        >
          {children}
        </div>
        {footer && (
          <div className="border-t border-line px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3 sm:px-6 sm:py-4">{footer}</div>
        )}
      </div>
    </div>
  );
};

export default Modal;
