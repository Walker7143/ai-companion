import { InputHTMLAttributes, forwardRef, useState } from 'react';

interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
}

export const Toggle = forwardRef<HTMLInputElement, ToggleProps>(
  ({ label, className = '', checked, onChange, style, ...props }, ref) => {
    const [isHovered, setIsHovered] = useState(false);

    return (
      <label
        className={className}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          cursor: 'pointer',
          ...style,
        }}
      >
        <div style={{ position: 'relative' }}>
          <input
            ref={ref}
            type="checkbox"
            checked={checked}
            onChange={onChange}
            style={{ position: 'absolute', opacity: 0, width: 0, height: 0 }}
            {...props}
          />
          <div
            style={{
              width: '36px',
              height: '20px',
              borderRadius: '10px',
              backgroundColor: checked ? 'var(--accent)' : isHovered ? 'var(--border-default)' : 'var(--bg-tertiary)',
              transition: 'background-color 200ms ease',
              cursor: 'pointer',
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
          />
          <div
            style={{
              position: 'absolute',
              left: checked ? '18px' : '2px',
              top: '2px',
              width: '16px',
              height: '16px',
              borderRadius: '50%',
              backgroundColor: '#ffffff',
              boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
              transition: 'left 200ms ease',
              cursor: 'pointer',
            }}
          />
        </div>
        {label && (
          <span
            style={{
              marginLeft: '12px',
              fontSize: '14px',
              color: 'var(--text-primary)',
            }}
          >
            {label}
          </span>
        )}
      </label>
    );
  }
);

Toggle.displayName = 'Toggle';
