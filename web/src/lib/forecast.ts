import type { Prediction, StoredReading } from '../api/types';
import { MINUTE, parseApiTime, type WallTime } from './time';

const EPS = 1e-9;

export function quantileIndex(quantiles: readonly number[], q: number): number {
  return quantiles.findIndex((level) => Math.abs(level - q) < EPS);
}

/** Prediction with quantile levels sorted ascending (columns permuted) and horizons sorted. */
export interface SortedForecast {
  t0: WallTime;
  horizons: number[];
  quantiles: number[];
  /** values[h][q], rows/columns following `horizons` / `quantiles`. */
  values: number[][];
}

export function sortForecast(p: Prediction): SortedForecast {
  const qOrder = p.quantiles.map((q, i) => [q, i] as const).sort((a, b) => a[0] - b[0]);
  const hOrder = p.horizons.map((h, i) => [h, i] as const).sort((a, b) => a[0] - b[0]);
  return {
    t0: parseApiTime(p.t0),
    horizons: hOrder.map(([h]) => h),
    quantiles: qOrder.map(([q]) => q),
    values: hOrder.map(([, hi]) => {
      const row = p.values[hi] ?? [];
      return qOrder.map(([, qi]) => row[qi] ?? Number.NaN);
    }),
  };
}

/**
 * Quantile pairs for the AGP ribbons: outer (≈ q0.02–q0.98), mid (q0.10–q0.90),
 * inner (q0.25–q0.75), and the median.
 */
export interface BandLevels {
  outer: [number, number] | null;
  mid: [number, number] | null;
  inner: [number, number] | null;
  median: number | null;
}

function pick(quantiles: readonly number[], preferred: number): number | null {
  return quantileIndex(quantiles, preferred) >= 0 ? preferred : null;
}

/**
 * Chooses band levels from the model's quantile set. Preferred levels are 0.02/0.98, 0.10/0.90,
 * 0.25/0.75 and 0.5; when absent the outer band falls back to the extreme levels and the median
 * to the level closest to 0.5.
 */
export function bandLevels(quantiles: readonly number[]): BandLevels {
  const sorted = [...quantiles].sort((a, b) => a - b);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (first === undefined || last === undefined) return { outer: null, mid: null, inner: null, median: null };
  const outerLo = pick(sorted, 0.02) ?? first;
  const outerHi = pick(sorted, 0.98) ?? last;
  const midLo = pick(sorted, 0.1);
  const midHi = pick(sorted, 0.9);
  const innerLo = pick(sorted, 0.25);
  const innerHi = pick(sorted, 0.75);
  const median = sorted.reduce((best, q) => (Math.abs(q - 0.5) < Math.abs(best - 0.5) ? q : best));
  const outer: [number, number] | null = outerLo < outerHi ? [outerLo, outerHi] : null;
  // A mid ribbon identical to the outer one would only darken it.
  const mid: [number, number] | null =
    midLo !== null && midHi !== null && !(outer && outer[0] === midLo && outer[1] === midHi) ? [midLo, midHi] : null;
  return {
    outer,
    mid,
    inner: innerLo !== null && innerHi !== null ? [innerLo, innerHi] : null,
    median,
  };
}

export interface FanPoint {
  t: WallTime;
  horizon: number;
  /** [low, high] per ribbon, lightest to deepest. */
  outer: [number, number] | null;
  mid: [number, number] | null;
  inner: [number, number] | null;
  median: number | null;
}

function valueAt(f: SortedForecast, row: number[], q: number): number | null {
  const i = quantileIndex(f.quantiles, q);
  const v = i >= 0 ? row[i] : undefined;
  return v === undefined || Number.isNaN(v) ? null : v;
}

function band(f: SortedForecast, row: number[], pair: [number, number] | null): [number, number] | null {
  if (!pair) return null;
  const a = valueAt(f, row, pair[0]);
  const b = valueAt(f, row, pair[1]);
  if (a === null || b === null) return null;
  // Guard against quantile crossing: a band is always [min, max].
  return [Math.min(a, b), Math.max(a, b)];
}

/**
 * Forecast fan points, one per horizon, ascending in time. When `anchor` (the observed glucose
 * at t0) is given, a zero-width point at t0 is prepended so the fan starts at the last reading.
 */
export function buildFan(p: Prediction, anchor?: number | null): FanPoint[] {
  const f = sortForecast(p);
  const levels = bandLevels(f.quantiles);
  const points: FanPoint[] = f.horizons.map((h, i) => {
    const row = f.values[i] ?? [];
    return {
      t: f.t0 + h * MINUTE,
      horizon: h,
      outer: band(f, row, levels.outer),
      mid: band(f, row, levels.mid),
      inner: band(f, row, levels.inner),
      median: levels.median === null ? null : valueAt(f, row, levels.median),
    };
  });
  if (anchor !== undefined && anchor !== null && Number.isFinite(anchor)) {
    points.unshift({
      t: f.t0,
      horizon: 0,
      outer: levels.outer ? [anchor, anchor] : null,
      mid: levels.mid ? [anchor, anchor] : null,
      inner: levels.inner ? [anchor, anchor] : null,
      median: anchor,
    });
  }
  return points;
}

export type Crossing = 'hypo' | 'hyper' | null;

/** Mirrors glucorag.risk.detectors: hypo when value <= threshold, hyper when value >= threshold. */
export function crossing(value: number, hypo: number, hyper: number): Crossing {
  if (value <= hypo) return 'hypo';
  if (value >= hyper) return 'hyper';
  return null;
}

/** Threshold crossing per cell of a sorted forecast (same shape as `values`). */
export function crossingMatrix(f: SortedForecast, hypo: number, hyper: number): Crossing[][] {
  return f.values.map((row) => row.map((v) => (Number.isNaN(v) ? null : crossing(v, hypo, hyper))));
}

export interface ReadingPoint {
  t: WallTime;
  glucose: number | null;
}

/**
 * Readings as a line series; a null point is inserted inside every gap longer than
 * `gapMinutes` so the chart breaks the line instead of interpolating across missing data.
 */
export function readingSeries(
  readings: readonly Pick<StoredReading, 'timestamp' | 'glucose_mg_dl'>[],
  gapMinutes: number,
): ReadingPoint[] {
  const pts = readings
    .map((r) => ({ t: parseApiTime(r.timestamp), glucose: r.glucose_mg_dl }))
    .sort((a, b) => a.t - b.t);
  const out: ReadingPoint[] = [];
  let prev: ReadingPoint | undefined;
  for (const p of pts) {
    if (prev && p.t - prev.t > gapMinutes * MINUTE) {
      out.push({ t: prev.t + (p.t - prev.t) / 2, glucose: null });
    }
    out.push(p);
    prev = p;
  }
  return out;
}

export interface ChartRow {
  t: WallTime;
  glucose?: number | null;
  outer?: [number, number] | null;
  mid?: [number, number] | null;
  inner?: [number, number] | null;
  median?: number | null;
}

/** Merge reading and fan series into one time-sorted array (rows at equal t are combined). */
export function mergeChartRows(readings: readonly ReadingPoint[], fan: readonly FanPoint[]): ChartRow[] {
  const byT = new Map<number, ChartRow>();
  for (const r of readings) byT.set(r.t, { ...byT.get(r.t), t: r.t, glucose: r.glucose });
  for (const p of fan) {
    byT.set(p.t, { ...byT.get(p.t), t: p.t, outer: p.outer, mid: p.mid, inner: p.inner, median: p.median });
  }
  return [...byT.values()].sort((a, b) => a.t - b.t);
}
