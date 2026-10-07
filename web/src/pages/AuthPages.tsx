import { useId, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ApiError, UnauthorizedError, errorMessage } from '../api/errors';
import { useAuth } from '../auth/context';
import { AuthFrame } from '../components/AuthFrame';
import { ResearchNotice } from '../components/Brand';
import { Field, FieldError, PasswordInput } from '../components/Field';
import { describedBy } from '../lib/aria';

const MIN_PASSWORD = 10;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface Errors {
  email?: string;
  password?: string;
  ack?: string;
  form?: string;
}

function checkEmail(email: string): string | undefined {
  if (!email.trim()) return 'Enter your email address.';
  if (!EMAIL_RE.test(email.trim())) return 'Enter an email address like name@example.com.';
  return undefined;
}

/** Focus the first field with an error so screen readers hear it. */
function focusFirst(form: HTMLFormElement | null, errors: Errors) {
  const name = (['email', 'password', 'ack'] as const).find((k) => errors[k]);
  if (name) form?.querySelector<HTMLInputElement>(`[name="${name}"]`)?.focus();
}

export function SignUpPage() {
  const { signUp } = useAuth();
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [ack, setAck] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next: Errors = {
      email: checkEmail(email),
      password: password.length < MIN_PASSWORD ? `Use at least ${MIN_PASSWORD} characters.` : undefined,
      ack: ack ? undefined : 'Confirm that you understand this is a research prototype.',
    };
    setErrors(next);
    if (next.email || next.password || next.ack) {
      focusFirst(formRef.current, next);
      return;
    }
    setBusy(true);
    try {
      // The router moves a new account on to set-up.
      await signUp(email.trim(), password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setErrors({ email: 'An account with this email already exists.' });
      else if (err instanceof ApiError && err.status === 422) setErrors({ password: err.message });
      else setErrors({ form: errorMessage(err) });
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      notice={false}
      aside={
        <p className="auth-switch">
          Have an account? <Link to="/signin">Sign in</Link>
        </p>
      }
    >
      <h1>Create account</h1>
      <p className="auth-lede">Your readings and forecasts stay in this account. You can export or delete them any time.</p>
      <form ref={formRef} className="form" onSubmit={(e) => void onSubmit(e)} noValidate>
        <Field id={`${id}-email`} label="Email" error={errors.email}>
          <input
            id={`${id}-email`}
            name="email"
            type="email"
            autoComplete="email"
            inputMode="email"
            spellCheck={false}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={describedBy(`${id}-email`, false, Boolean(errors.email))}
            required
          />
        </Field>
        {errors.email === 'An account with this email already exists.' ? (
          <p className="field-hint">
            <Link to="/signin">Sign in</Link> instead.
          </p>
        ) : null}
        <Field id={`${id}-password`} label="Password" hint={`At least ${MIN_PASSWORD} characters.`} error={errors.password}>
          <PasswordInput
            id={`${id}-password`}
            name="password"
            autoComplete="new-password"
            minLength={MIN_PASSWORD}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={describedBy(`${id}-password`, true, Boolean(errors.password))}
            required
          />
        </Field>
        <div className="check-field">
          <ResearchNotice className="notice-block" />
          <label className="check">
            <input
              type="checkbox"
              name="ack"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              aria-invalid={errors.ack ? true : undefined}
              aria-describedby={errors.ack ? `${id}-ack-error` : undefined}
              required
            />
            <span>I understand this is a research prototype and not for treatment decisions.</span>
          </label>
          {errors.ack ? <FieldError id={`${id}-ack-error`}>{errors.ack}</FieldError> : null}
        </div>
        {errors.form ? (
          <p className="form-error" role="alert">
            {errors.form}
          </p>
        ) : null}
        <button type="submit" className="button button-primary button-block" disabled={busy}>
          {busy ? 'Creating account' : 'Create account'}
        </button>
      </form>
    </AuthFrame>
  );
}

export function SignInPage() {
  const { signIn, notice } = useAuth();
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const next: Errors = {
      email: checkEmail(email),
      password: password ? undefined : 'Enter your password.',
    };
    setErrors(next);
    if (next.email || next.password) {
      focusFirst(formRef.current, next);
      return;
    }
    setBusy(true);
    try {
      await signIn(email.trim(), password);
    } catch (err) {
      // 401: wrong email or password; 429: throttled, with the wait in the message.
      setErrors({ form: err instanceof UnauthorizedError ? 'Email or password is incorrect.' : errorMessage(err) });
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      aside={
        <p className="auth-switch">
          New here? <Link to="/signup">Create account</Link>
        </p>
      }
    >
      <h1>Sign in</h1>
      {notice && !errors.form ? (
        <p className="form-notice" role="status">
          {notice}
        </p>
      ) : null}
      <form ref={formRef} className="form" onSubmit={(e) => void onSubmit(e)} noValidate>
        <Field id={`${id}-email`} label="Email" error={errors.email}>
          <input
            id={`${id}-email`}
            name="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            spellCheck={false}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={describedBy(`${id}-email`, false, Boolean(errors.email))}
            required
          />
        </Field>
        <Field id={`${id}-password`} label="Password" error={errors.password}>
          <PasswordInput
            id={`${id}-password`}
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={errors.password ? true : undefined}
            aria-describedby={describedBy(`${id}-password`, false, Boolean(errors.password))}
            required
          />
        </Field>
        {errors.form ? (
          <p className="form-error" role="alert">
            {errors.form}
          </p>
        ) : null}
        <button type="submit" className="button button-primary button-block" disabled={busy}>
          {busy ? 'Signing in' : 'Sign in'}
        </button>
      </form>
    </AuthFrame>
  );
}
