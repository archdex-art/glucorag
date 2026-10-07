/**
 * How many more readings, and roughly how long, until the model can forecast.
 *
 * The model reads the last `lookback` minutes on an `interval` grid. Mirroring
 * glucorag.risk.gap_guard.is_warming_up, a forecast is possible once the current unbroken run
 * of readings reaches back past `lookback − interval − interval / 2` minutes before the newest
 * reading. A gap longer than `gap` minutes starts a new run.
 */

import { MINUTE, type WallTime } from './time';

export interface ModelTiming {
  interval_min: number;
  lookback_min: number;
  data_gap_min: number;
}

export interface Warmup {
  /** Readings still needed at the model interval; 0 when a forecast is already possible. */
  needed: number;
  /** About how long those readings take to arrive, minutes. */
  minutes: number;
  /** First reading of the current unbroken run. */
  runStart: WallTime;
  /** True when an earlier run ended in a gap longer than `data_gap_min`. */
  afterGap: boolean;
}

/** Null without readings. `times` need not be sorted. */
export function warmup(times: readonly WallTime[], timing: ModelTiming): Warmup | null {
  const sorted = [...times].filter(Number.isFinite).sort((a, b) => a - b);
  const last = sorted[sorted.length - 1];
  if (last === undefined) return null;
  let runStart = last;
  let afterGap = false;
  for (let i = sorted.length - 2; i >= 0; i--) {
    const prev = sorted[i] ?? runStart;
    if (runStart - prev > timing.data_gap_min * MINUTE) {
      afterGap = true;
      break;
    }
    runStart = prev;
  }
  const { interval_min: step, lookback_min: lookback } = timing;
  const span = (last - runStart) / MINUTE;
  const reach = lookback - step - step / 2;
  const needed = span > reach ? 0 : Math.floor((reach - span) / step) + 1;
  return { needed, minutes: needed * step, runStart, afterGap };
}
