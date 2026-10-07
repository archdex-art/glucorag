import type { WallTime } from './time';
import { zoneOf, type ZoneKey } from './zones';

/**
 * Whole percentages that sum to exactly 100 (largest-remainder rounding). Ties go to the
 * earlier entry. All-zero input stays all zero.
 */
export function roundToHundred(values: readonly number[]): number[] {
  const total = values.reduce((a, b) => a + Math.max(0, b), 0);
  if (!(total > 0)) return values.map(() => 0);
  const exact = values.map((v) => (Math.max(0, v) / total) * 100);
  const floors = exact.map(Math.floor);
  let missing = 100 - floors.reduce((a, b) => a + b, 0);
  const order = exact
    .map((v, i) => ({ i, rem: v - Math.floor(v) }))
    .sort((a, b) => b.rem - a.rem || a.i - b.i);
  for (const { i } of order) {
    if (missing <= 0) break;
    floors[i] = (floors[i] ?? 0) + 1;
    missing -= 1;
  }
  return floors;
}

export const TIR_ORDER: readonly ZoneKey[] = ['very_low', 'low', 'target', 'high', 'very_high'];

export interface TimeInRanges {
  /** Readings counted (inside the window). */
  count: number;
  pct: Record<ZoneKey, number>;
}

/**
 * Share of readings per consensus zone for readings with `start <= t <= end`.
 * CGM readings sit on a regular grid, so the share of readings is the share of time.
 * Returns null when the window holds no reading.
 */
export function timeInRanges(
  readings: readonly { t: WallTime; v: number }[],
  start: WallTime,
  end: WallTime,
): TimeInRanges | null {
  const counts: Record<ZoneKey, number> = { very_low: 0, low: 0, target: 0, high: 0, very_high: 0 };
  let count = 0;
  for (const r of readings) {
    if (r.t < start || r.t > end || !Number.isFinite(r.v)) continue;
    counts[zoneOf(r.v)] += 1;
    count += 1;
  }
  if (count === 0) return null;
  const rounded = roundToHundred(TIR_ORDER.map((z) => counts[z]));
  const pct = Object.fromEntries(TIR_ORDER.map((z, i) => [z, rounded[i] ?? 0])) as Record<ZoneKey, number>;
  return { count, pct };
}
