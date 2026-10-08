import { describe, expect, it } from 'vitest';
import type { MeStatus, PatientRisk, RiskFlag, StoredPrediction } from '../api/types';
import { ENDED_AFTER_MIN, noForecastDetail, personStatus } from './personStatus';

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

const BAND = { t0: LAST, horizons: [15, 30, 45, 60], low_quantile: 0.25, high_quantile: 0.75, low: [150, 160, 165, 170], median: [170, 185, 190, 192], high: [190, 200, 210, 215] };

const say = (s: MeStatus, unit: 'mg/dL' | 'mmol/L' = 'mg/dL') => personStatus(s, unit);

describe('the status sentence', () => {
  it('says which limit a predicted low or high crosses, when, and how far it could go', () => {
    const low = say(status({ status: 'at_risk', risk: [flag({ horizon_min: 25, value_mg_dl: 69, extreme_mg_dl: 68 })] }));
    expect(low).toMatchObject({ kind: 'low', sentence: 'Heading below 70 in about 25 min (could reach 68).', details: [] });
    const high = say(status({ status: 'at_risk', risk: [flag({ type: 'hyper', horizon_min: 15, value_mg_dl: 190, extreme_mg_dl: 205 })] }));
    expect(high).toMatchObject({ kind: 'high', sentence: 'Heading above 180 in about 15 min (could reach 205).', urgent: false });
    const mmol = say(status({ status: 'at_risk', risk: [flag({ horizon_min: 25, extreme_mg_dl: 68 })] }), 'mmol/L');
    expect(mmol.sentence).toBe('Heading below 3.9 in about 25 min (could reach 3.8).');
    const mmolHigh = say(status({ status: 'at_risk', risk: [flag({ type: 'hyper', horizon_min: 45, extreme_mg_dl: 205 })] }), 'mmol/L');
    expect(mmolHigh.sentence).toBe('Heading above 10.0 in about 45 min (could reach 11.4).');
  });

  it('says "soon" without a positive horizon and drops the brackets without a value', () => {
    const now = say(status({ status: 'at_risk', risk: [flag({ horizon_min: 0, extreme_mg_dl: 66 })] }));
    expect(now.sentence).toBe('Heading below 70 soon (could reach 66).');
    const noValue = say(status({ status: 'at_risk', risk: [flag({ type: 'hyper', horizon_min: 15, extreme_mg_dl: Number.NaN })] }));
    expect(noValue.sentence).toBe('Heading above 180 in about 15 min.');
  });

  it('leads with the earliest flag; a low wins a tie; high severity is urgent; the rest follow below', () => {
    const both = say(
      status({
        status: 'at_risk',
        risk: [flag({ type: 'hyper', horizon_min: 45, extreme_mg_dl: 210 }), flag({ type: 'hypo', horizon_min: 15, severity: 'high' })],
      }),
    );
    expect(both).toMatchObject({
      kind: 'low',
      sentence: 'Heading below 70 in about 15 min (could reach 64).',
      details: ['High likely in about 45 min (could reach 210 mg/dL).'],
      urgent: true,
    });
    expect(both.flags.map((f) => f.type)).toEqual(['hypo', 'hyper']);
    const tie = say(status({ status: 'at_risk', risk: [flag({ type: 'hyper', horizon_min: 30 }), flag({ horizon_min: 30 })] }));
    expect(tie.kind).toBe('low');
  });

  it('leads with the reading when it is already past the limit (inclusive)', () => {
    const hyper = flag({ type: 'hyper', horizon_min: 15, value_mg_dl: 196, extreme_mg_dl: 230 });
    const at = (v: number, f: RiskFlag) =>
      say(status({ status: 'at_risk', risk: [f], last_glucose_mg_dl: v, trend_mg_dl_per_min: 1.5, forecast: BAND }));
    expect(at(198, hyper)).toMatchObject({
      kind: 'high',
      sentence: '198 mg/dL, rising. Likely about 185 in 30 min.',
      details: ['Could go as high as 230 mg/dL within the hour.'],
    });
    expect(at(180, hyper).sentence).toBe('180 mg/dL, rising. Likely about 185 in 30 min.');
    expect(at(179, hyper).sentence).toBe('Heading above 180 in about 15 min (could reach 230).');
    expect(at(70, flag({ horizon_min: 30 })).details).toEqual(['Could go as low as 64 mg/dL within the hour.']);
    expect(at(71, flag({ horizon_min: 30 })).sentence).toBe('Heading below 70 in about 30 min (could reach 64).');
  });

  it('never says "in range" beside an out-of-range reading when no low or high is likely', () => {
    const ok = (v: number) => say(status({ status: 'ok', last_glucose_mg_dl: v, forecast: BAND }));
    expect(ok(198)).toMatchObject({ kind: 'high', sentence: '198 mg/dL, steady. Likely about 185 in 30 min.', details: [] });
    expect(ok(180)).toMatchObject({ kind: 'high' }); // inclusive, as the alert rule
    expect(ok(179)).toMatchObject({ kind: 'in_range', sentence: 'In range for the next hour.' });
    expect(ok(70)).toMatchObject({ kind: 'low', sentence: '70 mg/dL, steady. Likely about 185 in 30 min.' });
    const noTrend = say(status({ status: 'ok', last_glucose_mg_dl: 198, trend_mg_dl_per_min: null, forecast: null }), 'mmol/L');
    expect(noTrend.sentence).toBe('11.0 mmol/L.');
  });

  it('covers in range, collecting and no readings', () => {
    expect(say(status({ status: 'ok' }))).toMatchObject({
      sentence: 'In range for the next hour.',
      details: ['Likely to stay between 70 and 180 mg/dL.'],
    });
    expect(say(status({ status: 'ok' }), 'mmol/L').details).toEqual(['Likely to stay between 3.9 and 10.0 mmol/L.']);
    expect(say(status({ status: 'warming_up' }, { fresh: false, prediction: null }))).toMatchObject({
      kind: 'collecting',
      sentence: 'Collecting readings.',
    });
    expect(say(status({ status: 'no_data', last_reading: null }, { prediction: null, fresh: false }))).toMatchObject({
      kind: 'no_readings',
      sentence: 'No readings yet.',
    });
  });

  it('says there is no current forecast for stale, old and gapped data', () => {
    const stale = say(status({ status: 'data_gap', stale: true, minutes_since_last: 180 }, { fresh: false }));
    expect(stale).toMatchObject({ kind: 'stale', sentence: 'No current forecast.', pastForecast: true });
    const ended = say(status({ status: 'data_gap', stale: true, minutes_since_last: ENDED_AFTER_MIN }, { fresh: false }));
    expect(ended.kind).toBe('ended');
    const gap = say(status({ status: 'data_gap', stale: false }, { fresh: false, prediction: null }));
    expect(gap).toMatchObject({ kind: 'gap', sentence: 'No current forecast.', pastForecast: false });
  });

  it('marks the stored forecast as past only when it was made from the latest reading', () => {
    const older = { ...PREDICTION, t0: '2026-10-06T11:00:00+00:00' };
    expect(say(status({ status: 'data_gap', stale: true, minutes_since_last: 200 }, { fresh: false, prediction: older })).pastForecast).toBe(false);
    expect(say(status({ status: 'ok' })).pastForecast).toBe(false);
  });

  it('never uses forecast-band or quantile words', () => {
    const cases = [
      status({ status: 'at_risk', risk: [flag({}), flag({ type: 'hyper', horizon_min: 45 })] }),
      status({ status: 'at_risk', risk: [flag({})], last_glucose_mg_dl: 60, forecast: BAND }),
      status({ status: 'ok', last_glucose_mg_dl: 200, forecast: BAND }),
      status({ status: 'ok' }),
    ];
    for (const s of cases) {
      const p = say(s);
      expect([p.sentence, ...p.details].join(' ')).not.toMatch(/band|quantile|q0\.|edge/i);
    }
  });
});

describe('detail sentences', () => {
  it('explains warming up with readings and time still needed', () => {
    const s = status({ status: 'warming_up' }, { fresh: false, prediction: null });
    const text = noForecastDetail(say(s), s, { needed: 3, minutes: 45, runStart: 0, afterGap: false });
    expect(text).toBe('Forecasts start once there are 2 hours of readings. 3 more readings needed, about 45 min.');
    const one = noForecastDetail(say(s), s, { needed: 1, minutes: 15, runStart: 0, afterGap: false });
    expect(one).toContain('1 more reading needed, about 15 min.');
  });

  it('explains stale data with its age and the fix', () => {
    const s = status({ status: 'data_gap', stale: true, minutes_since_last: 180 }, { fresh: false });
    expect(noForecastDetail(say(s), s, null)).toBe(
      'No forecast: your latest reading is 3 h old. Forecasts need a reading within the last hour. Add a reading or import a newer file.',
    );
  });

  it('dates old imports and points at the past forecast', () => {
    const s = status({ status: 'data_gap', stale: true, minutes_since_last: 3 * 24 * 60 }, { fresh: false });
    const text = noForecastDetail(say(s), s, null)!;
    expect(text).toMatch(/^Your data ends \d{1,2} Oct 2026, \d\d:\d\d\. The forecast below was made then\./);
    const none = status({ status: 'data_gap', stale: true, minutes_since_last: 3 * 24 * 60 }, { fresh: false, prediction: null });
    expect(noForecastDetail(say(none), none, null)).toMatch(/For a forecast, add a reading or import a newer file\.$/);
  });

  it('explains a gap inside recent readings', () => {
    const s = status({ status: 'data_gap', stale: false }, { fresh: false, prediction: null });
    expect(noForecastDetail(say(s), s, { needed: 5, minutes: 75, runStart: 0, afterGap: true })).toBe(
      'Your recent readings have a gap of more than an hour. Forecasts restart after 2 hours of readings. 5 more readings needed, about 1 h 15 min.',
    );
  });

  it('has nothing to add while a forecast is current', () => {
    const s = status({ status: 'ok' });
    expect(noForecastDetail(say(s), s, null)).toBeNull();
  });
});
