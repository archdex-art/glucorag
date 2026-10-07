/**
 * Types mirroring the GlucoRAG FastAPI response models (glucorag/api/*.py, glucorag/service.py,
 * glucorag/core/storage.py). Datetimes are kept as the raw ISO strings the API returns; parse
 * them with `lib/time.ts`. Staff routes return naive server-local times; every `/me` route
 * returns offset-aware times, which display in the browser's own time zone.
 */

export type ApiDateTime = string;

export type CohortStatus = 'at_risk' | 'data_gap' | 'warming_up' | 'ok' | 'no_data';
export type RiskType = 'hypo' | 'hyper';
export type AlertType = RiskType | 'data_gap';
export type Severity = 'low' | 'medium' | 'high';
export type DiabetesType = 'T1D' | 'T2D';

export interface Health {
  status: string;
  model_version: string;
}

export interface RiskFlag {
  type: RiskType;
  /** Earliest horizon at which the selected quantile crosses the threshold. */
  horizon_min: number;
  quantile: number;
  value_mg_dl: number;
  extreme_mg_dl: number;
  margin_mg_dl: number;
  severity: Severity;
}

/** Latest fresh forecast reduced to the patient's alert band (service.ForecastBand). */
export interface ForecastBand {
  t0: ApiDateTime;
  /** Minutes after t0. */
  horizons: number[];
  /** The patient's hypo alert quantile (the band's lower edge). */
  low_quantile: number;
  /** The patient's hyper alert quantile (the band's upper edge). */
  high_quantile: number;
  low: number[];
  median: number[];
  high: number[];
}

export interface PatientRisk {
  patient_id: string;
  diabetes_type: DiabetesType | string | null;
  status: CohortStatus;
  severity: Severity | string | null;
  last_reading: ApiDateTime | null;
  minutes_since_last: number | null;
  stale: boolean;
  latest_t0: ApiDateTime | null;
  model_version: string | null;
  risk: RiskFlag[];
  active_alerts: string[];
  last_glucose_mg_dl: number | null;
  /** mg/dL per minute across the latest sampling interval; null without such a pair. */
  trend_mg_dl_per_min: number | null;
  /** Present only while the latest forecast was made from the last reading (at_risk / ok). */
  forecast: ForecastBand | null;
}

export interface Cohort {
  as_of: ApiDateTime;
  patients: PatientRisk[];
}

export interface Prediction {
  patient_id: string;
  t0: ApiDateTime;
  /** Forecast horizons in minutes after t0. */
  horizons: number[];
  /** Quantile levels (e.g. 0.02 … 0.98). */
  quantiles: number[];
  /** values[horizon index][quantile index], mg/dL. */
  values: number[][];
  model_version: string;
}

export interface StoredPrediction extends Prediction {
  id: number;
  latency_ms: number;
  /** UTC audit time (timezone-aware). */
  created_at: ApiDateTime;
}

export interface Forecast {
  prediction: StoredPrediction;
  risk: RiskFlag[];
  hypo_quantile: number;
  hyper_quantile: number;
}

export interface StoredReading {
  patient_id: string;
  timestamp: ApiDateTime;
  glucose_mg_dl: number;
  raw_mg_dl: number;
  flag: string;
}

export interface History {
  patient_id: string;
  readings: StoredReading[];
  predictions: StoredPrediction[];
}

export interface StoredAlert {
  id: number;
  patient_id: string;
  type: AlertType;
  horizon_min: number | null;
  severity: Severity | string | null;
  t_raised: ApiDateTime;
  t0: ApiDateTime | null;
  model_version: string | null;
  details: Record<string, unknown>;
}

export interface ReleaseStatus {
  promoted: boolean;
  current_version: string | null;
  last_promotion: Record<string, unknown> | null;
}

export interface ModelInfo {
  version: string;
  dataset: string;
  created_at: ApiDateTime;
  interval_min: number;
  lookback_min: number;
  horizon_min: number;
  quantiles: number[];
  static_features: string[];
  hyperparameters: Record<string, unknown>;
  weights_sha256: string;
  data_hash: string;
  evaluation: Record<string, unknown> | null;
  cross_individual_cv: Record<string, unknown> | null;
  in_silico: Record<string, unknown> | null;
  release: ReleaseStatus;
}

export interface LatencyStats {
  samples: number;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  cycle_mean_ms: number | null;
}

export interface Thresholds {
  hypo_mg_dl: number;
  hyper_mg_dl: number;
  hypo_quantile: number;
  hyper_quantile: number;
  data_gap_min: number;
  [key: string]: number;
}

export interface ServiceStats {
  started_at: ApiDateTime;
  uptime_s: number;
  model_version: string;
  clock: 'wall' | 'data' | string;
  as_of: ApiDateTime;
  counters: Record<string, number>;
  rejected_by_reason: Record<string, number>;
  alerts_by_type: Record<string, number>;
  data_gaps_by_source: Record<string, number>;
  latency: LatencyStats;
  storage: Record<string, number>;
  thresholds: Thresholds;
}

export interface HistoryQuery {
  since?: ApiDateTime;
  until?: ApiDateTime;
  limit?: number;
}

export interface AlertQuery {
  patient_id?: string;
  type?: AlertType;
  since?: ApiDateTime;
  until?: ApiDateTime;
  limit?: number;
}

export type ExportKind = 'predictions' | 'alerts';
export type ExportFormat = 'csv' | 'json';

// ---------- Accounts and the personal API (/auth, /me) ----------

export type Role = 'person' | 'clinician';
export type Unit = 'mg/dL' | 'mmol/L';
export type Sex = 'F' | 'M';
export type Sensitivity = 'standard' | 'cautious' | 'very_cautious';

/** `GET /auth/me`, and the body of register/login. */
export interface Account {
  email: string;
  role: Role;
  unit: Unit;
  has_profile: boolean;
}

export interface Profile {
  age: number;
  gender: Sex;
  bmi: number;
  diabetes_type: DiabetesType;
  /** Null when the stored quantiles match none of the three settings. */
  sensitivity: Sensitivity | null;
  hypo_quantile: number;
  hyper_quantile: number;
}

export interface ProfileInput {
  age: number;
  gender: Sex;
  bmi: number;
  diabetes_type: DiabetesType;
  sensitivity: Sensitivity;
  unit: Unit;
}

/** What the service tells a person about the model and its rules. */
export interface ModelFacts {
  version: string;
  interval_min: number;
  lookback_min: number;
  horizon_min: number;
  data_gap_min: number;
  hypo_mg_dl: number;
  hyper_mg_dl: number;
}

export interface MeInfo {
  email: string;
  role: Role;
  unit: Unit;
  profile: Profile | null;
  readings: { count: number; first: ApiDateTime | null; last: ApiDateTime | null };
  model: ModelFacts;
}

/** A phone signed in with a device token (`GET /me/devices`). */
export interface Device {
  id: number;
  device: string;
  created_at: ApiDateTime;
  last_used_at: ApiDateTime | null;
}

/** `POST /me/pairing`: a single-use code that signs a phone in, valid for 10 minutes. */
export interface PairingCode {
  /** `ABCD-EFGH`. */
  code: string;
  expires_at: ApiDateTime;
  /** The address the phone will use; guessed from the network when the site is opened on localhost. */
  server_url: string;
  server_url_guessed: boolean;
  /** `glucorag://pair?server=…&code=…`, what the QR encodes. */
  uri: string;
  /** Server-drawn standalone SVG of the QR. */
  qr_svg: string;
}

export interface MeStatus {
  status: PatientRisk;
  /** The latest stored forecast, current or not. */
  prediction: StoredPrediction | null;
  /** The forecast was made from the latest reading, which is recent enough. */
  fresh: boolean;
  hypo_quantile: number;
  hyper_quantile: number;
  now: ApiDateTime | null;
  model: ModelFacts;
}

export interface MeReading {
  timestamp: ApiDateTime;
  glucose_mg_dl: number;
  flag: string;
}

export interface MeHistory {
  readings: MeReading[];
  since: ApiDateTime | null;
  until: ApiDateTime | null;
}

export type CycleStatus = 'predicted' | 'data_gap' | 'warming_up' | 'rejected';

export interface CycleResult {
  patient_id: string;
  timestamp: ApiDateTime;
  status: CycleStatus;
  range_flag: string | null;
  reason: string | null;
  detail: string | null;
  prediction: Prediction | null;
  risk: RiskFlag[];
  alerts: StoredAlert[];
}

/** Why `POST /me/readings` refused a reading (422 body). */
export interface RejectedReading {
  reason: string;
  detail: string | null;
}

export interface ReadingInput {
  /** Offset-aware ISO time. */
  timestamp: string;
  glucose: number;
  unit: Unit;
}

export type ImportUnit = 'auto' | Unit;
/** Order of numeric dates such as 06-10-2026: day first, month first, or let the service decide. */
export type ImportDates = 'auto' | 'dmy' | 'mdy';

export interface ImportResult {
  format: 'libreview' | 'dexcom' | 'generic' | string;
  unit: Unit;
  /** How dates were read: ISO, day first, month first, or year first. */
  date_order: 'iso' | 'dmy' | 'mdy' | 'ymd';
  /** Day-first and month-first both fit; the service chose the one ending nearest to now. */
  date_ambiguous: boolean;
  rows_read: number;
  unusable_rows: number;
  older_than_window: number;
  already_present: number;
  accepted: number;
  /** Per-reading outcome counts: predicted, warming_up, data_gap, rejected_<reason>. */
  outcomes: Record<string, number>;
  first: ApiDateTime;
  last: ApiDateTime;
  window_days: number;
}

export interface SampleResult {
  loaded: number;
  outcomes: Record<string, number>;
  first: ApiDateTime;
  last: ApiDateTime;
}
