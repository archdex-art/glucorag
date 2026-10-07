import { CircleAlert, Eye, EyeOff } from 'lucide-react';
import { useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { ICON } from './icon';

interface FieldProps {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  className?: string;
}

/** Label, control, hint and field-level error, wired by id. */
export function Field({ id, label, hint, error, children, className = '' }: FieldProps) {
  return (
    <div className={`field ${className}`.trim()}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="field-hint">
          {hint}
        </p>
      ) : null}
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : null}
    </div>
  );
}

export function FieldError({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="field-error">
      <CircleAlert {...ICON} />
      <span>{children}</span>
    </p>
  );
}

type PasswordProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & { id: string };

/** Password input with a show/hide toggle. */
export function PasswordInput(props: PasswordProps) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="input-with-button">
      <input {...props} type={visible ? 'text' : 'password'} spellCheck={false} autoCapitalize="off" />
      <button
        type="button"
        className="icon-button"
        aria-pressed={visible}
        aria-label="Show password"
        aria-controls={props.id}
        title={visible ? 'Hide password' : 'Show password'}
        onClick={() => setVisible(!visible)}
      >
        {visible ? <EyeOff {...ICON} /> : <Eye {...ICON} />}
      </button>
    </span>
  );
}
