import { describe, expect, it } from 'vitest';
import type { StoredAlert } from '../api/types';
import { alertSentence, personAlertSentence } from './alerts';

function alert(over: Partial<StoredAlert> & { details?: Record<string, unknown> }): StoredAlert {
  return {
    id: 1,
    patient_id: 'p',
    type: 'hyper',
    horizon_min: 45,
    severity: 'low',
    t_raised: '2026-10-06T04:02:00+05:30',
    t0: '2026-10-06T04:02:00+05:30',
    model_version: 'v1',
    ...over,
    details: { quantile: 0.75, value_mg_dl: 180.3, extreme_mg_dl: 180.3, margin_mg_dl: 0.3, ...over.details },
  };
}

describe('staff alert sentences', () => {
  it('name the quantile and the threshold', () => {
    expect(alertSentence(alert({}))).toBe('In 45 min the q0.75 forecast reaches 180 mg/dL, at 180.');
    const a = alert({ type: 'hypo', details: { quantile: 0.25, value_mg_dl: 66, extreme_mg_dl: 64, margin_mg_dl: 6 } });
    expect(alertSentence(a)).toBe('In 45 min the q0.25 forecast reaches 64 mg/dL, 6 below 70.');
  });
});

describe('person alert sentences', () => {
  it('say when a low or high is likely and how far it could go, in the reader’s unit', () => {
    const low = alert({ type: 'hypo', horizon_min: 25, details: { quantile: 0.25, value_mg_dl: 69, extreme_mg_dl: 66, margin_mg_dl: 4 } });
    expect(personAlertSentence(low, 'mg/dL')).toBe('Low likely in about 25 min (could reach 66 mg/dL).');
    expect(personAlertSentence(low, 'mmol/L')).toBe('Low likely in about 25 min (could reach 3.7 mmol/L).');
    const high = alert({ details: { value_mg_dl: 191, extreme_mg_dl: 205, margin_mg_dl: 25 } });
    expect(personAlertSentence(high, 'mg/dL')).toBe('High likely in about 45 min (could reach 205 mg/dL).');
  });

  it('fall back to the first crossing, and to the hour without a horizon', () => {
    const a = alert({ horizon_min: null, details: { extreme_mg_dl: undefined, value_mg_dl: 190 } });
    expect(personAlertSentence(a, 'mg/dL')).toBe('High likely within the hour (could reach 190 mg/dL).');
  });

  it('never use forecast-band or quantile words', () => {
    const text = personAlertSentence(alert({}), 'mg/dL');
    expect(text).not.toMatch(/band|quantile|q0\.|edge/i);
  });

  it('explain a data gap', () => {
    const gap = alert({ type: 'data_gap', horizon_min: null, details: { minutes_since_last: 75 } });
    expect(personAlertSentence(gap, 'mg/dL')).toBe('No reading for 1 h 15 min, so forecasts paused.');
  });
});
