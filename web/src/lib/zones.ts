/**
 * Consensus glucose ranges (Battelino et al., Diabetes Care 2019) and the log scale the range
 * strip draws them on. Zone colour is a display classification only; alerts come from the
 * backend's flags (an exact 70 is "target" here while the hypo rule, ≤ 70, may still fire).
 */

export type ZoneKey = 'very_low' | 'low' | 'target' | 'high' | 'very_high';

export const VERY_LOW_BELOW = 54;
export const LOW_BELOW = 70;
export const TARGET_MAX = 180;
export const HIGH_MAX = 250;

/** Domain of the range strip, mg/dL. */
export const SCALE_MIN = 40;
export const SCALE_MAX = 400;

export interface Zone {
  key: ZoneKey;
  label: string;
  /** Range as readers know it, e.g. "54–69". */
  range: string;
  /** Lower and upper edge on the strip scale, mg/dL. */
  from: number;
  to: number;
}

export const ZONES: readonly Zone[] = [
  { key: 'very_low', label: 'Very low', range: 'under 54', from: SCALE_MIN, to: VERY_LOW_BELOW },
  { key: 'low', label: 'Low', range: '54–69', from: VERY_LOW_BELOW, to: LOW_BELOW },
  { key: 'target', label: 'Target', range: '70–180', from: LOW_BELOW, to: TARGET_MAX },
  { key: 'high', label: 'High', range: '181–250', from: TARGET_MAX, to: HIGH_MAX },
  { key: 'very_high', label: 'Very high', range: 'over 250', from: HIGH_MAX, to: SCALE_MAX },
];

export const ZONE_LABEL: Record<ZoneKey, string> = {
  very_low: 'very low',
  low: 'low',
  target: 'target',
  high: 'high',
  very_high: 'very high',
};

export function zoneOf(v: number): ZoneKey {
  if (v < VERY_LOW_BELOW) return 'very_low';
  if (v < LOW_BELOW) return 'low';
  if (v <= TARGET_MAX) return 'target';
  if (v <= HIGH_MAX) return 'high';
  return 'very_high';
}

const LN_MIN = Math.log(SCALE_MIN);
const LN_SPAN = Math.log(SCALE_MAX) - LN_MIN;

/** Position on the strip in [0, 1]: `(ln v − ln 40) / (ln 400 − ln 40)`, clamped. */
export function logPosition(v: number): number {
  if (!(v > 0)) return 0;
  const x = (Math.log(v) - LN_MIN) / LN_SPAN;
  return Math.min(1, Math.max(0, x));
}
