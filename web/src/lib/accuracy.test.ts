import { describe, expect, it } from 'vitest';
import type { MeAccuracy } from '../api/types';
import { accuracyLine, accuracyWarningText, atHorizon, fmtCoverage, sparkPath } from './accuracy';

function mine(over: Partial<MeAccuracy> = {}): MeAccuracy {
  return { days: 7, horizon_min: 30, count: 143, min_count: 20, median_abs_error_mg_dl: 11.2, ...over };
}

describe('the accuracy line on Today', () => {
  it('rounds to the reader’s unit', () => {
    expect(accuracyLine(mine(), 'mg/dL')).toBe('Over the last 7 days, your 30-minute forecast was usually within 11 mg/dL.');
    expect(accuracyLine(mine(), 'mmol/L')).toBe('Over the last 7 days, your 30-minute forecast was usually within 0.6 mmol/L.');
  });

  it('follows the window and horizon the service reports', () => {
    expect(accuracyLine(mine({ days: 14, horizon_min: 60, median_abs_error_mg_dl: 20.6 }), 'mg/dL')).toBe(
      'Over the last 14 days, your 60-minute forecast was usually within 21 mg/dL.',
    );
  });

  it('never says "within 0"', () => {
    expect(accuracyLine(mine({ median_abs_error_mg_dl: 0.4 }), 'mg/dL')).toMatch(/within 1 mg\/dL\.$/);
    expect(accuracyLine(mine({ median_abs_error_mg_dl: 0.4 }), 'mmol/L')).toMatch(/within 0\.1 mmol\/L\.$/);
  });

  it('is hidden until enough forecasts were checked', () => {
    expect(accuracyLine(mine({ count: 12, median_abs_error_mg_dl: null }), 'mg/dL')).toBeNull();
    expect(accuracyLine(mine({ count: 12 }), 'mg/dL')).toBeNull();
  });
});

describe('live accuracy for staff', () => {
  it('words a warning with the 7-day RMSE, the reference and how far above it is', () => {
    expect(accuracyWarningText({ horizon_min: 30, rmse_7d_mg_dl: 24.13, reference_rmse_mg_dl: 17.5, ratio: 24.13 / 17.5 })).toBe(
      "Last 7 days' 30-min RMSE is 24.1 mg/dL, 38% above the evaluation's 17.5 mg/dL.",
    );
  });

  it('shows coverage as a whole percentage', () => {
    expect(fmtCoverage(0.4987)).toBe('50%');
    expect(fmtCoverage(1)).toBe('100%');
    expect(fmtCoverage(null)).toBe('—');
  });

  it('finds a horizon’s entry', () => {
    const row = { horizon_min: 60, count: 0, rmse_mg_dl: null, mae_mg_dl: null, median_abs_error_mg_dl: null, coverage_50: null, coverage_80: null };
    expect(atHorizon([row], 60)).toBe(row);
    expect(atHorizon([row], 30)).toBeNull();
  });
});

describe('sparkPath', () => {
  it('spreads values across the width with the maximum at the top', () => {
    expect(sparkPath([0, 10, 20], 100, 20, 20)).toBe('M0 20 L50 10 L100 0');
  });

  it('breaks the line at missing days and dots lone values', () => {
    expect(sparkPath([10, null, 10, 20, null], 100, 20, 20)).toBe('M0 10 h0 M50 10 L75 0');
  });

  it('clamps values beyond the scale and draws nothing without one', () => {
    expect(sparkPath([30, -5], 10, 10, 20)).toBe('M0 0 L10 10');
    expect(sparkPath([], 10, 10, 20)).toBe('');
    expect(sparkPath([null, null], 10, 10, 0)).toBe('');
  });
});
