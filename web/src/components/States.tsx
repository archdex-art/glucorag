import { CircleAlert, RotateCw } from 'lucide-react';
import type { ReactNode } from 'react';
import { errorMessage } from '../api/errors';
import { ICON } from './icon';

/** Placeholder rows in the shape of the content that is loading; no spinner. */
export function Skeleton({ label, rows = 4, variant = 'lines' }: { label: string; rows?: number; variant?: 'lines' | 'rows' | 'block' }) {
  return (
    <div className={`skeleton skeleton-${variant}`} role="status">
      <span className="visually-hidden">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="skeleton-item" aria-hidden="true" />
      ))}
    </div>
  );
}

interface ErrorProps {
  error: unknown;
  /** What failed, e.g. "The ward could not be loaded." */
  title: string;
  onRetry?: () => void;
}

export function ErrorState({ error, title, onRetry }: ErrorProps) {
  return (
    <div className="state state-error" role="alert">
      <CircleAlert {...ICON} />
      <div>
        <p className="state-title">{title}</p>
        <p>{errorMessage(error)}</p>
      </div>
      {onRetry ? (
        <button type="button" className="button" onClick={onRetry}>
          <RotateCw {...ICON} />
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="state state-empty">{children}</div>;
}
