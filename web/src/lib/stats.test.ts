import { describe, expect, it } from 'vitest';
import { coveragePercent, glucoseStats, gmi } from './stats';

describe('GMI', () => {
  it('is 3.31 + 0.02392 × mean mg/dL', () => {
    expect(gmi(154)).toBeCloseTo(6.99368, 5);
    expect(gmi(100)).toBeCloseTo(5.702, 5);
    expect(gmi(0)).toBeCloseTo(3.31, 9);
  });
});

describe('glucose statistics', () => {
  it('gives mean, sample SD, CV and GMI', () => {
    const s = glucoseStats([100, 120, 140, 160])!;
    expect(s.count).toBe(4);
    expect(s.mean).toBe(130);
    expect(s.sd).toBeCloseTo(25.8199, 4);
    expect(s.cv).toBeCloseTo((25.8199 / 130) * 100, 3);
    expect(s.gmi).toBeCloseTo(3.31 + 0.02392 * 130, 9);
  });

  it('has zero variability for one reading or a flat trace', () => {
    expect(glucoseStats([150])).toMatchObject({ count: 1, mean: 150, sd: 0, cv: 0 });
    expect(glucoseStats([90, 90, 90])).toMatchObject({ sd: 0, cv: 0 });
  });

  it('ignores non-finite values and is null without readings', () => {
    expect(glucoseStats([Number.NaN, 100, Number.POSITIVE_INFINITY, 200])).toMatchObject({ count: 2, mean: 150 });
    expect(glucoseStats([])).toBeNull();
    expect(glucoseStats([Number.NaN])).toBeNull();
  });
});

describe('coverage', () => {
  it('is readings over those expected at the model interval', () => {
    expect(coveragePercent(96, 24 * 60, 15)).toBe(100);
    expect(coveragePercent(48, 24 * 60, 15)).toBe(50);
    expect(coveragePercent(192, 14 * 24 * 60, 15)).toBeCloseTo((192 / 1344) * 100, 9);
  });

  it('caps at 100 (a window holds both edge readings) and is 0 at the edges', () => {
    expect(coveragePercent(97, 24 * 60, 15)).toBe(100);
    expect(coveragePercent(0, 1440, 15)).toBe(0);
    expect(coveragePercent(10, 0, 15)).toBe(0);
    expect(coveragePercent(10, 1440, 0)).toBe(0);
    expect(coveragePercent(1, 10, 15)).toBe(0);
  });
});
