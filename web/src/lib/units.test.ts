import { describe, expect, it } from 'vitest';
import { MG_DL_PER_MMOL_L, ZONE_RANGE, formatGlucose, formatGlucoseUnit, formatRateIn, parseGlucose, toMgDl, toUnit } from './units';

describe('glucose units', () => {
  it('converts with mg/dL = mmol/L × 18.0182 both ways', () => {
    expect(MG_DL_PER_MMOL_L).toBe(18.0182);
    expect(toMgDl(5.5, 'mmol/L')).toBeCloseTo(99.1001, 4);
    expect(toUnit(180, 'mmol/L')).toBeCloseTo(9.98990, 4);
    expect(toUnit(112, 'mg/dL')).toBe(112);
    expect(toUnit(toMgDl(7.3, 'mmol/L'), 'mmol/L')).toBeCloseTo(7.3, 12);
  });

  it('shows mg/dL as a whole number and mmol/L with one decimal', () => {
    expect(formatGlucose(112.4, 'mg/dL')).toBe('112');
    expect(formatGlucose(112.5, 'mg/dL')).toBe('113');
    expect(formatGlucose(112, 'mmol/L')).toBe('6.2');
    expect(formatGlucose(90.091, 'mmol/L')).toBe('5.0');
    expect(formatGlucoseUnit(112, 'mmol/L')).toBe('6.2 mmol/L');
    expect(formatGlucose(null, 'mg/dL')).toBe('—');
    expect(formatGlucose(Number.NaN, 'mmol/L')).toBe('—');
    expect(formatGlucoseUnit(undefined, 'mmol/L')).toBe('—');
  });

  it('labels the consensus thresholds 3.0 / 3.9 / 10.0 / 13.9 mmol/L', () => {
    expect([54, 70, 180, 250].map((v) => formatGlucose(v, 'mmol/L'))).toEqual(['3.0', '3.9', '10.0', '13.9']);
    expect([54, 70, 180, 250].map((v) => formatGlucose(v, 'mg/dL'))).toEqual(['54', '70', '180', '250']);
    expect(ZONE_RANGE['mmol/L'].target).toBe('3.9–10.0');
    expect(ZONE_RANGE['mg/dL'].high).toBe('181–250');
  });

  it('formats rates with a sign and one more decimal than the value', () => {
    expect(formatRateIn(1.44, 'mg/dL')).toBe('+1.4');
    expect(formatRateIn(-0.6, 'mg/dL')).toBe('−0.6');
    expect(formatRateIn(1.44, 'mmol/L')).toBe('+0.08');
    expect(formatRateIn(-2.5, 'mmol/L')).toBe('−0.14');
    expect(formatRateIn(0.04, 'mg/dL')).toBe('0.0');
    expect(formatRateIn(-0.01, 'mmol/L')).toBe('0.00');
  });

  it('parses typed values, with a comma decimal, into mg/dL', () => {
    expect(parseGlucose('112', 'mg/dL')).toBe(112);
    expect(parseGlucose(' 6,2 ', 'mmol/L')).toBeCloseTo(6.2 * 18.0182, 9);
    expect(parseGlucose('.5', 'mmol/L')).toBeCloseTo(9.0091, 4);
    for (const bad of ['', '0', '-3', 'abc', '6.2.1', '1e3', 'Infinity']) expect(parseGlucose(bad, 'mg/dL')).toBeNull();
  });
});
