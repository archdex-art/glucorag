import type { CohortStatus, PatientRisk, RiskFlag } from '../api/types';
import { formatElapsed } from './time';

export const STATUS_LABEL: Record<CohortStatus, string> = {
  at_risk: 'Needs attention',
  data_gap: 'Not reporting',
  warming_up: 'Warming up',
  ok: 'Stable',
  no_data: 'No readings yet',
};

/** Ward sections, top to bottom. */
export const SECTION_ORDER: readonly CohortStatus[] = ['at_risk', 'data_gap', 'warming_up', 'ok', 'no_data'];

const SEVERITY_RANK: Record<string, number> = { low: 1, medium: 2, high: 3 };

/** Backend urgency order inside "Needs attention" (glucorag.service._cohort_rank). */
const AT_RISK_RANK: Record<string, number> = { high: 0, medium: 2, low: 3 };

/** Flag with the earliest horizon (ties: higher severity first). */
export function earliestRisk(p: Pick<PatientRisk, 'risk'>): RiskFlag | null {
  let best: RiskFlag | null = null;
  for (const f of p.risk) {
    if (
      !best ||
      f.horizon_min < best.horizon_min ||
      (f.horizon_min === best.horizon_min &&
        (SEVERITY_RANK[f.severity] ?? 0) > (SEVERITY_RANK[best.severity] ?? 0))
    ) {
      best = f;
    }
  }
  return best;
}

const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

function compareAtRisk(a: PatientRisk, b: PatientRisk): number {
  const rank = (AT_RISK_RANK[a.severity ?? 'low'] ?? 3) - (AT_RISK_RANK[b.severity ?? 'low'] ?? 3);
  if (rank) return rank;
  const ha = earliestRisk(a)?.horizon_min ?? Number.POSITIVE_INFINITY;
  const hb = earliestRisk(b)?.horizon_min ?? Number.POSITIVE_INFINITY;
  return ha - hb || collator.compare(a.patient_id, b.patient_id);
}

/** Longest silence first; patients without readings last. */
function compareSilence(a: PatientRisk, b: PatientRisk): number {
  const ma = a.minutes_since_last;
  const mb = b.minutes_since_last;
  if (ma === null && mb === null) return collator.compare(a.patient_id, b.patient_id);
  if (ma === null) return 1;
  if (mb === null) return -1;
  return mb - ma || collator.compare(a.patient_id, b.patient_id);
}

export interface WardSection {
  status: CohortStatus;
  label: string;
  patients: PatientRisk[];
}

/** Every section in display order, empty ones included. */
export function wardSections(patients: readonly PatientRisk[]): WardSection[] {
  return SECTION_ORDER.map((status) => {
    const rows = patients.filter((p) => p.status === status);
    rows.sort(status === 'at_risk' ? compareAtRisk : compareSilence);
    return { status, label: STATUS_LABEL[status], patients: rows };
  });
}

export interface WardFilter {
  search: string;
  /** 'all', a diabetes type, or 'unknown' for patients without one. */
  diabetesType: string;
}

export const EMPTY_FILTER: WardFilter = { search: '', diabetesType: 'all' };

export function filterWard(patients: readonly PatientRisk[], f: WardFilter): PatientRisk[] {
  const needle = f.search.trim().toLowerCase();
  return patients.filter(
    (p) =>
      (!needle || p.patient_id.toLowerCase().includes(needle)) &&
      (f.diabetesType === 'all' ||
        (f.diabetesType === 'unknown' ? !p.diabetes_type : p.diabetes_type === f.diabetesType)),
  );
}

export function riskSentence(f: Pick<RiskFlag, 'type' | 'horizon_min'>): string {
  return `${f.type === 'hypo' ? 'Hypo' : 'Hyper'} predicted in ${f.horizon_min} min`;
}

/** One-line assessment for a ward row, in the ward's own words. */
export function assessment(p: PatientRisk): string {
  switch (p.status) {
    case 'at_risk': {
      const f = earliestRisk(p);
      return f ? riskSentence(f) : STATUS_LABEL.at_risk;
    }
    case 'data_gap':
      return p.minutes_since_last === null ? 'No reading received' : `No reading for ${formatElapsed(p.minutes_since_last)}`;
    case 'warming_up':
      return 'Warming up (forecast starts after 2 h of readings)';
    case 'ok':
      return 'Stable';
    case 'no_data':
      return 'No readings yet';
  }
}
