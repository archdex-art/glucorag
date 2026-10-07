import { ApiError, NetworkError, NotFoundError, UnauthorizedError } from './errors';
import type {
  Account,
  AlertQuery,
  Cohort,
  CycleResult,
  Device,
  ExportFormat,
  ExportKind,
  Forecast,
  Health,
  History,
  HistoryQuery,
  ImportDates,
  ImportResult,
  ImportUnit,
  MeHistory,
  MeInfo,
  MeStatus,
  ModelInfo,
  ProfileInput,
  ReadingInput,
  SampleResult,
  ServiceStats,
  StoredAlert,
} from './types';

type QueryValue = string | number | boolean | null | undefined;

export interface ApiClientOptions {
  /** Called once per 401 on a request that needs a session, before the UnauthorizedError is thrown. */
  onUnauthorized?: () => void;
  /** Injected for tests; defaults to the global fetch. */
  fetchImpl?: typeof fetch;
  /** Prefix for API paths; same origin by default. */
  baseUrl?: string;
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  query?: Record<string, QueryValue>;
  /** Sent as JSON. */
  json?: unknown;
  /** Sent as is with `contentType`. */
  text?: string;
  contentType?: string;
  signal?: AbortSignal;
  accept?: string;
  /**
   * A 401 here is an answer, not a lost session (wrong password at sign-in, signed out at boot):
   * throw without notifying `onUnauthorized`.
   */
  expect401?: boolean;
}

export function buildPath(path: string, query?: Record<string, QueryValue>): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== '') params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** A readable message from FastAPI's error body: a string detail, or the messages of a validation list. */
async function errorDetail(res: Response): Promise<{ message: string; detail: unknown }> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    body = undefined;
  }
  const record = body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string, unknown>) : null;
  const inner = record && 'detail' in record ? record.detail : undefined;
  // Bodies with more than `detail` (e.g. a rejected reading's `{reason, detail}`) stay whole.
  const detail = record && Object.keys(record).some((k) => k !== 'detail') ? record : (inner ?? body);
  let message = `${res.status} ${res.statusText || 'request failed'}`;
  if (typeof inner === 'string') message = inner;
  else if (Array.isArray(inner)) {
    const msgs = inner
      .map((e: unknown) => (e && typeof e === 'object' && 'msg' in e ? String(e.msg) : null))
      .filter((m): m is string => Boolean(m))
      .map((m) => m.replace(/^Value error, /, ''));
    if (msgs.length) message = msgs.join(' ');
  }
  return { message, detail };
}

/**
 * Typed wrapper over the GlucoRAG JSON API. It authenticates with the HttpOnly session cookie
 * (`credentials: 'same-origin'`); no credential is ever readable by, or stored from, JavaScript.
 */
export class ApiClient {
  private readonly onUnauthorized: (() => void) | undefined;
  private readonly fetchImpl: typeof fetch;
  private readonly baseUrl: string;

  constructor(options: ApiClientOptions = {}) {
    this.onUnauthorized = options.onUnauthorized;
    this.fetchImpl = options.fetchImpl ?? ((input, init) => globalThis.fetch(input, init));
    this.baseUrl = options.baseUrl ?? '';
  }

  async request(path: string, options: RequestOptions = {}): Promise<Response> {
    const headers = new Headers({ Accept: options.accept ?? 'application/json' });
    let body: string | undefined;
    if (options.json !== undefined) {
      headers.set('Content-Type', 'application/json');
      body = JSON.stringify(options.json);
    } else if (options.text !== undefined) {
      headers.set('Content-Type', options.contentType ?? 'text/plain');
      body = options.text;
    }
    let res: Response;
    try {
      res = await this.fetchImpl(this.baseUrl + buildPath(path, options.query), {
        method: options.method ?? 'GET',
        headers,
        body,
        signal: options.signal,
        credentials: 'same-origin',
        cache: 'no-store',
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') throw err;
      throw new NetworkError(err instanceof Error ? err.message : 'network error', { cause: err });
    }
    if (res.ok) return res;
    const { message, detail } = await errorDetail(res);
    if (res.status === 401) {
      if (!options.expect401) this.onUnauthorized?.();
      throw new UnauthorizedError(message);
    }
    if (res.status === 404) throw new NotFoundError(message, detail);
    const retry = Number(res.headers.get('Retry-After'));
    throw new ApiError(res.status, message, detail, Number.isFinite(retry) && retry > 0 ? retry : null);
  }

  async getJson<T>(path: string, options?: RequestOptions): Promise<T> {
    const res = await this.request(path, options);
    return (await res.json()) as T;
  }

  async send<T>(path: string, options: RequestOptions): Promise<T> {
    const res = await this.request(path, options);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  // ---------- Accounts ----------

  /** The signed-in account; UnauthorizedError when signed out (not reported as a lost session). */
  account(signal?: AbortSignal): Promise<Account> {
    return this.getJson('/auth/me', { signal, expect401: true });
  }

  signIn(email: string, password: string): Promise<Account> {
    return this.send('/auth/login', { method: 'POST', json: { email, password }, expect401: true });
  }

  signUp(email: string, password: string): Promise<Account> {
    return this.send('/auth/register', { method: 'POST', json: { email, password } });
  }

  signOut(): Promise<void> {
    return this.send('/auth/logout', { method: 'POST', expect401: true });
  }

  changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return this.send('/auth/password', {
      method: 'POST',
      json: { current_password: currentPassword, new_password: newPassword },
    });
  }

  // ---------- A person's own data (/me) ----------

  me(signal?: AbortSignal): Promise<MeInfo> {
    return this.getJson('/me', { signal });
  }

  saveProfile(profile: ProfileInput): Promise<MeInfo> {
    return this.send('/me/profile', { method: 'PUT', json: profile });
  }

  status(signal?: AbortSignal): Promise<MeStatus> {
    return this.getJson('/me/status', { signal });
  }

  myHistory(hours: number, signal?: AbortSignal): Promise<MeHistory> {
    return this.getJson('/me/history', { query: { hours }, signal });
  }

  myAlerts(limit: number, signal?: AbortSignal): Promise<StoredAlert[]> {
    return this.getJson('/me/alerts', { query: { limit }, signal });
  }

  /** 422 with `detail = {reason, detail}` when the reading is refused. */
  addReading(reading: ReadingInput): Promise<CycleResult> {
    return this.send('/me/readings', { method: 'POST', json: reading });
  }

  importFile(text: string, tz: string, unit: ImportUnit, dates: ImportDates = 'auto'): Promise<ImportResult> {
    return this.send('/me/import', { method: 'POST', query: { tz, unit, dates }, text, contentType: 'text/csv' });
  }

  loadSample(): Promise<SampleResult> {
    return this.send('/me/sample', { method: 'POST' });
  }

  async exportReadings(): Promise<{ blob: Blob; filename: string }> {
    const res = await this.request('/me/export', { accept: 'text/csv' });
    const named = /filename="?([^";]+)"?/.exec(res.headers.get('Content-Disposition') ?? '');
    return { blob: await res.blob(), filename: named?.[1] ?? 'glucorag-readings.csv' };
  }

  deleteReadings(): Promise<void> {
    return this.send('/me/readings', { method: 'DELETE' });
  }

  deleteAccount(password: string): Promise<void> {
    return this.send('/me', { method: 'DELETE', json: { password } });
  }

  /** Phones signed in with a device token. */
  devices(signal?: AbortSignal): Promise<Device[]> {
    return this.getJson('/me/devices', { signal });
  }

  /** Signs one phone out; 404 when the id is not one of yours. */
  revokeDevice(id: number): Promise<void> {
    return this.send(`/me/devices/${id}`, { method: 'DELETE' });
  }

  // ---------- Staff (clinician session) ----------

  health(signal?: AbortSignal): Promise<Health> {
    return this.getJson('/healthz', { signal });
  }

  cohort(signal?: AbortSignal): Promise<Cohort> {
    return this.getJson('/cohort/risk', { signal });
  }

  forecast(patientId: string, signal?: AbortSignal): Promise<Forecast> {
    return this.getJson(`/patients/${encodeURIComponent(patientId)}/forecast`, { signal });
  }

  history(patientId: string, query: HistoryQuery = {}, signal?: AbortSignal): Promise<History> {
    return this.getJson(`/patients/${encodeURIComponent(patientId)}/history`, {
      query: { ...query },
      signal,
    });
  }

  alerts(query: AlertQuery = {}, signal?: AbortSignal): Promise<StoredAlert[]> {
    return this.getJson('/alerts', { query: { ...query }, signal });
  }

  model(signal?: AbortSignal): Promise<ModelInfo> {
    return this.getJson('/model', { signal });
  }

  stats(signal?: AbortSignal): Promise<ServiceStats> {
    return this.getJson('/stats', { signal });
  }

  /** Staff export as a Blob, so it downloads with the session rather than through a link. */
  async exportBlob(
    kind: ExportKind,
    format: ExportFormat,
    filters: { patient_id?: string; since?: string; until?: string } = {},
  ): Promise<Blob> {
    const res = await this.request('/export', {
      query: { kind, format, ...filters },
      accept: format === 'csv' ? 'text/csv' : 'application/json',
    });
    return res.blob();
  }
}
