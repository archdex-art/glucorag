import { useId, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useCohort } from '../api/hooks';
import type { PatientRisk } from '../api/types';
import { PageHeader } from '../components/PageHeader';
import { PriorityChip } from '../components/PriorityChip';
import { RangeStrip } from '../components/RangeStrip';
import { Empty, ErrorState, Skeleton } from '../components/States';
import { AlertTag, StatusIcon } from '../components/StatusIcon';
import { TrendIcon } from '../components/Trend';
import { ZoneLegend } from '../components/ZoneLegend';
import { useRefresh } from '../components/refresh';
import { formatElapsed } from '../lib/time';
import { EMPTY_FILTER, assessment, earliestRisk, filterWard, wardSections, type WardFilter } from '../lib/ward';
import { zoneOf } from '../lib/zones';

function WardRow({ p }: { p: PatientRisk }) {
  const flag = earliestRisk(p);
  const fresh = p.status === 'at_risk' || p.status === 'ok';
  const value = p.last_glucose_mg_dl;
  return (
    <li>
      <Link to={`/patients/${encodeURIComponent(p.patient_id)}`} className={`ward-row status-${p.status}`}>
        <span className="cell-patient">
          <span className="patient-id num">{p.patient_id}</span>
          <span className="patient-type">{p.diabetes_type ?? 'Type unknown'}</span>
        </span>
        <span className="cell-now">
          {value !== null ? (
            <>
              <span className={`now-value num${fresh ? ` zt-${zoneOf(value)}` : ' is-old'}`}>{Math.round(value)}</span>
              <span className="unit">mg/dL</span>
              {fresh ? <TrendIcon rate={p.trend_mg_dl_per_min} /> : null}
              {p.minutes_since_last !== null ? (
                <span className="ago num">
                  {p.minutes_since_last < 1 ? 'Just now' : `${formatElapsed(p.minutes_since_last)} ago`}
                </span>
              ) : null}
            </>
          ) : (
            <span className="ago">No value</span>
          )}
        </span>
        <span className="cell-strip">
          <RangeStrip current={value} band={p.forecast} size="row" />
        </span>
        <span className="cell-assessment">
          <StatusIcon status={p.status} risk={flag?.type} />
          <span className="sentence">{assessment(p)}</span>
          <PriorityChip severity={p.severity} risk={flag?.type} />
        </span>
        <span className="cell-alerts">
          {p.active_alerts.length ? (
            p.active_alerts.map((a) => <AlertTag key={a} type={a} />)
          ) : (
            <span className="visually-hidden">No active alerts</span>
          )}
        </span>
      </Link>
    </li>
  );
}

function EmptyWard() {
  const origin = typeof window === 'undefined' ? 'http://127.0.0.1:8000' : window.location.origin;
  return (
    <Empty>
      <p className="state-title">No patients yet.</p>
      <p>Register a patient with POST /patients, then stream readings. To replay a recorded series:</p>
      <pre className="command">
        <code>
          GLUCORAG_API_KEY=&lt;key&gt; glucorag-replay data/raw/shanghai/Shanghai_T1DM/1001_0_20210730.xlsx --url {origin}
        </code>
      </pre>
    </Empty>
  );
}

export function WardPage() {
  const { paused } = useRefresh();
  const cohort = useCohort(paused);
  const [filter, setFilter] = useState<WardFilter>(EMPTY_FILTER);
  const ids = { search: useId(), type: useId() };

  const patients = useMemo(() => cohort.data?.patients ?? [], [cohort.data]);
  const types = useMemo(
    () => [...new Set(patients.map((p) => p.diabetes_type).filter((t): t is string => Boolean(t)))].sort(),
    [patients],
  );
  const sections = useMemo(() => wardSections(filterWard(patients, filter)), [patients, filter]);
  const shown = sections.reduce((n, s) => n + s.patients.length, 0);
  const filtered = filter.search.trim() !== '' || filter.diabetesType !== 'all';

  return (
    <>
      <PageHeader title="Ward" refresh={{ updatedAt: cohort.dataUpdatedAt }} />
      <div className="sheet">
        <div className="toolbar">
          <form className="filters" role="search" onSubmit={(e) => e.preventDefault()}>
            <div className="field">
              <label htmlFor={ids.search}>Patient ID</label>
              <input
                id={ids.search}
                type="search"
                className="num"
                value={filter.search}
                placeholder="Search"
                autoComplete="off"
                onChange={(e) => setFilter({ ...filter, search: e.target.value })}
              />
            </div>
            <div className="field">
              <label htmlFor={ids.type}>Diabetes type</label>
              <select id={ids.type} value={filter.diabetesType} onChange={(e) => setFilter({ ...filter, diabetesType: e.target.value })}>
                <option value="all">All types</option>
                {types.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
                <option value="unknown">Not recorded</option>
              </select>
            </div>
          </form>
          <ZoneLegend />
        </div>

        {cohort.isPending ? <Skeleton label="Loading the ward" variant="rows" rows={5} /> : null}
        {cohort.isError ? (
          <div className="sheet-pad">
            <ErrorState error={cohort.error} title="The ward could not be loaded." onRetry={() => void cohort.refetch()} />
          </div>
        ) : null}
        {cohort.data && patients.length === 0 ? <EmptyWard /> : null}
        {cohort.data && patients.length > 0 && shown === 0 ? (
          <Empty>
            <p>No patient matches these filters.</p>
            <button type="button" className="button" onClick={() => setFilter(EMPTY_FILTER)}>
              Clear filters
            </button>
          </Empty>
        ) : null}

        {cohort.data && shown > 0 ? (
          <>
            <div className="ward-cols" aria-hidden="true">
              <span>Patient</span>
              <span>Now</span>
              <span>Next hour</span>
              <span>Assessment</span>
              <span>Alerts</span>
            </div>
            {sections.map((s) =>
              s.patients.length === 0 ? (
                <h2 key={s.status} className="ward-section-empty">
                  {s.label}: none{filtered ? ' matching' : ''}
                </h2>
              ) : (
                <section key={s.status} className="ward-section" aria-labelledby={`section-${s.status}`}>
                  <h2 id={`section-${s.status}`}>
                    {s.label} <span className="count num">{s.patients.length}</span>
                  </h2>
                  <ul className="ward-rows">
                    {s.patients.map((p) => (
                      <WardRow key={p.patient_id} p={p} />
                    ))}
                  </ul>
                </section>
              ),
            )}
          </>
        ) : null}
      </div>
    </>
  );
}
