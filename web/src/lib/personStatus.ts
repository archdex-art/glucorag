/**
 * What Today says to a person, derived from `GET /me/status`. Words follow the backend's
 * decision (status and risk flags) in plain language: people read "low"/"high", never
 * "hypo"/"hyper", and never the forecast's band or quantile names.
 */

import type { MeStatus, PatientRisk, RiskFlag, Unit } from '../api/types';
import { likelySentence } from './alerts';
import { formatDateTime, formatElapsed, tryParseApiTime } from './time';
import { TREND_LABEL, trendOf } from './trend';
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
  /** Lines under the answer: what else is likely within the hour. */
  details: string[];
  /** Risk flags, earliest first. */
  flags: RiskFlag[];
  /** The earliest flag is high severity: give it "soon" emphasis. */
  urgent: boolean;
  /** The stored forecast was made from the latest reading but is no longer current. */
  pastForecast: boolean;
}

/** The headline's look-ahead: "Likely about 185 in 30 min". */
const AHEAD_MIN = 30;

export function sortFlags(flags: readonly RiskFlag[]): RiskFlag[] {
  return [...flags].sort((a, b) => a.horizon_min - b.horizon_min || (a.type === 'hypo' ? -1 : 1));
}

/** "198 mg/dL, steady. Likely about 185 in 30 min." */
function nowAndAhead(row: PatientRisk, value: number, unit: Unit): string {
  const trend = row.trend_mg_dl_per_min !== null ? `, ${TREND_LABEL[trendOf(row.trend_mg_dl_per_min)]}` : '';
  const i = row.forecast?.horizons.indexOf(AHEAD_MIN) ?? -1;
  const ahead = i >= 0 ? row.forecast?.median[i] : undefined;
  const likely = ahead !== undefined && Number.isFinite(ahead) ? ` Likely about ${formatGlucose(ahead, unit)} in ${AHEAD_MIN} min.` : '';
  return `${formatGlucoseUnit(value, unit)}${trend}.${likely}`;
}

/**
 * "Heading below 70 in about 25 min (could reach 68)." The time is the first crossing of the
 * limit; the value in brackets is the furthest the forecast goes within the hour.
 */
export function headingSentence(flag: RiskFlag, s: MeStatus, unit: Unit): string {
  const low = flag.type === 'hypo';
  const limit = formatGlucose(low ? s.model.hypo_mg_dl : s.model.hyper_mg_dl, unit);
  const when = flag.horizon_min > 0 ? `in about ${flag.horizon_min} min` : 'soon';
  const reach = Number.isFinite(flag.extreme_mg_dl) ? ` (could reach ${formatGlucose(flag.extreme_mg_dl, unit)})` : '';
  return `Heading ${low ? 'below' : 'above'} ${limit} ${when}${reach}.`;
}

export function personStatus(s: MeStatus, unit: Unit): PersonStatus {
  const row = s.status;
  const flags = sortFlags(row.risk);
  const last = tryParseApiTime(row.last_reading);
  const t0 = tryParseApiTime(s.prediction?.t0);
  const pastForecast = !s.fresh && last !== null && t0 !== null && t0 === last;
  const base = { flags, details: [] as string[], urgent: false, pastForecast };
  const value = row.last_glucose_mg_dl;
  // Same inclusive comparisons as the backend alert rule (<= hypo, >= hyper).
  const lowNow = value !== null && value <= s.model.hypo_mg_dl;
  const highNow = value !== null && value >= s.model.hyper_mg_dl;
  const inRange: PersonStatus = {
    ...base,
    kind: 'in_range',
    sentence: 'In range for the next hour.',
    details: [`Likely to stay between ${formatGlucose(s.model.hypo_mg_dl, unit)} and ${formatGlucoseUnit(s.model.hyper_mg_dl, unit)}.`],
  };
  switch (row.status) {
    case 'at_risk': {
      const first = flags[0];
      if (!first) return inRange;
      const low = first.type === 'hypo';
      const urgent = first.severity === 'high';
      const others = flags.slice(1).map((f) => likelySentence(f.type, f.horizon_min, f.extreme_mg_dl, unit));
      if (value !== null && (low ? lowNow : highNow)) {
        // Already past the limit: the reading leads, then how far the forecast could go.
        const further = `Could go as ${low ? 'low' : 'high'} as ${formatGlucoseUnit(first.extreme_mg_dl, unit)} within the hour.`;
        return { ...base, kind: low ? 'low' : 'high', sentence: nowAndAhead(row, value, unit), details: [further, ...others], urgent };
      }
      return {
        ...base,
        kind: low ? 'low' : 'high',
        sentence: headingSentence(first, s, unit),
        details: others,
        urgent,
      };
    }
    case 'ok':
      // No low or high is likely, but the reading itself may be outside the range: lead with it,
      // so the sentence never contradicts the coloured value beside it.
      if (value !== null && (highNow || lowNow)) {
        return { ...base, kind: highNow ? 'high' : 'low', sentence: nowAndAhead(row, value, unit) };
      }
      return inRange;
    case 'warming_up':
      return { ...base, kind: 'collecting', sentence: 'Collecting readings.' };
    case 'no_data':
      return { ...base, kind: 'no_readings', sentence: 'No readings yet.' };
    case 'data_gap': {
      const age = row.minutes_since_last ?? 0;
      const kind: TodayKind = !row.stale ? 'gap' : age >= ENDED_AFTER_MIN ? 'ended' : 'stale';
      return { ...base, kind, sentence: 'No current forecast.' };
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
