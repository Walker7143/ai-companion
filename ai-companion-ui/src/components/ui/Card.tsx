import { HTMLAttributes, forwardRef } from 'react';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated';
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ variant = 'default', className = '', style, children, ...props }, ref) => {
    const baseStyle: React.CSSProperties = {
      backgroundColor: 'var(--bg-secondary)',
      borderRadius: '12px',
      transition: 'box-shadow 200ms ease, border-color 200ms ease',
    };

    const variantStyle: React.CSSProperties =
      variant === 'elevated'
        ? { boxShadow: 'var(--shadow-md)' }
        : { border: '1px solid var(--border-subtle)', boxShadow: 'var(--shadow-sm)' };

    return (
      <div
        ref={ref}
        className={className}
        style={{ ...baseStyle, ...variantStyle, ...style }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

export const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className = '', style, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={className}
        style={{
          padding: '16px 16px 12px',
          marginBottom: '16px',
          borderBottom: '1px solid var(--border-subtle)',
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CardHeader.displayName = 'CardHeader';

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className = '', style, children, ...props }, ref) => {
    return (
      <h3
        ref={ref}
        className={className}
        style={{
          fontSize: '16px',
          fontWeight: 600,
          color: 'var(--text-primary)',
          ...style,
        }}
        {...props}
      >
        {children}
      </h3>
    );
  }
);

CardTitle.displayName = 'CardTitle';

export const CardContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className = '', style, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={className}
        style={{
          padding: '16px',
          ...style,
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CardContent.displayName = 'CardContent';
