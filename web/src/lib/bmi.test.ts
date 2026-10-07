import { describe, expect, it } from 'vitest';
import { BMI_MAX, BMI_MIN, bmiImperial, bmiInRange, bmiMetric, defaultMeasureSystem } from './bmi';

describe('BMI', () => {
  it('computes kg/m² from cm and kg, to one decimal', () => {
    expect(bmiMetric(180, 81)).toBe(25);
    expect(bmiMetric(165, 60)).toBe(22);
    expect(bmiMetric(170, 70)).toBe(24.2);
  });

  it('computes the same BMI from feet, inches and pounds', () => {
    // 5 ft 11 in = 180.34 cm; 180 lb = 81.65 kg.
    expect(bmiImperial(5, 11, 180)).toBe(25.1);
    expect(bmiImperial(6, 0, 200)).toBe(27.1);
    // Inches alone, and a missing inches field, both work.
    expect(bmiImperial(0, 70, 154)).toBe(bmiImperial(5, 10, 154));
    expect(bmiImperial(6, Number.NaN, 200)).toBe(bmiImperial(6, 0, 200));
  });

  it('gives null for missing or non-positive measurements', () => {
    expect(bmiMetric(0, 70)).toBeNull();
    expect(bmiMetric(170, 0)).toBeNull();
    expect(bmiMetric(Number.NaN, 70)).toBeNull();
    expect(bmiMetric(170, Number.POSITIVE_INFINITY)).toBeNull();
    expect(bmiImperial(-1, 0, 150)).toBeNull();
    expect(bmiImperial(0, 0, 150)).toBeNull();
  });

  it('accepts exactly the service range, 10 to 80', () => {
    expect([BMI_MIN, BMI_MAX]).toEqual([10, 80]);
    expect(bmiInRange(10)).toBe(true);
    expect(bmiInRange(80)).toBe(true);
    expect(bmiInRange(9.9)).toBe(false);
    expect(bmiInRange(80.1)).toBe(false);
    expect(bmiInRange(null)).toBe(false);
  });
});

describe('default measurement system', () => {
  it('follows the locale region, not the glucose unit', () => {
    expect(defaultMeasureSystem('en-US')).toBe('imperial');
    expect(defaultMeasureSystem('en-IN')).toBe('metric'); // mg/dL country, metric body measures
    expect(defaultMeasureSystem('en-GB')).toBe('metric');
    expect(defaultMeasureSystem('my-MM')).toBe('imperial');
  });

  it('infers the likely region from a bare language and falls back to metric', () => {
    expect(defaultMeasureSystem('en')).toBe('imperial'); // en → en-Latn-US
    expect(defaultMeasureSystem('de')).toBe('metric');
    expect(defaultMeasureSystem(undefined)).toBe('metric');
    expect(defaultMeasureSystem('not a locale!')).toBe('metric');
  });
});
