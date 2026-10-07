import { describe, expect, it } from 'vitest';
import { bandAt, envelope } from './envelope';
import { priorityOf } from './priority';

const BAND = {
  horizons: [15, 30, 45, 60],
  low: [150, 141, 158, 170],
  median: [170, 182, 196, 219],
  high: [190, 230, 246, 240],
};

describe('forecast envelope', () => {
  it('spans the minimum of low to the maximum of high, with the 60-min median', () => {
    expect(envelope(BAND)).toEqual({ low: 141, high: 246, median60: 219 });
  });

  it('falls back to the last horizon for the median and skips non-finite values', () => {
    const band = { horizons: [15, 30], low: [Number.NaN, 90], median: [100, 104], high: [120, Number.NaN] };
    expect(envelope(band)).toEqual({ low: 90, high: 120, median60: 104 });
  });

  it('is null without values', () => {
    expect(envelope({ horizons: [], low: [], median: [], high: [] })).toBeNull();
  });

  it('reads one horizon', () => {
    expect(bandAt(BAND, 30)).toEqual({ low: 141, median: 182, high: 230 });
    expect(bandAt(BAND, 90)).toBeNull();
  });
});

describe('priority labels', () => {
  it('maps backend severity to Urgent, Soon and Watch', () => {
    expect(priorityOf('high')).toBe('urgent');
    expect(priorityOf('medium')).toBe('soon');
    expect(priorityOf('low')).toBe('watch');
    expect(priorityOf(null)).toBeNull();
    expect(priorityOf('unexpected')).toBeNull();
  });
});
