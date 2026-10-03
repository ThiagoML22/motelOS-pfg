import React from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-accent-fg hover:bg-accent-hover',
  secondary: 'border border-line-strong bg-surface text-ink hover:bg-surface-2',
  ghost: 'text-muted hover:bg-surface-2 hover:text-ink',
  danger: 'bg-danger text-white hover:opacity-90',
};

const SIZES: Record<Size, string> = {
  sm: 'min-h-11 min-w-11 px-3 text-xs',
  md: 'min-h-11 min-w-11 px-4 text-sm',
};

const Button: React.FC<ButtonProps> = ({ variant = 'primary', size = 'md', className = '', type = 'button', ...props }) => (
  <button
    type={type}
    className={`press inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    {...props}
  />
);

export default Button;
