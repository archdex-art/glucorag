/**
 * What Today says to a person, derived from `GET /me/status`. Words follow the backend's
 * decision (status and risk flags); people read "low"/"high", never "hypo"/"hyper", and the
 * alert quantile is "the lower/upper edge of your forecast band".
 */

import type { MeStatus, ModelFacts, RiskFlag, Unit } from '../api/types';
import { formatDateTime, formatElapsed, tryParseApiTime } from './time';
import { formatGlucose, formatGlucoseUnit } from './units';
import type { Warmup } from './warmup';

export type TodayKind =
  | 'low'
  | 'high'
  | 'in_range'
  | 'collecting'
  /** Latest reading older than the gap limit, but recent. */
  | 'stale'
  /** Latest reading a day or more old, typically an old import. */
  | 'ended'
  /** Recent readings, but a gap inside the look-back window suspends forecasting. */
  | 'gap'
  | 'no_readings';

/** From this age on, stale data reads as "your data ends …" with its past forecast. */
export const ENDED_AFTER_MIN = 24 * 60;

export interface PersonStatus {
  kind: TodayKind;
  /** The one-line answer at the top of Today. */
  sentence: string;
  /** Risk flags, earliest first. */
  flags: RiskFlag[];
  /** The earliest flag is high severity: give it "soon" emphasis. */
  urgent: boolean;
  /** The stored forecast was made from the latest reading but is no longer current. */
  pastForecast: boolean;
}

export function sortFlags(flags: readonly RiskFlag[]): RiskFlag[] {
  return [...flags].sort((a, b) => a.horizon_min - b.horizon_min || (a.type === 'hypo' ? -1 : 1));
}

export function personStatus(s: MeStatus): PersonStatus {
  const row = s.status;
  const flags = sortFlags(row.risk);
  const last = tryParseApiTime(row.last_reading);
  const t0 = tryParseApiTime(s.prediction?.t0);
  const pastForecast = !s.fresh && last !== null && t0 !== null && t0 === last;
  const base = { flags, urgent: false, pastForecast };
  switch (row.status) {
    case 'at_risk': {
      const first = flags[0];
      if (!first) return { ...base, kind: 'in_range', sentence: 'In range for the next hour' };
      const low = first.type === 'hypo';
      const word = low ? 'Low' : 'High';
      // Same inclusive comparisons as the backend alert rule (<= hypo, >= hyper).
      const value = row.last_glucose_mg_dl;
      const pastNow =
        value !== null && (low ? value <= s.model.hypo_mg_dl : value >= s.model.hyper_mg_dl);
      return {
        ...base,
        kind: low ? 'low' : 'high',
        sentence: pastNow ? `${word} now` : `${word} predicted in ${first.horizon_min} min`,
        urgent: first.severity === 'high',
      };
    }
    case 'ok': {
      // The whole band stays in range, but the reading itself may be outside it: say both,
      // so the sentence never contradicts the coloured value beside it.
      const value = row.last_glucose_mg_dl;
      const firstHorizon = row.forecast?.horizons[0];
      const back = firstHorizon !== undefined ? `back in range within ${firstHorizon} min` : 'back in range soon';
      if (value !== null && value >= s.model.hyper_mg_dl) return { ...base, kind: 'high', sentence: `High now, ${back}` };
      if (value !== null && value <= s.model.hypo_mg_dl) return { ...base, kind: 'low', sentence: `Low now, ${back}` };
      return { ...base, kind: 'in_range', sentence: 'In range for the next hour' };
    }
    case 'warming_up':
      return { ...base, kind: 'collecting', sentence: 'Collecting readings' };
    case 'no_data':
      return { ...base, kind: 'no_readings', sentence: 'No readings yet' };
    case 'data_gap': {
      const age = row.minutes_since_last ?? 0;
      const kind: TodayKind = !row.stale ? 'gap' : age >= ENDED_AFTER_MIN ? 'ended' : 'stale';
      return { ...base, kind, sentence: 'No current forecast' };
    }
  }
}

/** "hour" for 60, "2 hours" for 120, else "45 min" / "1 h 30 min". */
function span(minutes: number): string {
  if (minutes === 60) return 'hour';
  if (minutes % 60 === 0) return `${minutes / 60} hours`;
  return formatElapsed(minutes);
}

/** "3 more needed, about 45 min." */
function readingsToGo(w: Warmup | null): string {
  if (!w || w.needed <= 0) return 'The next reading should bring one.';
  return `${w.needed} more ${w.needed === 1 ? 'reading' : 'readings'} needed, about ${formatElapsed(w.minutes)}.`;
}

/**
 * The sentence for one risk flag:
 * "The lower edge of your forecast band reaches 64 mg/dL in 25 min, 6 below 70."
 */
export function riskDetail(f: RiskFlag, unit: Unit, model: Pick<ModelFacts, 'hypo_mg_dl' | 'hyper_mg_dl'>): string {
  const low = f.type === 'hypo';
  const threshold = low ? model.hypo_mg_dl : model.hyper_mg_dl;
  const edge = low ? 'lower' : 'upper';
  const beyond = Math.abs(f.value_mg_dl - threshold);
  const side = low ? 'below' : 'above';
  let text =
    `The ${edge} edge of your forecast band reaches ${formatGlucoseUnit(f.value_mg_dl, unit)} in ${f.horizon_min} min` +
    (formatGlucose(beyond, unit) === formatGlucose(0, unit)
      ? `, at ${formatGlucose(threshold, unit)}.`
      : `, ${formatGlucose(beyond, unit)} ${side} ${formatGlucose(threshold, unit)}.`);
  if (formatGlucose(f.extreme_mg_dl, unit) !== formatGlucose(f.value_mg_dl, unit)) {
    text += ` It goes as ${low ? 'low' : 'high'} as ${formatGlucoseUnit(f.extreme_mg_dl, unit)} within the hour.`;
  }
  return text;
}

/** The explanation under the sentence when there is no current forecast; null otherwise. */
export function noForecastDetail(p: PersonStatus, s: MeStatus, warm: Warmup | null): string | null {
  const row = s.status;
  const model = s.model;
  switch (p.kind) {
    case 'collecting':
      return `Forecasts start once there are ${span(model.lookback_min)} of readings. ${readingsToGo(warm)}`;
    case 'gap':
      return (
        `Your recent readings have a gap of more than ${span(model.data_gap_min).replace(/^hour$/, 'an hour')}. ` +
        `Forecasts restart after ${span(model.lookback_min)} of readings. ${readingsToGo(warm)}`
      );
    case 'stale':
      return (
        `No forecast: your latest reading is ${formatElapsed(row.minutes_since_last)} old. ` +
        `Forecasts need a reading within the last ${span(model.data_gap_min)}. Add a reading or import a newer file.`
      );
    case 'ended': {
      const ends = `Your data ends ${formatDateTime(tryParseApiTime(row.last_reading))}.`;
      return p.pastForecast
        ? `${ends} The forecast below was made then. For a current forecast, add a reading or import a newer file.`
        : `${ends} For a forecast, add a reading or import a newer file.`;
    }
    default:
      return null;
  }
}
