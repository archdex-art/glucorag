import type { AlertType, RiskType, StoredAlert, Unit } from '../api/types';
import { asNumber, fmtQuantile } from './format';
import { formatElapsed, tryParseApiTime } from './time';
import { formatGlucoseUnit } from './units';

export const ALERT_LABEL: Record<AlertType, string> = {
  hypo: 'Hypo predicted',
  hyper: 'Hyper predicted',
  data_gap: 'Data gap',
};

export function sortAlertsNewestFirst(alerts: readonly StoredAlert[]): StoredAlert[] {
  return [...alerts].sort(
    (a, b) => (tryParseApiTime(b.t_raised) ?? 0) - (tryParseApiTime(a.t_raised) ?? 0) || b.id - a.id,
  );
}

/** What the alert says, as one sentence. */
export function alertSentence(a: StoredAlert): string {
  if (a.type === 'data_gap') {
    const gap = asNumber(a.details.minutes_since_last);
    if (gap !== null) return `No reading for ${formatElapsed(gap)}.`;
    const reason = typeof a.details.reason === 'string' ? a.details.reason : null;
    return reason ? `Forecast skipped: ${reason.charAt(0).toLowerCase()}${reason.slice(1)}.` : 'Readings stopped arriving.';
  }
  const q = asNumber(a.details.quantile);
  const extreme = asNumber(a.details.extreme_mg_dl) ?? asNumber(a.details.value_mg_dl);
  const margin = asNumber(a.details.margin_mg_dl);
  const when = a.horizon_min !== null ? `In ${a.horizon_min} min the` : 'The';
  const which = q !== null ? `${fmtQuantile(q)} forecast` : 'forecast';
  if (extreme === null) return `${when} ${which} crosses the ${a.type} threshold.`;
  const head = `${when} ${which} reaches ${Math.round(extreme)} mg/dL`;
  if (margin === null) return `${head}.`;
  // margin = distance of the extreme beyond the threshold, so the threshold follows from it.
  const threshold = a.type === 'hypo' ? extreme + margin : extreme - margin;
  if (Math.round(margin) === 0) return `${head}, at ${Math.round(threshold)}.`;
  return `${head}, ${Math.round(margin)} ${a.type === 'hypo' ? 'below' : 'above'} ${Math.round(threshold)}.`;
}

/** The same alerts in a person's words: low/high, never hypo/hyper. */
export const PERSON_ALERT_LABEL: Record<AlertType, string> = {
  hypo: 'Low predicted',
  hyper: 'High predicted',
  data_gap: 'Readings stopped',
};

/**
 * A predicted low or high in plain words: "Low likely in about 25 min (could reach 66 mg/dL)."
 * `horizon` is when the forecast first crosses the limit; `couldReach` the furthest it goes.
 */
export function likelySentence(type: RiskType, horizon: number | null, couldReach: number | null, unit: Unit): string {
  const head = `${type === 'hypo' ? 'Low' : 'High'} likely ${horizon !== null ? `in about ${horizon} min` : 'within the hour'}`;
  return couldReach !== null ? `${head} (could reach ${formatGlucoseUnit(couldReach, unit)}).` : `${head}.`;
}

/** "Low likely in about 25 min (could reach 66 mg/dL)." */
export function personAlertSentence(a: StoredAlert, unit: Unit): string {
  if (a.type === 'data_gap') {
    const gap = asNumber(a.details.minutes_since_last);
    return gap !== null ? `No reading for ${formatElapsed(gap)}, so forecasts paused.` : 'Forecasts paused for a gap in readings.';
  }
  const couldReach = asNumber(a.details.extreme_mg_dl) ?? asNumber(a.details.value_mg_dl);
  return likelySentence(a.type, a.horizon_min, couldReach, unit);
}
