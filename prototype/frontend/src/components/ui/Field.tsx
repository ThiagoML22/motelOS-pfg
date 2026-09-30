import React from 'react';

export const inputClass =
  'w-full rounded-md border border-line-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-subtle focus:border-accent focus:ring-1 focus:ring-accent focus-visible:outline-none';

interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}

const Field: React.FC<FieldProps> = ({ label, htmlFor, hint, error, children }) => (
  <div>
    <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-medium text-muted">
      {label}
    </label>
    {children}
    {error ? (
      <p role="alert" className="mt-1.5 text-xs text-danger">
        {error}
      </p>
    ) : (
      hint && <p className="mt-1.5 text-xs text-subtle">{hint}</p>
    )}
  </div>
);

export default Field;
