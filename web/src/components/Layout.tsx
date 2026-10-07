import { Activity, Bell, ChartLine, CirclePlus, FlaskConical, House, LogOut, Server, Settings, type LucideIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useCohort } from '../api/hooks';
import { useAccount, useAuth } from '../auth/context';
import { ResearchNotice, Wordmark } from './Brand';
import { ErrorBoundary } from './ErrorBoundary';
import { ClockStatus } from './PageHeader';
import { ICON, NAV_ICON } from './icon';
import { RefreshContext, type RefreshState } from './refresh';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end: boolean;
}

const PERSON_NAV: NavItem[] = [
  { to: '/', label: 'Today', icon: House, end: true },
  { to: '/history', label: 'History', icon: ChartLine, end: false },
  { to: '/add', label: 'Add data', icon: CirclePlus, end: false },
];

const CLINICAL_NAV: NavItem[] = [
  { to: '/ward', label: 'Ward', icon: Activity, end: false },
  { to: '/alerts', label: 'Alerts', icon: Bell, end: false },
  { to: '/model', label: 'Model', icon: FlaskConical, end: false },
  { to: '/system', label: 'System', icon: Server, end: false },
];

const SETTINGS: NavItem = { to: '/settings', label: 'Settings', icon: Settings, end: false };

function NavItems({ items, activeAlerts, className }: { items: NavItem[]; activeAlerts: number; className: string }) {
  return (
    <ul className={className}>
      {items.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink to={to} end={end}>
            <Icon {...NAV_ICON} />
            <span className="nav-label">{label}</span>
            {to === '/alerts' && activeAlerts > 0 ? (
              <span className="badge num">
                {activeAlerts}
                <span className="visually-hidden"> active</span>
              </span>
            ) : null}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

/** Rail from 900px, top bar and bottom tab bar below. People see their four pages; clinicians the clinical group. */
export function Layout() {
  const { signOut } = useAuth();
  const account = useAccount();
  const clinician = account.role === 'clinician';
  const location = useLocation();
  const [paused, setPaused] = useState(false);
  const refresh = useMemo<RefreshState>(() => ({ paused, setPaused }), [paused]);
  const cohort = useCohort(paused, clinician);
  const activeAlerts = cohort.data?.patients.reduce((n, p) => n + p.active_alerts.length, 0) ?? 0;
  const tabs = clinician ? [...CLINICAL_NAV, SETTINGS] : [...PERSON_NAV, SETTINGS];

  return (
    <RefreshContext.Provider value={refresh}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="shell">
        <aside className="rail">
          <Wordmark />
          <nav aria-label="Main" className="rail-navs">
            {clinician ? (
              <div className="rail-group">
                <h2 className="rail-heading">Clinical</h2>
                <NavItems items={CLINICAL_NAV} activeAlerts={activeAlerts} className="rail-nav" />
              </div>
            ) : (
              <NavItems items={PERSON_NAV} activeAlerts={0} className="rail-nav" />
            )}
            <NavItems items={[SETTINGS]} activeAlerts={0} className="rail-nav" />
          </nav>
          <div className="rail-foot">
            <ResearchNotice />
            <p className="rail-account" title={account.email}>
              <span className="visually-hidden">Signed in as </span>
              {account.email}
            </p>
            <button type="button" className="button button-quiet" onClick={() => void signOut()}>
              <LogOut {...ICON} />
              Sign out
            </button>
          </div>
        </aside>

        <header className="topbar">
          <Wordmark />
          {clinician ? <ClockStatus withTime={false} /> : null}
        </header>
        <ResearchNotice className="notice-bar" />

        <main id="main" className="main" tabIndex={-1}>
          <ErrorBoundary key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>

        <nav className="tabbar" aria-label="Main">
          <NavItems items={tabs} activeAlerts={activeAlerts} className={`tabbar-nav tabbar-${tabs.length}`} />
        </nav>
      </div>
    </RefreshContext.Provider>
  );
}
