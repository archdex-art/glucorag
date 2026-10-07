import { TriangleAlert } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { NotFoundError } from '../api/errors';
import { useAlerts, useCohort, useForecast, useHistory, useStats } from '../api/hooks';
import type { PatientRisk, RiskFlag } from '../api/types';
import { AlertRow } from '../components/AlertRow';
import { ForecastChart } from '../components/ForecastChart';
import { ForecastTable } from '../components/ForecastTable';
import { PageHeader } from '../components/PageHeader';
import { PriorityChip } from '../components/PriorityChip';
import { Readout } from '../components/Readout';
import { Empty, ErrorState, Skeleton } from '../components/States';
import { AlertTag, StatusIcon } from '../components/StatusIcon';
import { TimeInRanges } from '../components/TimeInRanges';
import { ICON } from '../components/icon';
import { useRefresh } from '../components/refresh';
import { sortAlertsNewestFirst } from '../lib/alerts';
import { buildFan, mergeChartRows, readingSeries } from '../lib/forecast';
import { fmtQuantile } from '../lib/format';
import { timeInRanges, TIR_ORDER } from '../lib/tir';
import { HOUR, formatElapsed, formatWhen, parseApiTime, toApiTime, tryParseApiTime } from '../lib/time';
import { STATUS_LABEL, earliestRisk, riskSentence } from '../lib/ward';
import { useMediaQuery } from '../lib/useMediaQuery';
import { LOW_BELOW, TARGET_MAX, ZONES } from '../lib/zones';

const WINDOWS = [
  { label: '6 h', ms: 6 * HOUR },
  { label: '24 h', ms: 24 * HOUR },
  { label: '3 d', ms: 72 * HOUR },
] as const;

function flagSentence(f: RiskFlag): string {
  // margin = distance of the most extreme value beyond the threshold.
  const threshold = f.type === 'hypo' ? f.extreme_mg_dl + f.margin_mg_dl : f.extreme_mg_dl - f.margin_mg_dl;
  return (
    `${riskSentence(f)}: the ${fmtQuantile(f.quantile)} forecast reaches ${Math.round(f.extreme_mg_dl)} mg/dL, ` +
    `${Math.round(f.margin_mg_dl)} ${f.type === 'hypo' ? 'below' : 'above'} ${Math.round(threshold)}.`
  );
}

function Assessment({ row, hypo, hyper }: { row: PatientRisk; hypo: number; hyper: number }) {
  if (row.stale || row.status === 'data_gap') {
    return (
      <p className="warning-line">
        <TriangleAlert {...ICON} />
        {row.minutes_since_last !== null ? `No reading for ${formatElapsed(row.minutes_since_last)}. ` : ''}
        The last forecast is out of date, so it raises no alerts.
      </p>
    );
  }
  if (row.risk.length) {
    return (
      <ul className="risk-sentences">
        {[...row.risk]
          .sort((a, b) => a.horizon_min - b.horizon_min)
          .map((f) => (
            <li key={f.type} className={`tone-${f.type}`}>
              <StatusIcon status="at_risk" risk={f.type} />
              {flagSentence(f)}
            </li>
          ))}
      </ul>
    );
  }
  const text: Record<string, string> = {
    ok: `No crossing of ${hypo} or ${hyper} mg/dL is forecast in the next hour.`,
    warming_up: 'Warming up (forecast starts after 2 h of readings).',
    no_data: 'No readings yet.',
  };
  return <p className="assessment-line">{text[row.status] ?? STATUS_LABEL[row.status]}</p>;
}

function WindowControl({ value, onChange }: { value: number; onChange: (ms: number) => void }) {
  const name = useId();
  return (
    <fieldset className="segmented">
      <legend className="visually-hidden">Time window</legend>
      {WINDOWS.map((w) => (
        <label key={w.label}>
          <input type="radio" name={name} checked={value === w.ms} onChange={() => onChange(w.ms)} />
          <span>{w.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

const RIBBONS = [
  ['ribbon-inner', 'q0.25–q0.75'],
  ['ribbon-mid', 'q0.10–q0.90'],
  ['ribbon-outer', 'q0.02–q0.98'],
] as const;

export function PatientPage() {
  const { id = '' } = useParams();
  const { paused } = useRefresh();
  const [windowMs, setWindowMs] = useState<number>(WINDOWS[0].ms);

  const cohort = useCohort(paused);
  const stats = useStats(paused);
  const row = cohort.data?.patients.find((p) => p.patient_id === id);
  // No stored prediction (no data, warming up): skip the request rather than collect a 404.
  const forecast = useForecast(id, paused, Boolean(row?.latest_t0));
  const alerts = useAlerts({ patient_id: id, limit: 50 }, paused);
  const narrow = useMediaQuery('(max-width: 599.98px)');

  const anchor = tryParseApiTime(row?.last_reading ?? forecast.data?.prediction.t0 ?? null);
  const since = anchor !== null ? toApiTime(anchor - windowMs) : null;
  const history = useHistory(id, since, paused);
  const today = tryParseApiTime(cohort.data?.as_of);

  const thresholds = stats.data?.thresholds;
  const hypo = thresholds?.hypo_mg_dl ?? LOW_BELOW;
  const hyper = thresholds?.hyper_mg_dl ?? TARGET_MAX;
  const gapMin = thresholds?.data_gap_min ?? 60;
  const noForecast = (row !== undefined && !row.latest_t0) || forecast.error instanceof NotFoundError;
  const fresh = row?.status === 'at_risk' || row?.status === 'ok';
  const windowLabel = WINDOWS.find((w) => w.ms === windowMs)?.label ?? '';

  const chart = useMemo(() => {
    if (anchor === null || !history.data) return null;
    const readings = readingSeries(history.data.readings, gapMin);
    const fc = forecast.data?.prediction;
    const t0 = fc ? parseApiTime(fc.t0) : null;
    const atT0 = t0 !== null ? readings.find((r) => r.t === t0)?.glucose : null;
    const fan = fc ? buildFan(fc, atT0) : [];
    const start = anchor - windowMs;
    const tir = timeInRanges(
      history.data.readings.map((r) => ({ t: parseApiTime(r.timestamp), v: r.glucose_mg_dl })),
      start,
      anchor,
    );
    return {
      rows: mergeChartRows(readings, fan),
      start,
      end: Math.max(anchor, fan[fan.length - 1]?.t ?? anchor),
      t0,
      tir,
    };
  }, [anchor, history.data, forecast.data, gapMin, windowMs]);

  const patientAlerts = useMemo(() => sortAlertsNewestFirst(alerts.data ?? []), [alerts.data]);

  const breadcrumb = (
    <nav aria-label="Breadcrumb" className="breadcrumb">
      <ol>
        <li>
          <Link to="/ward">Ward</Link>
        </li>
        <li aria-current="page">Patient {id}</li>
      </ol>
    </nav>
  );

  if (cohort.isPending) {
    return (
      <>
        <PageHeader title={`Patient ${id}`} breadcrumb={breadcrumb} />
        <div className="sheet">
          <Skeleton label="Loading the patient" variant="block" rows={3} />
        </div>
      </>
    );
  }
  if (cohort.isError) {
    return (
      <>
        <PageHeader title={`Patient ${id}`} breadcrumb={breadcrumb} />
        <div className="sheet sheet-pad">
          <ErrorState error={cohort.error} title="The patient could not be loaded." onRetry={() => void cohort.refetch()} />
        </div>
      </>
    );
  }
  if (!row) {
    return (
      <>
        <PageHeader title={`Patient ${id}`} breadcrumb={breadcrumb} />
        <div className="sheet">
          <Empty>
            <p className="state-title">Patient {id} is not registered.</p>
            <p>
              Check the ID, or go back to the <Link to="/ward">Ward</Link>.
            </p>
          </Empty>
        </div>
      </>
    );
  }

  const flag = earliestRisk(row);
  const lastReading = tryParseApiTime(row.last_reading);
  const tir = chart?.tir ?? null;
  const lowShare = tir ? tir.pct.very_low + tir.pct.low : 0;

  return (
    <>
      <PageHeader
        title={`Patient ${row.patient_id}`}
        breadcrumb={breadcrumb}
        refresh={{ updatedAt: Math.max(cohort.dataUpdatedAt, forecast.dataUpdatedAt, history.dataUpdatedAt) }}
      >
        <div className="patient-facts">
          <span>{row.diabetes_type ?? 'Type not recorded'}</span>
          <span className="fact-status">
            <StatusIcon status={row.status} risk={flag?.type} />
            {STATUS_LABEL[row.status]}
          </span>
          <PriorityChip severity={row.severity} risk={flag?.type} />
          {row.active_alerts.length ? (
            <span className="fact-alerts">
              <span className="visually-hidden">Active alerts:</span>
              {row.active_alerts.map((a) => (
                <AlertTag key={a} type={a} />
              ))}
            </span>
          ) : null}
          {lastReading !== null ? (
            <span className="num muted">Last reading {formatWhen(lastReading, today)}</span>
          ) : null}
        </div>
      </PageHeader>

      <div className="sheet">
        <section className="sheet-section" aria-label="Current value and forecast">
          <Readout
            current={row.last_glucose_mg_dl}
            trend={row.trend_mg_dl_per_min}
            band={row.forecast}
            stale={row.status !== 'at_risk' && row.status !== 'ok'}
          />
          <Assessment row={row} hypo={hypo} hyper={hyper} />
        </section>

        <section className="sheet-section" aria-labelledby="chart-heading">
          <div className="section-head">
            <h2 id="chart-heading">Glucose and forecast</h2>
            {anchor !== null ? <WindowControl value={windowMs} onChange={setWindowMs} /> : null}
          </div>
          {noForecast ? (
            <p className="info-line">
              Forecast starts after 2 hours of readings.
            </p>
          ) : null}
          {forecast.isError && !noForecast ? (
            <ErrorState error={forecast.error} title="The forecast could not be loaded." onRetry={() => void forecast.refetch()} />
          ) : null}
          {history.isError ? (
            <ErrorState error={history.error} title="The readings could not be loaded." onRetry={() => void history.refetch()} />
          ) : null}
          {anchor !== null && !chart && history.isPending ? <Skeleton label="Loading readings" variant="block" rows={1} /> : null}
          {chart ? (
            <figure className="chart">
              <div className="chart-plot">
                <ForecastChart
                  rows={chart.rows}
                  start={chart.start}
                  end={chart.end}
                  t0={chart.t0}
                  t0Label={fresh ? 'Now' : 'Last forecast'}
                  low={hypo}
                  high={hyper}
                  height={narrow ? 260 : 320}
                  maxTicks={narrow ? 4 : 8}
                />
              </div>
              <figcaption className="chart-legend">
                <span className="key key-reading">Readings</span>
                {forecast.data ? (
                  <>
                    <span className="key key-median">Median forecast</span>
                    {RIBBONS.map(([cls, label]) => (
                      <span key={cls} className={`key ${cls}`}>
                        {label}
                      </span>
                    ))}
                  </>
                ) : null}
                <span className="key-note num">
                  Rules at {hypo} and {hyper} mg/dL; backgrounds show the glucose zones.
                </span>
              </figcaption>
            </figure>
          ) : null}
        </section>

        {chart ? (
          <section className="sheet-section" aria-labelledby="tir-heading">
            <h2 id="tir-heading">Time in ranges, last {windowLabel}</h2>
            {tir ? (
              <TimeInRanges
                title={`Time in ranges, last ${windowLabel}`}
                segments={TIR_ORDER.map((z) => {
                  const zone = ZONES.find((x) => x.key === z);
                  return { zone: z, label: zone?.label ?? z, range: zone?.range ?? '', pct: tir.pct[z] };
                })}
                caption={
                  <>
                    Target: over 70% in range, under 4% low. This window: {tir.pct.target}% in range, {lowShare}% low, from{' '}
                    {tir.count} readings.
                  </>
                }
              />
            ) : (
              <p className="muted">No readings in this window.</p>
            )}
          </section>
        ) : null}

        {forecast.data ? (
          <details className="sheet-section disclosure-section">
            <summary>All forecast quantiles</summary>
            <ForecastTable
              prediction={forecast.data.prediction}
              hypoQuantile={forecast.data.hypo_quantile}
              hyperQuantile={forecast.data.hyper_quantile}
              hypo={hypo}
              hyper={hyper}
            />
          </details>
        ) : null}

        <section className="sheet-section" aria-labelledby="alerts-heading">
          <div className="section-head">
            <h2 id="alerts-heading">Alerts</h2>
            <Link to="/alerts">All alerts</Link>
          </div>
          {alerts.isPending ? <Skeleton label="Loading alerts" rows={3} /> : null}
          {alerts.isError ? <ErrorState error={alerts.error} title="The alerts could not be loaded." onRetry={() => void alerts.refetch()} /> : null}
          {alerts.data && patientAlerts.length === 0 ? <p className="muted">No alerts raised for this patient.</p> : null}
          {patientAlerts.length ? (
            <ul className="alert-list">
              {patientAlerts.map((a) => (
                <AlertRow key={a.id} alert={a} showPatient={false} today={today} />
              ))}
            </ul>
          ) : null}
        </section>
      </div>
    </>
  );
}
