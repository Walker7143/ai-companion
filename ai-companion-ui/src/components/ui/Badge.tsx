import { HTMLAttributes, forwardRef } from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'dialogue' | 'memory' | 'session' | 'proactive' | 'api';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-bg-tertiary text-text-secondary dark:bg-bg-tertiary dark:text-text-secondary',
  success: 'bg-success/20 text-success dark:bg-success/20 dark:text-success',
  warning: 'bg-warning/20 text-warning dark:bg-warning/20 dark:text-warning',
  error: 'bg-error/20 text-error dark:bg-error/20 dark:text-error',
  info: 'bg-info/20 text-info dark:bg-info/20 dark:text-info',
  dialogue: 'bg-tag-dialogue/20 text-tag-dialogue dark:bg-tag-dialogue/20 dark:text-tag-dialogue',
  memory: 'bg-tag-memory/20 text-tag-memory dark:bg-tag-memory/20 dark:text-tag-memory',
  session: 'bg-tag-session/20 text-tag-session dark:bg-tag-session/20 dark:text-tag-session',
  proactive: 'bg-tag-proactive/20 text-tag-proactive dark:bg-tag-proactive/20 dark:text-tag-proactive',
  api: 'bg-tag-api/20 text-tag-api dark:bg-tag-api/20 dark:text-tag-api',
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ variant = 'default', className = '', children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={`
          inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
          ${variantStyles[variant]}
          ${className}
        `}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';
