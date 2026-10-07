import { describe, expect, it } from 'vitest';
import type { MeStatus, PatientRisk, RiskFlag, StoredPrediction } from '../api/types';
import { ENDED_AFTER_MIN, noForecastDetail, personStatus, riskDetail } from './personStatus';

const MODEL = {
  version: 'v1',
  interval_min: 15,
  lookback_min: 120,
  horizon_min: 60,
  data_gap_min: 60,
  hypo_mg_dl: 70,
  hyper_mg_dl: 180,
};
const LAST = '2026-10-06T12:00:00+00:00';

function flag(over: Partial<RiskFlag>): RiskFlag {
  return {
    type: 'hypo',
    horizon_min: 30,
    quantile: 0.25,
    value_mg_dl: 64,
    extreme_mg_dl: 64,
    margin_mg_dl: 6,
    severity: 'medium',
    ...over,
  };
}

const PREDICTION: StoredPrediction = {
  id: 1,
  patient_id: 'p',
  t0: LAST,
  horizons: [15, 30, 45, 60],
  quantiles: [0.5],
  values: [[100], [100], [100], [100]],
  model_version: 'v1',
  latency_ms: 1,
  created_at: LAST,
};

function status(row: Partial<PatientRisk>, over: Partial<MeStatus> = {}): MeStatus {
  return {
    status: {
      patient_id: 'p',
      diabetes_type: 'T1D',
      status: 'ok',
      severity: null,
      last_reading: LAST,
      minutes_since_last: 4,
      stale: false,
      latest_t0: LAST,
      model_version: 'v1',
      risk: [],
      active_alerts: [],
      last_glucose_mg_dl: 100,
      trend_mg_dl_per_min: 0,
      forecast: null,
      ...row,
    },
    prediction: PREDICTION,
    fresh: true,
    hypo_quantile: 0.25,
    hyper_quantile: 0.75,
    now: LAST,
    model: MODEL,
    ...over,
  };
}

describe('the status sentence', () => {
  it('names a predicted low or high with its timing', () => {
    expect(personStatus(status({ status: 'at_risk', risk: [flag({ horizon_min: 25 })] })).sentence).toBe('Low predicted in 25 min');
    const high = personStatus(status({ status: 'at_risk', risk: [flag({ type: 'hyper', horizon_min: 15, value_mg_dl: 190 })] }));
    expect(high).toMatchObject({ kind: 'high', sentence: 'High predicted in 15 min', urgent: false });
  });

  it('leads with the earliest flag; a low wins a tie; high severity is urgent', () => {
    const both = personStatus(
      status({
        status: 'at_risk',
        risk: [flag({ type: 'hyper', horizon_min: 45 }), flag({ type: 'hypo', horizon_min: 15, severity: 'high' })],
      }),
    );
    expect(both).toMatchObject({ kind: 'low', sentence: 'Low predicted in 15 min', urgent: true });
    expect(both.flags.map((f) => f.type)).toEqual(['hypo', 'hyper']);
    const tie = personStatus(status({ status: 'at_risk', risk: [flag({ type: 'hyper', horizon_min: 30 }), flag({ horizon_min: 30 })] }));
    expect(tie.kind).toBe('low');
  });

  it('says "now" when the current value is already past the threshold (inclusive)', () => {
    const hyper = flag({ type: 'hyper', horizon_min: 15, value_mg_dl: 196 });
    const at = (v: number, f: RiskFlag) => personStatus(status({ status: 'at_risk', risk: [f], last_glucose_mg_dl: v })).sentence;
    expect(at(198, hyper)).toBe('High now');
    expect(at(180, hyper)).toBe('High now');
    expect(at(179, hyper)).toBe('High predicted in 15 min');
    expect(at(70, flag({ horizon_min: 30 }))).toBe('Low now');
    expect(at(71, flag({ horizon_min: 30 }))).toBe('Low predicted in 30 min');
  });

  it('never says "in range" beside an out-of-range reading when only the band is in range', () => {
    const band = { t0: LAST, horizons: [15, 30, 45, 60], low_quantile: 0.25, high_quantile: 0.75, low: [150], median: [165], high: [178] };
    const ok = (v: number) => personStatus(status({ status: 'ok', last_glucose_mg_dl: v, forecast: band }));
    expect(ok(184)).toMatchObject({ kind: 'high', sentence: 'High now, back in range within 15 min' });
    expect(ok(180)).toMatchObject({ kind: 'high' }); // inclusive, as the alert rule
    expect(ok(179)).toMatchObject({ kind: 'in_range', sentence: 'In range for the next hour' });
    expect(ok(70)).toMatchObject({ kind: 'low', sentence: 'Low now, back in range within 15 min' });
  });

  it('covers in range, collecting and no readings', () => {
    expect(personStatus(status({ status: 'ok' })).sentence).toBe('In range for the next hour');
    expect(personStatus(status({ status: 'warming_up' }, { fresh: false, prediction: null }))).toMatchObject({
      kind: 'collecting',
      sentence: 'Collecting readings',
    });
    expect(personStatus(status({ status: 'no_data', last_reading: null }, { prediction: null, fresh: false }))).toMatchObject({
      kind: 'no_readings',
      sentence: 'No readings yet',
    });
  });

  it('says there is no current forecast for stale, old and gapped data', () => {
    const stale = personStatus(status({ status: 'data_gap', stale: true, minutes_since_last: 180 }, { fresh: false }));
    expect(stale).toMatchObject({ kind: 'stale', sentence: 'No current forecast', pastForecast: true });
    const ended = personStatus(status({ status: 'data_gap', stale: true, minutes_since_last: ENDED_AFTER_MIN }, { fresh: false }));
    expect(ended.kind).toBe('ended');
    const gap = personStatus(status({ status: 'data_gap', stale: false }, { fresh: false, prediction: null }));
    expect(gap).toMatchObject({ kind: 'gap', sentence: 'No current forecast', pastForecast: false });
  });

  it('marks the stored forecast as past only when it was made from the latest reading', () => {
    const older = { ...PREDICTION, t0: '2026-10-06T11:00:00+00:00' };
    expect(personStatus(status({ status: 'data_gap', stale: true, minutes_since_last: 200 }, { fresh: false, prediction: older })).pastForecast).toBe(false);
    expect(personStatus(status({ status: 'ok' })).pastForecast).toBe(false);
  });
});

describe('detail sentences', () => {
  it('phrases a low as the lower edge of the band, in the reader’s unit', () => {
    const f = flag({ value_mg_dl: 64, extreme_mg_dl: 64, horizon_min: 25 });
    expect(riskDetail(f, 'mg/dL', MODEL)).toBe('The lower edge of your forecast band reaches 64 mg/dL in 25 min, 6 below 70.');
    expect(riskDetail(f, 'mmol/L', MODEL)).toBe('The lower edge of your forecast band reaches 3.6 mmol/L in 25 min, 0.3 below 3.9.');
  });

  it('adds how far it goes when the extreme lies beyond the first crossing', () => {
    const f = flag({ type: 'hyper', value_mg_dl: 190, extreme_mg_dl: 230, horizon_min: 15, margin_mg_dl: 50 });
    expect(riskDetail(f, 'mg/dL', MODEL)).toBe(
      'The upper edge of your forecast band reaches 190 mg/dL in 15 min, 10 above 180. It goes as high as 230 mg/dL within the hour.',
    );
    expect(riskDetail(flag({ value_mg_dl: 70 }), 'mg/dL', MODEL)).toContain('reaches 70 mg/dL in 30 min, at 70.');
  });

  it('explains warming up with readings and time still needed', () => {
    const s = status({ status: 'warming_up' }, { fresh: false, prediction: null });
    const text = noForecastDetail(personStatus(s), s, { needed: 3, minutes: 45, runStart: 0, afterGap: false });
    expect(text).toBe('Forecasts start once there are 2 hours of readings. 3 more readings needed, about 45 min.');
    const one = noForecastDetail(personStatus(s), s, { needed: 1, minutes: 15, runStart: 0, afterGap: false });
    expect(one).toContain('1 more reading needed, about 15 min.');
  });

  it('explains stale data with its age and the fix', () => {
    const s = status({ status: 'data_gap', stale: true, minutes_since_last: 180 }, { fresh: false });
    expect(noForecastDetail(personStatus(s), s, null)).toBe(
      'No forecast: your latest reading is 3 h old. Forecasts need a reading within the last hour. Add a reading or import a newer file.',
    );
  });

  it('dates old imports and points at the past forecast', () => {
    const s = status({ status: 'data_gap', stale: true, minutes_since_last: 3 * 24 * 60 }, { fresh: false });
    const text = noForecastDetail(personStatus(s), s, null)!;
    expect(text).toMatch(/^Your data ends \d{1,2} Oct 2026, \d\d:\d\d\. The forecast below was made then\./);
    const none = status({ status: 'data_gap', stale: true, minutes_since_last: 3 * 24 * 60 }, { fresh: false, prediction: null });
    expect(noForecastDetail(personStatus(none), none, null)).toMatch(/For a forecast, add a reading or import a newer file\.$/);
  });

  it('explains a gap inside recent readings', () => {
    const s = status({ status: 'data_gap', stale: false }, { fresh: false, prediction: null });
    expect(noForecastDetail(personStatus(s), s, { needed: 5, minutes: 75, runStart: 0, afterGap: true })).toBe(
      'Your recent readings have a gap of more than an hour. Forecasts restart after 2 hours of readings. 5 more readings needed, about 1 h 15 min.',
    );
  });

  it('has nothing to add while a forecast is current', () => {
    const s = status({ status: 'ok' });
    expect(noForecastDetail(personStatus(s), s, null)).toBeNull();
  });
});
