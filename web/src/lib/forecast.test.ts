import { describe, expect, it } from 'vitest';
import type { Prediction, StoredReading } from '../api/types';
import {
  bandLevels,
  buildFan,
  crossing,
  crossingMatrix,
  mergeChartRows,
  quantileIndex,
  readingSeries,
  sortForecast,
} from './forecast';
import { MINUTE, parseApiTime } from './time';

const Q = [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98];

function prediction(overrides: Partial<Prediction> = {}): Prediction {
  return {
    patient_id: '1001',
    t0: '2021-08-06T12:58:00',
    horizons: [15, 30, 45, 60],
    quantiles: Q,
    values: [
      [100, 105, 110, 115, 120, 125, 130],
      [90, 98, 104, 112, 121, 130, 140],
      [75, 88, 98, 110, 123, 136, 152],
      [62, 80, 93, 108, 126, 143, 185],
    ],
    model_version: 'shanghai-v1',
    ...overrides,
  };
}

describe('quantile bands', () => {
  it('selects q0.02–q0.98 outer, q0.10–q0.90 mid, q0.25–q0.75 inner and the median', () => {
    expect(bandLevels(Q)).toEqual({ outer: [0.02, 0.98], mid: [0.1, 0.9], inner: [0.25, 0.75], median: 0.5 });
    expect(quantileIndex(Q, 0.75)).toBe(4);
    expect(quantileIndex(Q, 0.1 + 0.2 - 0.05)).toBe(2); // float tolerance
    expect(quantileIndex(Q, 0.3)).toBe(-1);
  });

  it('falls back to extreme levels when 0.02/0.98 or 0.25/0.75 are absent', () => {
    // q0.10–q0.90 already is the outer ribbon here, so there is no separate mid ribbon.
    expect(bandLevels([0.9, 0.1, 0.5])).toEqual({ outer: [0.1, 0.9], mid: null, inner: null, median: 0.5 });
    expect(bandLevels([])).toEqual({ outer: null, mid: null, inner: null, median: null });
  });

  it('maps quantile indices to per-horizon bands at t0 + horizon', () => {
    const fan = buildFan(prediction());
    const t0 = parseApiTime('2021-08-06T12:58:00');
    expect(fan.map((p) => p.t)).toEqual([15, 30, 45, 60].map((h) => t0 + h * MINUTE));
    expect(fan[3]).toEqual({
      t: t0 + 60 * MINUTE,
      horizon: 60,
      outer: [62, 185],
      mid: [80, 143],
      inner: [93, 126],
      median: 108,
    });
  });

  it('sorts shuffled quantile columns and horizons before building bands', () => {
    const p = prediction();
    // Permute quantile columns (reverse) and horizon rows (reverse) consistently.
    const shuffled = prediction({
      quantiles: [...Q].reverse(),
      horizons: [...p.horizons].reverse(),
      values: [...p.values].reverse().map((row) => [...row].reverse()),
    });
    expect(sortForecast(shuffled)).toEqual(sortForecast(p));
    expect(buildFan(shuffled)).toEqual(buildFan(p));
  });

  it('keeps bands ordered [low, high] even when quantiles cross', () => {
    const crossed = prediction({ horizons: [15], values: [[130, 105, 125, 115, 110, 125, 100]] });
    const [pt] = buildFan(crossed);
    expect(pt?.outer).toEqual([100, 130]);
    expect(pt?.inner).toEqual([110, 125]);
  });

  it('anchors the fan at the observed reading at t0 when provided', () => {
    const fan = buildFan(prediction(), 118);
    expect(fan).toHaveLength(5);
    expect(fan[0]).toMatchObject({ horizon: 0, outer: [118, 118], inner: [118, 118], median: 118 });
    expect(buildFan(prediction(), null)).toHaveLength(4);
  });
});

describe('threshold crossings', () => {
  it('uses the detector rule: hypo <= threshold, hyper >= threshold', () => {
    expect(crossing(70, 70, 180)).toBe('hypo');
    expect(crossing(70.01, 70, 180)).toBeNull();
    expect(crossing(180, 70, 180)).toBe('hyper');
    expect(crossing(179.9, 70, 180)).toBeNull();
  });

  it('marks every horizon × quantile cell outside the thresholds', () => {
    const m = crossingMatrix(sortForecast(prediction()), 70, 180);
    expect(m).toHaveLength(4);
    expect(m[0]).toEqual([null, null, null, null, null, null, null]);
    expect(m[3]).toEqual(['hypo', null, null, null, null, null, 'hyper']);
    expect(m.flat().filter(Boolean)).toHaveLength(2);
  });
});

describe('reading series', () => {
  const r = (timestamp: string, glucose_mg_dl: number): StoredReading => ({
    patient_id: '1001',
    timestamp,
    glucose_mg_dl,
    raw_mg_dl: glucose_mg_dl,
    flag: 'ok',
  });

  it('sorts readings and breaks the line inside gaps longer than the data-gap limit', () => {
    const pts = readingSeries(
      [r('2021-08-06T12:15:00', 110), r('2021-08-06T12:00:00', 100), r('2021-08-06T14:15:00', 140)],
      60,
    );
    expect(pts.map((p) => p.glucose)).toEqual([100, 110, null, 140]);
    expect(pts[2]?.t).toBe(parseApiTime('2021-08-06T13:15:00'));
  });

  it('merges readings and fan rows that share t0', () => {
    const readings = readingSeries([r('2021-08-06T12:43:00', 120), r('2021-08-06T12:58:00', 118)], 60);
    const rows = mergeChartRows(readings, buildFan(prediction(), 118));
    expect(rows).toHaveLength(2 + 4);
    expect(rows[1]).toMatchObject({ t: parseApiTime('2021-08-06T12:58:00'), glucose: 118, median: 118 });
    expect(rows.map((x) => x.t)).toEqual([...rows.map((x) => x.t)].sort((a, b) => a - b));
  });
});
