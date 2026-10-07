import { describe, expect, it } from 'vitest';
import { trendOf } from './trend';
import { ZONES, logPosition, zoneOf } from './zones';

describe('zone classification', () => {
  it('splits at exactly 54, 70, 180 and 250', () => {
    expect(zoneOf(53.9)).toBe('very_low');
    expect(zoneOf(54)).toBe('low');
    expect(zoneOf(69.9)).toBe('low');
    expect(zoneOf(70)).toBe('target');
    expect(zoneOf(180)).toBe('target');
    expect(zoneOf(180.1)).toBe('high');
    expect(zoneOf(250)).toBe('high');
    expect(zoneOf(250.1)).toBe('very_high');
  });

  it('lists the zones in order with contiguous edges', () => {
    expect(ZONES.map((z) => z.key)).toEqual(['very_low', 'low', 'target', 'high', 'very_high']);
    for (let i = 1; i < ZONES.length; i++) expect(ZONES[i]!.from).toBe(ZONES[i - 1]!.to);
  });
});

describe('log scale', () => {
  it('maps 40 to 0, 400 to 1 and the geometric middle to 0.5', () => {
    expect(logPosition(40)).toBe(0);
    expect(logPosition(400)).toBe(1);
    expect(logPosition(Math.sqrt(40 * 400))).toBeCloseTo(0.5, 12);
  });

  it('is monotonic inside the domain', () => {
    let prev = -1;
    for (let v = 40; v <= 400; v += 3) {
      const x = logPosition(v);
      expect(x).toBeGreaterThan(prev);
      prev = x;
    }
  });

  it('clamps below 40 and above 400', () => {
    expect(logPosition(39)).toBe(0);
    expect(logPosition(0)).toBe(0);
    expect(logPosition(-5)).toBe(0);
    expect(logPosition(Number.NaN)).toBe(0);
    expect(logPosition(401)).toBe(1);
    expect(logPosition(10_000)).toBe(1);
  });
});

describe('trend buckets', () => {
  it('splits at exactly ±1 and ±2 mg/dL per min', () => {
    expect(trendOf(2.01)).toBe('rising_quickly');
    expect(trendOf(2)).toBe('rising');
    expect(trendOf(1.01)).toBe('rising');
    expect(trendOf(1)).toBe('steady');
    expect(trendOf(0)).toBe('steady');
    expect(trendOf(-1)).toBe('steady');
    expect(trendOf(-1.01)).toBe('falling');
    expect(trendOf(-2)).toBe('falling');
    expect(trendOf(-2.01)).toBe('falling_quickly');
  });
});
