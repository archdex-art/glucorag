import type { UseQueryResult } from '@tanstack/react-query';
import { TriangleAlert } from 'lucide-react';
import type { AccuracyWindows, DailyAccuracy, ModelAccuracy } from '../api/types';
import { accuracyWarningText, atHorizon, fmtCoverage, sparkPath } from '../lib/accuracy';
import { fmtInt, fmtNumber } from '../lib/format';
import { formatApiTime, formatDayMonth, tryParseApiTime } from '../lib/time';
import { ErrorState, Skeleton } from './States';
import { ICON } from './icon';

const WINDOWS: { key: keyof AccuracyWindows; label: string }[] = [
  { key: 'last_7_days', label: '7 days' },
  { key: 'last_30_days', label: '30 days' },
];

/** The sparkline's drawing box; it stretches to the column width. */
const SPARK = { w: 300, h: 56 } as const;
/** The daily RMSE line follows this horizon. */
const SPARK_HORIZON = 30;

interface Scope {
  key: string;
  label: string;
  note?: string;
  windows: AccuracyWindows;
}

const mgdl = (v: number | null) => (v === null ? '—' : fmtNumber(v, 1));

/** Horizons the service reported, ascending. */
function horizonsOf(scopes: readonly Scope[]): number[] {
  const all = scopes.flatMap((s) => WINDOWS.flatMap((w) => s.windows[w.key].map((r) => r.horizon_min)));
  return [...new Set(all)].sort((a, b) => a - b);
}

/** One row group per scope: each window at each horizon. */
function AccuracyTable({ scopes, caption }: { scopes: Scope[]; caption: string }) {
  const horizons = horizonsOf(scopes);
  const span = WINDOWS.length * horizons.length;
  return (
    <div className="table-wrap">
      <table className="table table-num live-accuracy-table">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Scope</th>
            <th scope="col">Window</th>
            <th scope="col">Horizon</th>
            <th scope="col">Matched</th>
            <th scope="col">RMSE</th>
            <th scope="col">MAE</th>
            <th scope="col">Median error</th>
            <th scope="col">In 50% band</th>
            <th scope="col">In 80% band</th>
          </tr>
        </thead>
        {scopes.map((s) => (
          <tbody key={s.key}>
            {WINDOWS.flatMap((w, wi) =>
              horizons.map((h, hi) => {
                const r = atHorizon(s.windows[w.key], h);
                return (
                  <tr key={`${w.key}-${h}`}>
                    {wi === 0 && hi === 0 ? (
                      <th scope="rowgroup" rowSpan={span} className="live-scope">
                        {s.label}
                        {s.note ? <span className="chip chip-clock">{s.note}</span> : null}
                      </th>
                    ) : null}
                    {hi === 0 ? <td rowSpan={horizons.length}>{w.label}</td> : null}
                    <td>{h} min</td>
                    <td>{fmtInt(r?.count ?? 0)}</td>
                    <td>{mgdl(r?.rmse_mg_dl ?? null)}</td>
                    <td>{mgdl(r?.mae_mg_dl ?? null)}</td>
                    <td>{mgdl(r?.median_abs_error_mg_dl ?? null)}</td>
                    <td>{fmtCoverage(r?.coverage_50 ?? null)}</td>
                    <td>{fmtCoverage(r?.coverage_80 ?? null)}</td>
                  </tr>
                );
              }),
            )}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function dayLabel(date: string | undefined): string {
  const t = tryParseApiTime(date);
  return t === null ? '' : formatDayMonth(t);
}

/** First and last day under a sparkline. */
function SparkAxis({ daily }: { daily: DailyAccuracy[] }) {
  return (
    <p className="spark-axis num" aria-hidden="true">
      <span>{dayLabel(daily[0]?.date)}</span>
      <span>{dayLabel(daily[daily.length - 1]?.date)}</span>
    </p>
  );
}

/** Daily RMSE at 30 min, with the evaluation's test RMSE as a dashed reference. */
function RmseSpark({ daily, reference }: { daily: DailyAccuracy[]; reference: number | null }) {
  const values = daily.map((d) => atHorizon(d.horizons, SPARK_HORIZON)?.rmse_mg_dl ?? null);
  const shown = values.filter((v): v is number => v !== null);
  const max = Math.max(...shown, reference ?? 0) * 1.15;
  const latest = [...daily].reverse().find((d) => atHorizon(d.horizons, SPARK_HORIZON)?.rmse_mg_dl != null);
  const latestValue = latest ? atHorizon(latest.horizons, SPARK_HORIZON)?.rmse_mg_dl ?? null : null;
  const label = shown.length
    ? `Daily ${SPARK_HORIZON}-minute RMSE over ${daily.length} days: ${fmtNumber(Math.min(...shown), 1)} to ${fmtNumber(Math.max(...shown), 1)} mg/dL; ` +
      `latest ${fmtNumber(latestValue, 1)} mg/dL on ${dayLabel(latest?.date)}.` +
      (reference !== null ? ` Evaluation ${fmtNumber(reference, 1)} mg/dL.` : '')
    : `No ${SPARK_HORIZON}-minute forecasts matched in the last ${daily.length} days.`;
  return (
    <figure className="spark">
      <figcaption className="spark-title">
        Daily {SPARK_HORIZON}-min RMSE
        <span className="spark-value num">{latestValue !== null ? `${fmtNumber(latestValue, 1)} mg/dL` : '—'}</span>
      </figcaption>
      <svg className="spark-svg" role="img" aria-label={label} viewBox={`0 0 ${SPARK.w} ${SPARK.h}`} preserveAspectRatio="none" width="100%" height={SPARK.h}>
        <line className="spark-base" x1={0} x2={SPARK.w} y1={SPARK.h} y2={SPARK.h} />
        {reference !== null && max > 0 ? (
          <line className="spark-reference" x1={0} x2={SPARK.w} y1={SPARK.h - (reference / max) * SPARK.h} y2={SPARK.h - (reference / max) * SPARK.h} />
        ) : null}
        <path className="spark-line" d={sparkPath(values, SPARK.w, SPARK.h, max)} />
      </svg>
      <SparkAxis daily={daily} />
      {reference !== null ? (
        <p className="chart-legend">
          <span className="key key-line">Live</span>
          <span className="key key-reference">Evaluation {fmtNumber(reference, 1)} mg/dL</span>
        </p>
      ) : null}
    </figure>
  );
}

const ALERT_KINDS = [
  { key: 'hypo', label: 'Hypo' },
  { key: 'hyper', label: 'Hyper' },
  { key: 'data_gap', label: 'Data gap' },
] as const;

/** Daily alerts as stacked bars: hypo, hyper and data gaps. */
function AlertSpark({ daily }: { daily: DailyAccuracy[] }) {
  const totals = daily.map((d) => d.alerts.hypo + d.alerts.hyper + d.alerts.data_gap);
  const max = Math.max(...totals, 0);
  const slot = daily.length ? SPARK.w / daily.length : 0;
  const sums = ALERT_KINDS.map((k) => daily.reduce((n, d) => n + d.alerts[k.key], 0));
  const label =
    `Alerts per day over ${daily.length} days: ` +
    ALERT_KINDS.map((k, i) => `${fmtInt(sums[i])} ${k.label.toLowerCase()}`).join(', ') +
    `; at most ${fmtInt(max)} on one day.`;
  return (
    <figure className="spark">
      <figcaption className="spark-title">
        Daily alerts
        <span className="spark-value num">{fmtInt(totals.reduce((a, b) => a + b, 0))} in total</span>
      </figcaption>
      <svg className="spark-svg" role="img" aria-label={label} viewBox={`0 0 ${SPARK.w} ${SPARK.h}`} preserveAspectRatio="none" width="100%" height={SPARK.h}>
        <line className="spark-base" x1={0} x2={SPARK.w} y1={SPARK.h} y2={SPARK.h} />
        {max > 0
          ? daily.flatMap((d, i) => {
              let top = SPARK.h;
              return ALERT_KINDS.map((k) => {
                const h = (d.alerts[k.key] / max) * SPARK.h;
                top -= h;
                return h > 0 ? (
                  <rect key={`${d.date}-${k.key}`} className={`spark-bar spark-${k.key}`} x={i * slot + slot * 0.15} width={slot * 0.7} y={top} height={h} />
                ) : null;
              });
            })
          : null}
      </svg>
      <SparkAxis daily={daily} />
      <p className="chart-legend">
        {ALERT_KINDS.map((k, i) => (
          <span key={k.key} className={`key key-${k.key}`}>
            {k.label} {fmtInt(sums[i])}
          </span>
        ))}
      </p>
    </figure>
  );
}

/** Staff: how live forecasts compare with the readings that followed, against the evaluation report. */
export function LiveAccuracy({ query }: { query: UseQueryResult<ModelAccuracy> }) {
  const a = query.data;
  const reference30 = a?.reference.find((r) => r.horizon_min === SPARK_HORIZON)?.rmse_mg_dl ?? null;
  const scopes: Scope[] = a
    ? [
        { key: 'cohort', label: 'All versions', windows: a.cohort },
        ...a.versions.map((v) => ({
          key: `v-${v.model_version}`,
          label: `Version ${v.model_version}`,
          note: v.model_version === a.model_version ? 'Serving' : undefined,
          windows: v,
        })),
      ]
    : [];
  const patients: Scope[] = a?.patients.map((p) => ({ key: `p-${p.patient_id}`, label: p.patient_id, windows: p })) ?? [];

  return (
    <>
      <section className="sheet-section" aria-labelledby="live-accuracy-heading">
        <h2 id="live-accuracy-heading">Live accuracy</h2>
        {query.isPending ? <Skeleton label="Loading live accuracy" rows={5} /> : null}
        {query.isError ? (
          <ErrorState error={query.error} title="Live accuracy could not be loaded." onRetry={() => void query.refetch()} />
        ) : null}
        {a ? (
          <>
            <p className="caption">
              Stored forecasts matched with the reading that arrived at their horizon, as of {formatApiTime(a.as_of)}. Serving
              model {a.model_version}. A warning shows when its 7-day RMSE is more than {fmtNumber(a.warning_ratio, 2)} times the
              evaluation&apos;s.
            </p>
            {a.warnings.map((w) => (
              <p key={w.horizon_min} className="warning-line">
                <TriangleAlert {...ICON} />
                {accuracyWarningText(w)}
              </p>
            ))}
            <AccuracyTable
              scopes={scopes}
              caption="Errors in mg/dL; lower is better. The 50% and 80% bands are q0.25–q0.75 and q0.10–q0.90: about 50% and 80% of readings should fall inside."
            />
            <div className="spark-grid">
              <RmseSpark daily={a.daily} reference={reference30} />
              <AlertSpark daily={a.daily} />
            </div>
          </>
        ) : null}
      </section>
      {patients.length ? (
        <details className="sheet-section disclosure-section">
          <summary>Live accuracy per patient</summary>
          <div className="disclosure-body">
            <AccuracyTable scopes={patients} caption="Each patient's forecasts, all versions. Errors in mg/dL." />
          </div>
        </details>
      ) : null}
    </>
  );
}
