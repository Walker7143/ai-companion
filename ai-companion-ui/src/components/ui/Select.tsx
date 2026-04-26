import { SelectHTMLAttributes, forwardRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: SelectOption[];
  error?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, options, error, className = '', style, ...props }, ref) => {
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
        <div style={{ position: 'relative' }}>
          <select
            ref={ref}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            style={{
              width: '100%',
              padding: '8px 36px 8px 12px',
              borderRadius: '6px',
              border: `1px solid ${error ? 'var(--error)' : focused ? 'var(--accent)' : 'var(--border-subtle)'}`,
              backgroundColor: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
              fontSize: '14px',
              outline: 'none',
              boxShadow: focused ? '0 0 0 3px var(--accent-light)' : 'none',
              transition: 'all 150ms ease',
              appearance: 'none',
              cursor: 'pointer',
              ...style,
            }}
            {...props}
          >
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <ChevronDown
            style={{
              position: 'absolute',
              right: '12px',
              top: '50%',
              transform: 'translateY(-50%)',
              width: '16px',
              height: '16px',
              color: 'var(--text-muted)',
              pointerEvents: 'none',
            }}
          />
        </div>
        {error && (
          <p style={{ marginTop: '4px', fontSize: '12px', color: 'var(--error)' }}>
            {error}
          </p>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';
