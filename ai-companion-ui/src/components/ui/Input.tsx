import { InputHTMLAttributes, forwardRef, useState } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', type = 'text', style, ...props }, ref) => {
    const [focused, setFocused] = useState(false);

    return (
      <div className={className} style={{ width: '100%' }}>
        {label && (
          <label
            style={{
              display: 'block',
              fontSize: '13px',
              fontWeight: 500,
              color: 'var(--text-primary)',
              marginBottom: '6px',
            }}
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          type={type}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: '6px',
            border: `1px solid ${error ? 'var(--error)' : focused ? 'var(--accent)' : 'var(--border-subtle)'}`,
            backgroundColor: 'var(--bg-secondary)',
            color: 'var(--text-primary)',
            fontSize: '14px',
            outline: 'none',
            boxShadow: focused ? '0 0 0 3px var(--accent-light)' : 'none',
            transition: 'all 150ms ease',
            opacity: props.disabled ? 0.5 : 1,
            cursor: props.disabled ? 'not-allowed' : 'text',
            ...style,
          }}
          {...props}
        />
        {error && (
          <p style={{ marginTop: '4px', fontSize: '12px', color: 'var(--error)' }}>
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
