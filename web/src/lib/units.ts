/**
 * Glucose units. Values travel and are stored in mg/dL; mmol/L is a display and input unit.
 * mg/dL = mmol/L × 18.0182. mg/dL shows as a whole number, mmol/L with one decimal, so the
 * consensus thresholds read 54 / 70 / 180 / 250 mg/dL or 3.0 / 3.9 / 10.0 / 13.9 mmol/L.
 */

import type { Unit } from '../api/types';
import { HIGH_MAX, LOW_BELOW, TARGET_MAX, VERY_LOW_BELOW, type ZoneKey } from './zones';

export const UNITS: readonly Unit[] = ['mg/dL', 'mmol/L'];

export const MG_DL_PER_MMOL_L = 18.0182;

export function isUnit(v: unknown): v is Unit {
  return v === 'mg/dL' || v === 'mmol/L';
}

/** A mg/dL value in `unit`, unrounded. */
export function toUnit(mgDl: number, unit: Unit): number {
  return unit === 'mmol/L' ? mgDl / MG_DL_PER_MMOL_L : mgDl;
}

/** A value entered in `unit`, as mg/dL. */
export function toMgDl(value: number, unit: Unit): number {
  return unit === 'mmol/L' ? value * MG_DL_PER_MMOL_L : value;
}

/** Decimal places shown for a glucose value. */
export function unitDigits(unit: Unit): number {
  return unit === 'mmol/L' ? 1 : 0;
}

/** Input step for a glucose field. */
export function unitStep(unit: Unit): string {
  return unit === 'mmol/L' ? '0.1' : '1';
}

/** A mg/dL value as display text in `unit` ("112" or "6.2"); "—" when missing. */
export function formatGlucose(mgDl: number | null | undefined, unit: Unit): string {
  if (mgDl === null || mgDl === undefined || !Number.isFinite(mgDl)) return '—';
  const v = toUnit(mgDl, unit);
  const digits = unitDigits(unit);
  // Avoid "-0" and "−0.0" for values that round to zero.
  const rounded = Number(v.toFixed(digits));
  return (Object.is(rounded, -0) ? 0 : rounded).toFixed(digits);
}

/** "112 mg/dL" or "6.2 mmol/L". */
export function formatGlucoseUnit(mgDl: number | null | undefined, unit: Unit): string {
  const v = formatGlucose(mgDl, unit);
  return v === '—' ? v : `${v} ${unit}`;
}

/**
 * Rate of change per minute with a sign and a typographic minus: mg/dL "+1.4", mmol/L "+0.08"
 * (one more decimal than the value, so steady drifts stay visible).
 */
export function formatRateIn(mgDlPerMin: number, unit: Unit): string {
  const digits = unitDigits(unit) + 1;
  const v = Number(toUnit(mgDlPerMin, unit).toFixed(digits));
  if (v === 0) return (0).toFixed(digits);
  return `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(digits)}`;
}

/**
 * Parse a typed glucose value in `unit` (a comma decimal separator is accepted) into mg/dL.
 * Null for anything that is not a positive finite number.
 */
export function parseGlucose(text: string, unit: Unit): number | null {
  const t = text.trim().replace(',', '.');
  if (!/^\d+(\.\d+)?$|^\.\d+$/.test(t)) return null;
  const v = Number(t);
  if (!Number.isFinite(v) || v <= 0) return null;
  return toMgDl(v, unit);
}

/** Consensus zone ranges as readers know them in each unit. */
export const ZONE_RANGE: Record<Unit, Record<ZoneKey, string>> = {
  'mg/dL': {
    very_low: `under ${VERY_LOW_BELOW}`,
    low: `${VERY_LOW_BELOW}–${LOW_BELOW - 1}`,
    target: `${LOW_BELOW}–${TARGET_MAX}`,
    high: `${TARGET_MAX + 1}–${HIGH_MAX}`,
    very_high: `over ${HIGH_MAX}`,
  },
  'mmol/L': {
    very_low: 'under 3.0',
    low: '3.0–3.8',
    target: '3.9–10.0',
    high: '10.1–13.9',
    very_high: 'over 13.9',
  },
};

