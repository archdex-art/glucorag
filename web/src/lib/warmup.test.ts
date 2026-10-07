import { describe, expect, it } from 'vitest';
import { MINUTE } from './time';
import { warmup } from './warmup';

const TIMING = { interval_min: 15, lookback_min: 120, data_gap_min: 60 };
const T = Date.UTC(2026, 9, 6, 12, 0);
/** n readings every `step` minutes, ending at T. */
const run = (n: number, step = 15, end = T) => Array.from({ length: n }, (_, i) => end - (n - 1 - i) * step * MINUTE);

describe('readings needed before the first forecast', () => {
  it('is null without readings', () => {
    expect(warmup([], TIMING)).toBeNull();
  });

  it('needs 7 more after one reading, and one fewer per reading after that', () => {
    expect(warmup(run(1), TIMING)).toMatchObject({ needed: 7, minutes: 105, runStart: T, afterGap: false });
    expect(warmup(run(5), TIMING)).toMatchObject({ needed: 3, minutes: 45 });
    expect(warmup(run(7), TIMING)).toMatchObject({ needed: 1, minutes: 15 });
  });

  it('is ready at 8 readings (the look-back window is full)', () => {
    expect(warmup(run(8), TIMING)).toMatchObject({ needed: 0, minutes: 0 });
    expect(warmup(run(30), TIMING)).toMatchObject({ needed: 0 });
  });

  it('follows the half-step tolerance at the window edge', () => {
    // A span of exactly 97.5 min is still warming up; one minute more is not.
    expect(warmup([T - 97.5 * MINUTE, T - 45 * MINUTE, T], TIMING)!.needed).toBe(1);
    expect(warmup([T - 98.5 * MINUTE, T - 45 * MINUTE, T], TIMING)!.needed).toBe(0);
  });

  it('counts time, not readings, when readings are denser than the interval', () => {
    // 13 readings 5 min apart span 60 min: like 5 readings at 15 min.
    expect(warmup(run(13, 5), TIMING)).toMatchObject({ needed: 3, minutes: 45 });
  });

  it('restarts after a gap longer than the gap limit, and accepts unsorted input', () => {
    const before = run(20, 15, T - 3 * 60 * MINUTE);
    const after = run(3);
    const w = warmup([...after, ...before].reverse(), TIMING)!;
    expect(w).toMatchObject({ needed: 5, minutes: 75, runStart: after[0], afterGap: true });
    // A gap of exactly the limit does not break the run.
    expect(warmup([T - 60 * MINUTE, T], TIMING)).toMatchObject({ runStart: T - 60 * MINUTE, afterGap: false });
  });
});
