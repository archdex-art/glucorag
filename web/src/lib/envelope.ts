import type { ForecastBand } from '../api/types';

export type Band = Pick<ForecastBand, 'horizons' | 'low' | 'median' | 'high'>;

export interface Envelope {
  /** Lowest low-quantile value over the next hour. */
  low: number;
  /** Highest high-quantile value over the next hour. */
  high: number;
  /** Median at 60 min (the last horizon when 60 is absent); null when unavailable. */
  median60: number | null;
}

/** The next-hour envelope: `min(low)` to `max(high)`, plus the 60-min median. */
export function envelope(band: Band): Envelope | null {
  const lows = band.low.filter((x) => Number.isFinite(x));
  const highs = band.high.filter((x) => Number.isFinite(x));
  if (!lows.length || !highs.length) return null;
  const low = Math.min(...lows);
  const high = Math.max(...highs);
  const at60 = band.horizons.indexOf(60);
  const m = at60 >= 0 ? band.median[at60] : band.median[band.median.length - 1];
  return {
    low: Math.min(low, high),
    high: Math.max(low, high),
    median60: m !== undefined && Number.isFinite(m) ? m : null,
  };
}

export interface BandPoint {
  low: number;
  median: number;
  high: number;
}

/** Band values at one horizon (minutes), or null if the band has no such horizon. */
export function bandAt(band: Band, horizon: number): BandPoint | null {
  const i = band.horizons.indexOf(horizon);
  if (i < 0) return null;
  const low = band.low[i];
  const median = band.median[i];
  const high = band.high[i];
  if (low === undefined || median === undefined || high === undefined) return null;
  if (![low, median, high].every(Number.isFinite)) return null;
  return { low: Math.min(low, high), median, high: Math.max(low, high) };
}
