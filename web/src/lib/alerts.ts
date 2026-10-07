import type { AlertType, StoredAlert, Unit } from '../api/types';
import { asNumber, fmtQuantile } from './format';
import { formatElapsed, tryParseApiTime } from './time';
import { formatGlucose, formatGlucoseUnit } from './units';

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

/** "The lower edge of your forecast band reached 64 mg/dL in 25 min, 6 below 70." */
export function personAlertSentence(a: StoredAlert, unit: Unit): string {
  if (a.type === 'data_gap') {
    const gap = asNumber(a.details.minutes_since_last);
    return gap !== null ? `No reading for ${formatElapsed(gap)}, so forecasts paused.` : 'Forecasts paused for a gap in readings.';
  }
  const edge = a.type === 'hypo' ? 'lower' : 'upper';
  const value = asNumber(a.details.value_mg_dl) ?? asNumber(a.details.extreme_mg_dl);
  const extreme = asNumber(a.details.extreme_mg_dl);
  const margin = asNumber(a.details.margin_mg_dl);
  const when = a.horizon_min !== null ? ` in ${a.horizon_min} min` : ' within the hour';
  if (value === null) return `The ${edge} edge of your forecast band crossed ${a.type === 'hypo' ? 'the low' : 'the high'} limit${when}.`;
  let text = `The ${edge} edge of your forecast band reached ${formatGlucoseUnit(value, unit)}${when}`;
  if (extreme !== null && margin !== null) {
    // margin is how far the extreme lies beyond the threshold, so the threshold follows from it.
    const threshold = a.type === 'hypo' ? extreme + margin : extreme - margin;
    const beyond = Math.abs(value - threshold);
    // A crossing smaller than the display precision reads "at 10.0", never "0.0 above 10.0".
    text +=
      formatGlucose(beyond, unit) === formatGlucose(0, unit)
        ? `, at ${formatGlucose(threshold, unit)}`
        : `, ${formatGlucose(beyond, unit)} ${a.type === 'hypo' ? 'below' : 'above'} ${formatGlucose(threshold, unit)}`;
  }
  return `${text}.`;
}
