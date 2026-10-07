import { describe, expect, it } from 'vitest';
import type { PatientRisk, RiskFlag } from '../api/types';
import { EMPTY_FILTER, assessment, earliestRisk, filterWard, wardSections } from './ward';

function flag(type: 'hypo' | 'hyper', horizon_min: number, severity: RiskFlag['severity'] = 'low'): RiskFlag {
  return { type, horizon_min, quantile: 0.25, value_mg_dl: 65, extreme_mg_dl: 60, margin_mg_dl: 10, severity };
}

function patient(id: string, p: Partial<PatientRisk> = {}): PatientRisk {
  return {
    patient_id: id,
    diabetes_type: 'T1D',
    status: 'ok',
    severity: null,
    last_reading: '2021-08-06T12:58:00',
    minutes_since_last: 0,
    stale: false,
    latest_t0: '2021-08-06T12:58:00',
    model_version: 'shanghai-v1',
    risk: [],
    active_alerts: [],
    last_glucose_mg_dl: 120,
    trend_mg_dl_per_min: 0,
    forecast: null,
    ...p,
  };
}

const ids = (ps: PatientRisk[]) => ps.map((p) => p.patient_id);

describe('ward sections', () => {
  it('always returns the five sections in order, empty ones included', () => {
    const sections = wardSections([patient('1', { status: 'no_data' })]);
    expect(sections.map((s) => s.label)).toEqual([
      'Needs attention',
      'Not reporting',
      'Warming up',
      'Stable',
      'No readings yet',
    ]);
    expect(sections.map((s) => s.patients.length)).toEqual([0, 0, 0, 0, 1]);
    expect(wardSections([]).every((s) => s.patients.length === 0)).toBe(true);
  });

  it('sorts needs-attention rows by backend rank, then earliest horizon', () => {
    const rows = [
      patient('low-15', { status: 'at_risk', severity: 'low', risk: [flag('hyper', 15)] }),
      patient('med-45', { status: 'at_risk', severity: 'medium', risk: [flag('hyper', 45, 'medium')] }),
      patient('high-60', { status: 'at_risk', severity: 'high', risk: [flag('hypo', 60, 'high')] }),
      patient('med-30', { status: 'at_risk', severity: 'medium', risk: [flag('hyper', 60), flag('hypo', 30, 'medium')] }),
    ];
    expect(ids(wardSections(rows)[0]!.patients)).toEqual(['high-60', 'med-30', 'med-45', 'low-15']);
  });

  it('sorts other sections by minutes since the last reading, longest first', () => {
    const rows = [
      patient('a', { status: 'data_gap', minutes_since_last: 130 }),
      patient('b', { status: 'data_gap', minutes_since_last: 70_560 }),
      patient('c', { status: 'ok', minutes_since_last: 5 }),
      patient('d', { status: 'ok', minutes_since_last: 30 }),
      patient('e', { status: 'data_gap', minutes_since_last: 130 }),
    ];
    const s = wardSections(rows);
    expect(ids(s[1]!.patients)).toEqual(['b', 'a', 'e']);
    expect(ids(s[3]!.patients)).toEqual(['d', 'c']);
  });
});

describe('ward rows', () => {
  it('filters by id substring and diabetes type', () => {
    const rows = [patient('1001'), patient('2001', { diabetes_type: 'T2D' }), patient('9', { diabetes_type: null })];
    expect(ids(filterWard(rows, { ...EMPTY_FILTER, search: ' 00 ' }))).toEqual(['1001', '2001']);
    expect(ids(filterWard(rows, { ...EMPTY_FILTER, diabetesType: 'T2D' }))).toEqual(['2001']);
    expect(ids(filterWard(rows, { ...EMPTY_FILTER, diabetesType: 'unknown' }))).toEqual(['9']);
  });

  it('picks the earliest flag (ties: more severe) for the assessment', () => {
    expect(earliestRisk({ risk: [flag('hyper', 30, 'low'), flag('hypo', 30, 'high')] })?.type).toBe('hypo');
    expect(assessment(patient('1', { status: 'at_risk', risk: [flag('hyper', 45), flag('hypo', 15)] }))).toBe(
      'Hypo predicted in 15 min',
    );
    expect(assessment(patient('1', { status: 'data_gap', minutes_since_last: 130 }))).toBe('No reading for 2 h 10 min');
    expect(assessment(patient('1', { status: 'data_gap', minutes_since_last: 49 * 1440 }))).toBe('No reading for 49 days');
  });
});
