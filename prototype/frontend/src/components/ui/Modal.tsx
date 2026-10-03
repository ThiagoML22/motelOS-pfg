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
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 animate-fade-in bg-ink/40" onClick={onClose} aria-hidden="true" />
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={`relative flex max-h-[90vh] w-full animate-pop-in flex-col rounded-lg border border-line bg-surface shadow-panel focus:outline-none ${SIZES[size]}`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
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
        <div className="overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="border-t border-line px-6 py-4">{footer}</div>}
      </div>
    </div>
  );
};

export default Modal;
