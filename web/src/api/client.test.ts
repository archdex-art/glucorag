import { describe, expect, it, vi } from 'vitest';
import { ApiClient, buildPath } from './client';
import { ApiError, NetworkError, NotFoundError, UnauthorizedError } from './errors';

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

/** A fresh Response per call (bodies are single-use). */
function mockFetch(make: () => Response) {
  return vi.fn<typeof fetch>(async () => make());
}

describe('ApiClient', () => {
  it('sends the session cookie (same-origin credentials) and no API key', async () => {
    const fetchImpl = mockFetch(() => jsonResponse({ email: 'a@b.co', role: 'person', unit: 'mg/dL', has_profile: false }));
    const api = new ApiClient({ fetchImpl });

    await api.account();

    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('/auth/me');
    expect(init?.credentials).toBe('same-origin');
    expect(init?.method).toBe('GET');
    const headers = new Headers(init?.headers);
    expect(headers.get('X-API-Key')).toBeNull();
    expect(headers.get('Accept')).toBe('application/json');
  });

  it('posts JSON bodies and decodes the answer', async () => {
    const fetchImpl = mockFetch(() => jsonResponse({ email: 'a@b.co', role: 'person', unit: 'mmol/L', has_profile: true }));
    const api = new ApiClient({ fetchImpl });

    const account = await api.signIn('a@b.co', 'correct horse');

    expect(account.unit).toBe('mmol/L');
    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('/auth/login');
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
    expect(JSON.parse(String(init?.body))).toEqual({ email: 'a@b.co', password: 'correct horse' });
  });

  it('posts an import as text/csv with the time zone, unit and date order in the query', async () => {
    const fetchImpl = mockFetch(() => jsonResponse({ accepted: 3 }));
    const api = new ApiClient({ fetchImpl });

    await api.importFile('timestamp,glucose\n', 'Europe/London', 'mmol/L', 'dmy');

    const [url, init] = fetchImpl.mock.calls[0]!;
    expect(url).toBe('/me/import?tz=Europe%2FLondon&unit=mmol%2FL&dates=dmy');
    expect(init?.method).toBe('POST');
    expect(new Headers(init?.headers).get('Content-Type')).toBe('text/csv');
    expect(init?.body).toBe('timestamp,glucose\n');
  });

  it('treats 204 as an empty success', async () => {
    const api = new ApiClient({ fetchImpl: mockFetch(() => new Response(null, { status: 204 })) });
    await expect(api.deleteReadings()).resolves.toBeUndefined();
  });

  it('encodes path segments and drops empty query parameters', async () => {
    const fetchImpl = mockFetch(() => jsonResponse({ patient_id: 'a/b', readings: [], predictions: [] }));
    const api = new ApiClient({ fetchImpl });

    await api.history('a/b', { since: '2021-08-06T06:58:00', limit: 100 });
    await api.alerts({ patient_id: undefined, type: 'hypo', limit: 5 });

    expect(fetchImpl.mock.calls[0]![0]).toBe('/patients/a%2Fb/history?since=2021-08-06T06%3A58%3A00&limit=100');
    expect(fetchImpl.mock.calls[1]![0]).toBe('/alerts?type=hypo&limit=5');
    expect(buildPath('/x', { a: '', b: null, c: 0 })).toBe('/x?c=0');
  });

  it('on a 401 for a session request notifies the session and throws UnauthorizedError', async () => {
    const onUnauthorized = vi.fn();
    const fetchImpl = mockFetch(() => jsonResponse({ detail: 'Not signed in' }, 401));
    const api = new ApiClient({ fetchImpl, onUnauthorized });

    const err = await api.status().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(UnauthorizedError);
    expect((err as UnauthorizedError).status).toBe(401);
    expect(onUnauthorized).toHaveBeenCalledTimes(1);
  });

  it('does not end the session for the 401s that are answers (wrong password, signed out at boot)', async () => {
    const onUnauthorized = vi.fn();
    const fetchImpl = mockFetch(() => jsonResponse({ detail: 'Email or password is incorrect.' }, 401));
    const api = new ApiClient({ fetchImpl, onUnauthorized });

    const login = await api.signIn('a@b.co', 'wrong password').catch((e: unknown) => e);
    const boot = await api.account().catch((e: unknown) => e);

    expect(login).toBeInstanceOf(UnauthorizedError);
    expect((login as Error).message).toBe('Email or password is incorrect.');
    expect(boot).toBeInstanceOf(UnauthorizedError);
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('keeps a rejected reading’s reason and the Retry-After of a throttled sign-in', async () => {
    const rejected = new ApiClient({
      fetchImpl: mockFetch(() => jsonResponse({ reason: 'duplicate', detail: 'reading at 10:00 already ingested' }, 422)),
    });
    const err = await rejected.addReading({ timestamp: '2026-10-06T10:00:00Z', glucose: 6.2, unit: 'mmol/L' }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).detail).toEqual({ reason: 'duplicate', detail: 'reading at 10:00 already ingested' });

    const throttled = new ApiClient({
      fetchImpl: mockFetch(() => jsonResponse({ detail: 'Too many failed attempts. Try again in 15 min.' }, 429, { 'Retry-After': '840' })),
    });
    const t = await throttled.signIn('a@b.co', 'x').catch((e: unknown) => e);
    expect((t as ApiError).status).toBe(429);
    expect((t as ApiError).retryAfter).toBe(840);
    expect((t as Error).message).toBe('Too many failed attempts. Try again in 15 min.');
  });

  it('turns a validation error list into readable text', async () => {
    const api = new ApiClient({
      fetchImpl: mockFetch(() =>
        jsonResponse({ detail: [{ loc: ['body', 'email'], msg: 'Value error, Enter a valid email address.', type: 'value_error' }] }, 422),
      ),
    });
    const err = await api.signUp('nope', 'long enough password').catch((e: unknown) => e);
    expect((err as Error).message).toBe('Enter a valid email address.');
  });

  it('maps 404 to NotFoundError without ending the session', async () => {
    const onUnauthorized = vi.fn();
    const fetchImpl = mockFetch(() => jsonResponse({ detail: "No forecast yet for '1001'" }, 404));
    const api = new ApiClient({ fetchImpl, onUnauthorized });

    const err = await api.forecast('1001').catch((e: unknown) => e);

    expect(err).toBeInstanceOf(NotFoundError);
    expect((err as Error).message).toContain('No forecast yet');
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('wraps connection failures in NetworkError', async () => {
    const fetchImpl = vi.fn<typeof fetch>(() => Promise.reject(new TypeError('Failed to fetch')));
    const api = new ApiClient({ fetchImpl });

    const err = await api.health().catch((e: unknown) => e);

    expect(err).toBeInstanceOf(NetworkError);
    expect((err as Error).message).toBe('Failed to fetch');
  });

  it('downloads the personal export with its file name', async () => {
    const fetchImpl = mockFetch(
      () =>
        new Response('timestamp,glucose_mg_dl,flag\n', {
          headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename="glucorag-readings-20261006.csv"' },
        }),
    );
    const api = new ApiClient({ fetchImpl });

    const { blob, filename } = await api.exportReadings();

    expect(filename).toBe('glucorag-readings-20261006.csv');
    expect(blob.size).toBe('timestamp,glucose_mg_dl,flag\n'.length);
    expect(new Headers(fetchImpl.mock.calls[0]![1]?.headers).get('Accept')).toBe('text/csv');
  });

  it('reads accuracy and the public downloads list from their endpoints', async () => {
    const fetchImpl = mockFetch(() => jsonResponse({ phone_apk: null, watch_apk: null, releases_url: 'https://example.org/releases' }));
    const api = new ApiClient({ fetchImpl });

    await api.myAccuracy();
    await api.modelAccuracy();
    const downloads = await api.downloads();

    expect(fetchImpl.mock.calls.map(([url]) => url)).toEqual(['/me/accuracy', '/model/accuracy', '/downloads']);
    expect(downloads.releases_url).toBe('https://example.org/releases');
  });
});
