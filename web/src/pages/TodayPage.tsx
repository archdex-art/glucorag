import { Plus } from 'lucide-react';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useMe, useMeAccuracy, useMeAlerts, useMeHistory, useMeStatus } from '../api/hooks';
import type { MeAccuracy, MeHistory, MeInfo, MeStatus, StoredAlert } from '../api/types';
import { useAccount } from '../auth/context';
import { AddDataChoices } from '../components/AddDataChoices';
import { GlucoseFigure } from '../components/GlucoseFigure';
import { ForecastTable } from '../components/ForecastTable';
import { PageHeader } from '../components/PageHeader';
import { PersonAlerts } from '../components/PersonAlerts';
import { RangesSummary } from '../components/RangesSummary';
import { Readout } from '../components/Readout';
import { ErrorState, Skeleton } from '../components/States';
import { StatusIcon } from '../components/StatusIcon';
import { ICON } from '../components/icon';
import { useRefresh } from '../components/refresh';
import { todayMode } from '../lib/access';
import { accuracyLine } from '../lib/accuracy';
import { buildFan, mergeChartRows, readingSeries } from '../lib/forecast';
import { noForecastDetail, personStatus, type PersonStatus } from '../lib/personStatus';
import { sourcePhrase } from '../lib/source';
import { HOUR, formatElapsed, formatWhen, parseApiTime, tryParseApiTime } from '../lib/time';
import { timeInRanges } from '../lib/tir';
import { formatGlucose } from '../lib/units';
import { warmup } from '../lib/warmup';

// 3 h of readings + the 1 h forecast: the answer gets a quarter of the width, and the trend
// that produced it stays visible. Longer windows live on History.
const CHART_HOURS = 3;
const ALERTS_SHOWN = 5;

function ago(minutes: number | null): string {
  if (minutes === null) return '';
  return minutes < 1 ? 'just now' : `${formatElapsed(minutes)} ago`;
}

/** The answer: one sentence, then why. */
function StatusSentence({ p, s, warmText }: { p: PersonStatus; s: MeStatus; warmText: string | null }) {
  const first = p.flags[0];
  // The value's own side when no flag fired (out of range now, no low or high likely).
  const side = first?.type ?? (p.kind === 'high' ? 'hyper' : p.kind === 'low' ? 'hypo' : undefined);
  const tone = side ? `tone-${side}` : p.kind === 'in_range' ? 'status-ok' : 'tone-neutral';
  return (
    <div className="status-block">
      <h2 className={`status-sentence ${tone}${p.urgent ? ' is-urgent' : ''}`}>
        <StatusIcon status={side ? 'at_risk' : s.status.status} risk={side} />
        <span>{p.sentence}</span>
      </h2>
      {p.details.length ? (
        <ul className="status-detail">
          {p.details.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      ) : null}
      {warmText ? <p className="status-detail">{warmText}</p> : null}
    </div>
  );
}

interface Ready {
  me: MeInfo;
  s: MeStatus;
  history: MeHistory;
  alerts: StoredAlert[] | undefined;
  alertsError: unknown;
  retryAlerts: () => void;
  /** Absent while loading or when it failed: the line is simply not shown. */
  accuracy: MeAccuracy | undefined;
}

function TodayContent({ me, s, history, alerts, alertsError, retryAlerts, accuracy }: Ready) {
  const unit = me.unit;
  const row = s.status;
  const p = personStatus(s, unit);
  const now = tryParseApiTime(s.now);
  const accuracyText = accuracy ? accuracyLine(accuracy, unit) : null;

  const view = useMemo(() => {
    const readings = history.readings.map((r) => ({ t: parseApiTime(r.timestamp), v: r.glucose_mg_dl }));
    const last = tryParseApiTime(row.last_reading);
    const warm = warmup(
      readings.map((r) => r.t),
      { interval_min: s.model.interval_min, lookback_min: s.model.lookback_min, data_gap_min: s.model.data_gap_min },
    );
    const showFan = Boolean(s.prediction) && (s.fresh || p.pastForecast);
    const series = readingSeries(history.readings, s.model.data_gap_min);
    const t0 = showFan && s.prediction ? parseApiTime(s.prediction.t0) : null;
    const atT0 = t0 !== null ? series.find((r) => r.t === t0)?.glucose : null;
    const fan = showFan && s.prediction ? buildFan(s.prediction, atT0) : [];
    const end = Math.max(last ?? 0, fan[fan.length - 1]?.t ?? 0);
    const start = (last ?? end) - CHART_HOURS * HOUR;
    const tir = last !== null ? timeInRanges(readings, last - 24 * HOUR, last) : null;
    return { rows: mergeChartRows(series.filter((r) => r.t >= start), fan), start, end, t0, fan: fan.length > 0, tir, warm, last };
  }, [history, row.last_reading, s, p.pastForecast]);

  const warmText = noForecastDetail(p, s, view.warm);
  const t0Label = view.t0 === null ? '' : s.fresh ? 'Now' : `Forecast made at ${formatWhen(view.t0, now)}`;
  const chartSummary =
    `Chart of your readings over the ${CHART_HOURS} hours to ${formatWhen(view.last, now)}` +
    (view.fan ? `, and the forecast for the hour after ${formatWhen(view.t0, now)}.` : '. No forecast is drawn.');

  return (
    <div className="sheet">
      <section className="sheet-section today-top" aria-label="Your glucose now and over the next hour">
        <div className="answer">
          <StatusSentence p={p} s={s} warmText={warmText} />
          <Readout
            layout="stack"
            audience="person"
            unit={unit}
            current={row.last_glucose_mg_dl}
            trend={row.trend_mg_dl_per_min}
            band={row.forecast}
            stale={row.stale}
            age={row.minutes_since_last !== null ? `Reading from ${formatWhen(view.last, now)}, ${ago(row.minutes_since_last)}` : null}
            noForecast={p.pastForecast ? 'See the past forecast' : 'No current forecast'}
          />
          {accuracyText ? <p className="caption today-accuracy">{accuracyText}</p> : null}
        </div>
        <div className="today-chart">
          <GlucoseFigure
            rows={view.rows}
            start={view.start}
            end={view.end}
            t0={view.t0}
            t0Label={t0Label}
            hypo={s.model.hypo_mg_dl}
            hyper={s.model.hyper_mg_dl}
            unit={unit}
            withFan={view.fan}
            summary={chartSummary}
          />
        </div>
      </section>

      {s.prediction && view.fan ? (
        <details className="sheet-section disclosure-section">
          <summary>{s.fresh ? 'Forecast in detail' : `Forecast made at ${formatWhen(view.t0, now)}, in detail`}</summary>
          <ForecastTable
            prediction={s.prediction}
            hypoQuantile={s.hypo_quantile}
            hyperQuantile={s.hyper_quantile}
            hypo={s.model.hypo_mg_dl}
            hyper={s.model.hyper_mg_dl}
            unit={unit}
            audience="person"
          />
        </details>
      ) : null}

      <section className="sheet-section" aria-labelledby="tir-heading">
        <h2 id="tir-heading">Time in ranges, last 24 hours</h2>
        {view.tir ? (
          <RangesSummary tir={view.tir} unit={unit} windowLabel="the last 24 hours" />
        ) : (
          <p className="muted">No readings in the last 24 hours of your data.</p>
        )}
      </section>

      <section className="sheet-section" aria-labelledby="alerts-heading">
        <div className="section-head">
          <h2 id="alerts-heading">Latest alerts</h2>
          <Link to="/history">All alerts in History</Link>
        </div>
        {alertsError ? <ErrorState error={alertsError} title="Your alerts could not be loaded." onRetry={retryAlerts} /> : null}
        {!alerts && !alertsError ? <Skeleton label="Loading alerts" rows={2} /> : null}
        {alerts && alerts.length === 0 ? (
          <p className="muted">
            No alerts yet. You get an alert when a low (at or below {formatGlucose(s.model.hypo_mg_dl, unit)}) or a high (at or
            above {formatGlucose(s.model.hyper_mg_dl, unit)} {unit}) looks likely within the hour.
          </p>
        ) : null}
        {alerts && alerts.length ? <PersonAlerts alerts={alerts} unit={unit} today={now} /> : null}
      </section>
    </div>
  );
}

function TodaySkeleton() {
  return (
    <div className="sheet">
      <section className="sheet-section today-top" aria-busy="true">
        <div className="answer">
          <Skeleton label="Loading your forecast" rows={5} />
        </div>
        <div className="today-chart">
          <Skeleton label="Loading the chart" variant="block" rows={1} />
        </div>
      </section>
    </div>
  );
}

export function TodayPage() {
  const account = useAccount();
  const { paused } = useRefresh();
  const me = useMe();
  const hasReadings = me.data ? todayMode(me.data.readings.count) === 'forecast' : false;
  const status = useMeStatus(paused, hasReadings);
  const history = useMeHistory(24, paused, hasReadings);
  const alerts = useMeAlerts(ALERTS_SHOWN, paused, hasReadings);
  const accuracy = useMeAccuracy(paused, hasReadings);

  const last = status.data?.status.last_reading ?? null;
  const source = me.data ? sourcePhrase(account.email, last) : null;
  const minutes = status.data?.status.minutes_since_last ?? null;
  const updatedAt = Math.max(status.dataUpdatedAt, history.dataUpdatedAt);

  const header = (
    <PageHeader title="Today" refresh={hasReadings ? { updatedAt } : undefined}>
      {hasReadings ? (
        <div className="today-source">
          <p className="num">
            {minutes !== null ? `Last reading ${ago(minutes)}` : 'Loading your latest reading'}
            {source ? `, ${source}` : ''}
          </p>
          <Link className="button button-primary" to="/add">
            <Plus {...ICON} />
            Add reading
          </Link>
        </div>
      ) : null}
    </PageHeader>
  );

  if (me.isError) {
    return (
      <>
        {header}
        <div className="sheet sheet-pad">
          <ErrorState error={me.error} title="Your account could not be loaded." onRetry={() => void me.refetch()} />
        </div>
      </>
    );
  }
  if (me.data && !hasReadings) {
    return (
      <>
        {header}
        <div className="sheet sheet-pad">
          <h2 className="today-empty-title">No readings yet</h2>
          <p className="today-empty-lede">Add your data to see your next hour. The easiest way is live from your phone.</p>
          <AddDataChoices headingLevel={3} />
        </div>
      </>
    );
  }
  const failed = status.error ?? history.error;
  if (failed && !(status.data && history.data)) {
    return (
      <>
        {header}
        <div className="sheet sheet-pad">
          <ErrorState
            error={failed}
            title="Your forecast could not be loaded."
            onRetry={() => {
              void status.refetch();
              void history.refetch();
            }}
          />
        </div>
      </>
    );
  }
  if (!me.data || !status.data || !history.data) {
    return (
      <>
        {header}
        <TodaySkeleton />
      </>
    );
  }
  return (
    <>
      {header}
      <TodayContent
        me={me.data}
        s={status.data}
        history={history.data}
        alerts={alerts.data}
        alertsError={alerts.error}
        retryAlerts={() => void alerts.refetch()}
        accuracy={accuracy.data}
      />
    </>
  );
}
