/**
 * How close forecasts came to the readings that followed: a person's one line on Today, and the
 * staff "Live accuracy" figures on the Model page.
 */

import type { AccuracyWarning, HorizonAccuracy, MeAccuracy, Unit } from '../api/types';
import { fmtNumber } from './format';
import { formatGlucose, formatGlucoseUnit, toMgDl, unitDigits } from './units';

/**
 * "Over the last 7 days, your 30-minute forecast was usually within 11 mg/dL." Null until
 * enough forecasts have been checked. An error below the display precision shows as the
 * smallest step ("within 0.1 mmol/L"), never "within 0".
 */
export function accuracyLine(a: MeAccuracy, unit: Unit): string | null {
  const error = a.median_abs_error_mg_dl;
  if (error === null || a.count < a.min_count) return null;
  const step = toMgDl(10 ** -unitDigits(unit), unit);
  const shown = Number(formatGlucose(error, unit)) > 0 ? error : step;
  return `Over the last ${a.days} days, your ${a.horizon_min}-minute forecast was usually within ${formatGlucoseUnit(shown, unit)}.`;
}

/** "Last 7 days' 30-min RMSE is 24.1 mg/dL, 38% above the evaluation's 17.5 mg/dL." */
export function accuracyWarningText(w: AccuracyWarning): string {
  const above = Math.round((w.ratio - 1) * 100);
  return (
    `Last 7 days' ${w.horizon_min}-min RMSE is ${fmtNumber(w.rmse_7d_mg_dl, 1)} mg/dL, ` +
    `${above}% above the evaluation's ${fmtNumber(w.reference_rmse_mg_dl, 1)} mg/dL.`
  );
}

/** A coverage fraction as a whole percentage, "—" when there is nothing to cover. */
export function fmtCoverage(fraction: number | null): string {
  return fraction === null ? '—' : `${Math.round(fraction * 100)}%`;
}

/** The entry for one horizon, if the service reported it. */
export function atHorizon(rows: readonly HorizonAccuracy[], horizon: number): HorizonAccuracy | null {
  return rows.find((r) => r.horizon_min === horizon) ?? null;
}

/**
 * An SVG path through `values` spread evenly across `width`, scaled so `max` sits at the top and
 * 0 at the bottom of `height`. Missing values break the line instead of bridging the gap; a
 * value with no neighbour becomes a zero-length segment, which a round line cap draws as a dot.
 */
export function sparkPath(values: readonly (number | null)[], width: number, height: number, max: number): string {
  if (!values.length || !(max > 0)) return '';
  const present = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v);
  const dx = values.length > 1 ? width / (values.length - 1) : 0;
  const parts: string[] = [];
  values.forEach((v, i) => {
    if (!present(v)) return;
    const x = values.length > 1 ? i * dx : width / 2;
    const y = height - (Math.min(Math.max(v, 0), max) / max) * height;
    const joined = present(values[i - 1]);
    parts.push(`${joined ? 'L' : 'M'}${Number(x.toFixed(2))} ${Number(y.toFixed(2))}`);
    if (!joined && !present(values[i + 1])) parts.push('h0');
  });
  return parts.join(' ');
}
