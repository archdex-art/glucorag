import { Pause, Play } from 'lucide-react';
import type { ReactNode } from 'react';
import { useStats } from '../api/hooks';
import { useAuth } from '../auth/context';
import { epochToWall, formatApiTime, formatTime } from '../lib/time';
import { ICON } from './icon';
import { useRefresh } from './refresh';

/** Staff only: "Replay data" chip plus the data time, or "Live" on the wall clock. */
export function ClockStatus({ withTime = true }: { withTime?: boolean }) {
  const { paused } = useRefresh();
  const staff = useAuth().account?.role === 'clinician';
  const stats = useStats(paused, staff);
  if (!staff || !stats.data) return null;
  if (stats.data.clock !== 'data') return <span className="chip chip-clock">Live</span>;
  return (
    <span className="clock-status">
      <span className="chip chip-clock">Replay data</span>
      {withTime ? (
        <span className="clock-time num">
          {/* The data clock starts at datetime.min until the first reading arrives. */}
          {stats.data.as_of.startsWith('0001-') ? (
            'No data time yet'
          ) : (
            <>
              Data time <time>{formatApiTime(stats.data.as_of)}</time>
            </>
          )}
        </span>
      ) : null}
    </span>
  );
}

interface RefreshProps {
  /** react-query dataUpdatedAt (epoch ms; 0 = never). */
  updatedAt: number;
}

function RefreshControl({ updatedAt }: RefreshProps) {
  const { paused, setPaused } = useRefresh();
  return (
    <span className="refresh">
      <span className="refresh-text num">
        {updatedAt ? `Updated ${formatTime(epochToWall(updatedAt), true)}` : 'Not updated yet'}
        {paused ? <span className="refresh-paused">, paused</span> : null}
      </span>
      <button
        type="button"
        className="icon-button toggle"
        aria-pressed={paused}
        aria-label="Pause auto-refresh"
        title={paused ? 'Resume auto-refresh' : 'Pause auto-refresh'}
        onClick={() => setPaused(!paused)}
      >
        {paused ? <Play {...ICON} /> : <Pause {...ICON} />}
      </button>
    </span>
  );
}

interface Props {
  title: ReactNode;
  /** Lines under the title (patient facts, verdicts). */
  children?: ReactNode;
  /** Shown for pages that poll. */
  refresh?: RefreshProps;
  /** Above the title. */
  breadcrumb?: ReactNode;
}

export function PageHeader({ title, children, refresh, breadcrumb }: Props) {
  return (
    <header className="page-header">
      {breadcrumb}
      <div className="page-header-row">
        <h1>{title}</h1>
        <div className="page-status">
          <ClockStatus />
          {refresh ? <RefreshControl {...refresh} /> : null}
        </div>
      </div>
      {children}
    </header>
  );
}
