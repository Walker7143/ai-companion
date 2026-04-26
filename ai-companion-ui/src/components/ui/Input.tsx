import { InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', type = 'text', ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label className="block text-sm font-medium text-text-primary mb-1.5">
            {label}
          </label>
        )}
        <input
          ref={ref}
          type={type}
          className={`
            w-full px-3 py-2 rounded-md
            bg-bg-secondary border border-border-subtle
            text-text-primary placeholder-text-muted
            focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent
            transition-colors duration-150
            disabled:opacity-50 disabled:cursor-not-allowed
            dark:bg-bg-secondary dark:border-border-subtle
            ${error ? 'border-error focus:ring-error' : ''}
            ${className}
          `}
          {...props}
        />
        {error && <p className="mt-1 text-xs text-error">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';

interface PasswordInputProps extends Omit<InputProps, 'type'> {}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className = '', ...props }, ref) => {
    return <Input ref={ref} type="password" className={className} {...props} />;
  }
);

PasswordInput.displayName = 'PasswordInput';
