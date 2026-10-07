import { useId, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMe, useMeAlerts, useMeHistory, useMeStatus } from '../api/hooks';
import { GlucoseFigure } from '../components/GlucoseFigure';
import { PageHeader } from '../components/PageHeader';
import { PersonAlerts } from '../components/PersonAlerts';
import { RangesSummary } from '../components/RangesSummary';
import { ErrorState, Skeleton } from '../components/States';
import { useRefresh } from '../components/refresh';
import { mergeChartRows, readingSeries } from '../lib/forecast';
import { fmtNumber } from '../lib/format';
import { coveragePercent, glucoseStats } from '../lib/stats';
import { HOUR, formatDateTime, parseApiTime, tryParseApiTime } from '../lib/time';
import { timeInRanges } from '../lib/tir';
import { formatGlucose } from '../lib/units';

const WINDOWS = [
  { hours: 24, label: '24 h', long: 'the last 24 hours' },
  { hours: 72, label: '3 d', long: 'the last 3 days' },
  { hours: 168, label: '7 d', long: 'the last 7 days' },
  { hours: 336, label: '14 d', long: 'the last 14 days' },
] as const;

type Window = (typeof WINDOWS)[number];

function WindowControl({ value, onChange }: { value: Window; onChange: (w: Window) => void }) {
  const name = useId();
  return (
    <fieldset className="segmented">
      <legend className="visually-hidden">Time window</legend>
      {WINDOWS.map((w) => (
        <label key={w.hours}>
          <input type="radio" name={name} checked={value.hours === w.hours} onChange={() => onChange(w)} />
          <span>{w.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

export function HistoryPage() {
  const { paused } = useRefresh();
  const [win, setWin] = useState<Window>(WINDOWS[0]);
  const me = useMe();
  const hasReadings = (me.data?.readings.count ?? 0) > 0;
  const history = useMeHistory(win.hours, paused, hasReadings);
  const status = useMeStatus(paused, hasReadings);
  const alerts = useMeAlerts(500, paused, hasReadings);
  const unit = me.data?.unit ?? 'mg/dL';
  const model = me.data?.model;

  const view = useMemo(() => {
    if (!history.data || !model || !history.data.until) return null;
    const end = parseApiTime(history.data.until);
    const start = end - win.hours * HOUR;
    const points = history.data.readings.map((r) => ({ t: parseApiTime(r.timestamp), v: r.glucose_mg_dl }));
    const inWindow = points.filter((r) => r.t >= start && r.t <= end);
    return {
      start,
      end,
      rows: mergeChartRows(readingSeries(history.data.readings, model.data_gap_min), []),
      tir: timeInRanges(points, start, end),
      stats: glucoseStats(inWindow.map((r) => r.v)),
      coverage: coveragePercent(inWindow.length, win.hours * 60, model.interval_min),
    };
  }, [history.data, model, win.hours]);

  const windowAlerts = useMemo(() => {
    if (!view || !alerts.data) return [];
    return alerts.data.filter((a) => {
      const t = tryParseApiTime(a.t_raised);
      return t !== null && t >= view.start && t <= view.end;
    });
  }, [alerts.data, view]);

  const today = tryParseApiTime(status.data?.now);
  const header = (
    <PageHeader title="History" refresh={hasReadings ? { updatedAt: history.dataUpdatedAt } : undefined}>
      {hasReadings ? (
        <div className="history-controls">
          <WindowControl value={win} onChange={setWin} />
          {view ? (
            <p className="num muted">
              {formatDateTime(view.start)} to {formatDateTime(view.end)}
            </p>
          ) : null}
        </div>
      ) : null}
    </PageHeader>
  );

  if (me.isError || history.isError) {
    const err = me.error ?? history.error;
    return (
      <>
        {header}
        <div className="sheet sheet-pad">
          <ErrorState
            error={err}
            title="Your history could not be loaded."
            onRetry={() => {
              void me.refetch();
              void history.refetch();
            }}
          />
        </div>
      </>
    );
  }
  if (me.data && !hasReadings) {
    return (
      <>
        {header}
        <div className="sheet sheet-pad prose-block">
          <h2>No readings yet</h2>
          <p>
            Your history fills in as readings arrive. <Link to="/add">Add data</Link> to start.
          </p>
        </div>
      </>
    );
  }
  if (!view || !me.data) {
    return (
      <>
        {header}
        <div className="sheet">
          <section className="sheet-section">
            <Skeleton label="Loading your history" variant="block" rows={1} />
          </section>
          <section className="sheet-section">
            <Skeleton label="Loading statistics" rows={3} />
          </section>
        </div>
      </>
    );
  }

  const st = view.stats;
  return (
    <>
      {header}
      <div className="sheet">
        <section className="sheet-section" aria-labelledby="readings-heading">
          <h2 id="readings-heading">Readings, {win.long}</h2>
          <GlucoseFigure
            rows={view.rows}
            start={view.start}
            end={view.end}
            t0={null}
            t0Label=""
            hypo={me.data.model.hypo_mg_dl}
            hyper={me.data.model.hyper_mg_dl}
            unit={unit}
            withFan={false}
            summary={`Chart of your readings from ${formatDateTime(view.start)} to ${formatDateTime(view.end)}.`}
          />
          <p className="caption history-note">The window ends at your latest reading, so older imports still show.</p>
        </section>

        <section className="sheet-section" aria-labelledby="stats-heading">
          <h2 id="stats-heading">Statistics</h2>
          {st ? (
            <dl className="stats">
              <div>
                <dt>Average</dt>
                <dd>
                  <span className="stat-value num">{formatGlucose(st.mean, unit)}</span> <span className="unit">{unit}</span>
                </dd>
              </div>
              <div>
                <dt>GMI</dt>
                <dd>
                  <span className="stat-value num">{fmtNumber(st.gmi)}</span> <span className="unit">%</span>
                  <span className="stat-note">Estimates a lab HbA1c from the average.</span>
                </dd>
              </div>
              <div>
                <dt>Variability (CV)</dt>
                <dd>
                  <span className="stat-value num">{fmtNumber(st.cv)}</span> <span className="unit">%</span>
                  <span className="stat-note">Target 36% or less.</span>
                </dd>
              </div>
              <div>
                <dt>Readings</dt>
                <dd>
                  <span className="stat-value num">{st.count.toLocaleString('en-US')}</span>
                </dd>
              </div>
              <div>
                <dt>Coverage</dt>
                <dd>
                  <span className="stat-value num">{Math.round(view.coverage)}</span> <span className="unit">%</span>
                  <span className="stat-note">
                    Of the readings a sensor takes every {me.data.model.interval_min} min.
                  </span>
                </dd>
              </div>
            </dl>
          ) : (
            <p className="muted">No readings in this window.</p>
          )}
          {st && st.count < 2 ? <p className="caption">Variability needs at least two readings.</p> : null}
        </section>

        <section className="sheet-section" aria-labelledby="tir-heading">
          <h2 id="tir-heading">Time in ranges</h2>
          {view.tir ? <RangesSummary tir={view.tir} unit={unit} windowLabel={win.long} /> : <p className="muted">No readings in this window.</p>}
        </section>

        <section className="sheet-section" aria-labelledby="alerts-heading">
          <h2 id="alerts-heading">Alerts, {win.long}</h2>
          {alerts.isError ? <ErrorState error={alerts.error} title="Your alerts could not be loaded." onRetry={() => void alerts.refetch()} /> : null}
          {alerts.isPending ? <Skeleton label="Loading alerts" rows={2} /> : null}
          {alerts.data && windowAlerts.length === 0 ? <p className="muted">No alerts in this window.</p> : null}
          {windowAlerts.length ? <PersonAlerts alerts={windowAlerts} unit={unit} today={today} /> : null}
        </section>
      </div>
    </>
  );
}
