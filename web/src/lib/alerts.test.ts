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

describe('alert sentences at the display precision', () => {
  it('says "at" the limit when the crossing rounds to zero in the reader’s unit', () => {
    expect(personAlertSentence(alert({}), 'mmol/L')).toBe(
      'The upper edge of your forecast band reached 10.0 mmol/L in 45 min, at 10.0.',
    );
    expect(alertSentence(alert({}))).toBe('In 45 min the q0.75 forecast reaches 180 mg/dL, at 180.');
  });

  it('keeps the distance once it shows at the display precision', () => {
    // 182 mg/dL: 2 above 180 in mg/dL, but 0.1 above 10.0 in mmol/L.
    const a = alert({ details: { value_mg_dl: 182, extreme_mg_dl: 182, margin_mg_dl: 2 } });
    expect(personAlertSentence(a, 'mg/dL')).toBe('The upper edge of your forecast band reached 182 mg/dL in 45 min, 2 above 180.');
    expect(personAlertSentence(a, 'mmol/L')).toBe('The upper edge of your forecast band reached 10.1 mmol/L in 45 min, 0.1 above 10.0.');
  });

  it('measures lows below the limit', () => {
    const a = alert({ type: 'hypo', details: { quantile: 0.25, value_mg_dl: 64, extreme_mg_dl: 64, margin_mg_dl: 6 } });
    expect(personAlertSentence(a, 'mg/dL')).toBe('The lower edge of your forecast band reached 64 mg/dL in 45 min, 6 below 70.');
  });
});
