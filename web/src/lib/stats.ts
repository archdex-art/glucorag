/** Summary statistics of a reading window, as AGP reports show them. All inputs in mg/dL. */

/**
 * Glucose management indicator (Bergenstal et al., Diabetes Care 2018), in percent:
 * GMI = 3.31 + 0.02392 × mean glucose in mg/dL.
 */
export function gmi(meanMgDl: number): number {
  return 3.31 + 0.02392 * meanMgDl;
}

export interface GlucoseStats {
  count: number;
  mean: number;
  /** Sample standard deviation (n − 1); 0 for a single reading. */
  sd: number;
  /** Coefficient of variation, percent: SD / mean × 100. */
  cv: number;
  gmi: number;
}

/** Null when there is no finite reading. */
export function glucoseStats(values: readonly number[]): GlucoseStats | null {
  const xs = values.filter((v) => Number.isFinite(v));
  const n = xs.length;
  if (n === 0) return null;
  const mean = xs.reduce((a, b) => a + b, 0) / n;
  const sd = n > 1 ? Math.sqrt(xs.reduce((a, v) => a + (v - mean) ** 2, 0) / (n - 1)) : 0;
  return { count: n, mean, sd, cv: mean > 0 ? (sd / mean) * 100 : 0, gmi: gmi(mean) };
}

/**
 * Share of the readings a sensor would produce in the window at the model interval, percent,
 * capped at 100. A 24 h window at 15 min expects 96 readings.
 */
export function coveragePercent(count: number, windowMinutes: number, intervalMinutes: number): number {
  if (!(windowMinutes > 0) || !(intervalMinutes > 0) || !(count > 0)) return 0;
  const expected = Math.floor(windowMinutes / intervalMinutes);
  if (expected <= 0) return 0;
  return Math.min(100, (count / expected) * 100);
}
