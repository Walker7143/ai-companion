import { HTMLAttributes, forwardRef } from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, React.CSSProperties> = {
  default: {
    backgroundColor: 'var(--bg-tertiary)',
    color: 'var(--text-secondary)',
  },
  success: {
    backgroundColor: 'var(--success-light)',
    color: 'var(--success)',
  },
  warning: {
    backgroundColor: 'var(--warning-light)',
    color: 'var(--warning)',
  },
  error: {
    backgroundColor: 'var(--error-light)',
    color: 'var(--error)',
  },
  info: {
    backgroundColor: 'var(--info-light)',
    color: 'var(--info)',
  },
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ variant = 'default', className = '', style, children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={className}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          padding: '2px 8px',
          borderRadius: '4px',
          fontSize: '11px',
          fontWeight: 500,
          ...variantStyles[variant],
          ...style,
        }}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';
