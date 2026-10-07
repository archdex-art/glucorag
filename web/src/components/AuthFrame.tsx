import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ResearchNotice, Wordmark } from './Brand';

interface Props {
  children: ReactNode;
  /** Right of the wordmark, e.g. "Have an account? Sign in". */
  aside?: ReactNode;
  wide?: boolean;
  /** Off when the page shows the research notice itself (sign-up, beside its checkbox). */
  notice?: boolean;
}

/** The frame of the signed-out and set-up pages: wordmark, one sheet, the research notice. */
export function AuthFrame({ children, aside, wide = false, notice = true }: Props) {
  return (
    <div className="auth-page">
      <header className="auth-top">
        <Link to="/" className="wordmark-link">
          <Wordmark />
        </Link>
        {aside}
      </header>
      <main id="main" className={`auth-sheet${wide ? ' auth-sheet-wide' : ''}`}>
        {children}
      </main>
      {notice ? <ResearchNotice className="auth-notice" /> : null}
    </div>
  );
}
