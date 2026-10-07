import { describe, expect, it } from 'vitest';
import { roundToHundred, timeInRanges } from './tir';
import { MINUTE } from './time';

const sum = (xs: Record<string, number>) => Object.values(xs).reduce((a, b) => a + b, 0);

describe('time in ranges', () => {
  it('counts readings per zone and rounds to percentages that sum to 100', () => {
    // 3 readings: one each in low, target, high → 33.3 % each must still sum to 100.
    const r = [
      { t: 0, v: 60 },
      { t: 15 * MINUTE, v: 120 },
      { t: 30 * MINUTE, v: 200 },
    ];
    const tir = timeInRanges(r, 0, 30 * MINUTE);
    expect(tir?.count).toBe(3);
    expect(sum(tir!.pct)).toBe(100);
    expect(tir!.pct).toEqual({ very_low: 0, low: 34, target: 33, high: 33, very_high: 0 });
  });

  it('keeps sums at 100 for awkward splits', () => {
    for (const counts of [[1, 1, 1, 1, 3], [7, 0, 0, 0, 0], [1, 2, 3, 4, 5], [2, 97, 1, 0, 0]]) {
      expect(roundToHundred(counts).reduce((a, b) => a + b, 0)).toBe(100);
    }
    expect(roundToHundred([0, 0, 0])).toEqual([0, 0, 0]);
  });

  it('returns null for an empty window', () => {
    expect(timeInRanges([], 0, 60 * MINUTE)).toBeNull();
    expect(timeInRanges([{ t: 2 * 60 * MINUTE, v: 100 }], 0, 60 * MINUTE)).toBeNull();
  });

  it('excludes readings outside the window and keeps its edges', () => {
    const r = [
      { t: -MINUTE, v: 40 },
      { t: 0, v: 100 },
      { t: 60 * MINUTE, v: 300 },
      { t: 61 * MINUTE, v: 40 },
    ];
    const tir = timeInRanges(r, 0, 60 * MINUTE);
    expect(tir?.count).toBe(2);
    expect(tir!.pct).toEqual({ very_low: 0, low: 0, target: 50, high: 0, very_high: 50 });
  });
});
