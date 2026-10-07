import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { SESSION_ENDED } from '../api/errors';
import type { Account } from '../api/types';

const MODEL = { version: 'v1', interval_min: 15, lookback_min: 120, horizon_min: 60, data_gap_min: 60, hypo_mg_dl: 70, hyper_mg_dl: 180 };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

/** A fetch stub answering by path; unknown paths fail the test loudly. */
function serve(routes: Record<string, () => Response>) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const path = String(input).split('?')[0]!;
    const route = routes[path];
    if (!route) throw new Error(`unexpected request ${path}`);
    return route();
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function start(path: string) {
  window.history.pushState({}, '', `/ui${path}`);
  render(<App />);
}

const person = (has_profile: boolean): Account => ({ email: 'pat@example.com', role: 'person', unit: 'mmol/L', has_profile });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('session and routing', () => {
  it('shows Welcome when signed out, without a session-ended message', async () => {
    const fetchMock = serve({ '/auth/me': () => json({ detail: 'Not signed in' }, 401) });
    start('/');
    expect(await screen.findByRole('heading', { name: 'Where will your glucose be in an hour?' })).toBeTruthy();
    expect(screen.queryByText(SESSION_ENDED)).toBeNull();
    expect(window.location.pathname).toBe('/ui/welcome');
    const [, init] = fetchMock.mock.calls[0]!;
    expect(init?.credentials).toBe('same-origin');
    expect(new Headers(init?.headers).get('X-API-Key')).toBeNull();
  });

  it('sends a person without a profile to set-up', async () => {
    serve({ '/auth/me': () => json(person(false)) });
    start('/history');
    expect(await screen.findByRole('heading', { name: 'About you' })).toBeTruthy();
    expect(window.location.pathname).toBe('/ui/setup');
  });

  it('returns to sign-in with a message when a later request gets a 401', async () => {
    serve({
      '/auth/me': () => json(person(true)),
      '/me': () => json({ email: 'pat@example.com', role: 'person', unit: 'mmol/L', profile: null, readings: { count: 10, first: null, last: null }, model: MODEL }),
      '/me/status': () => json({ detail: 'Session expired' }, 401),
      '/me/history': () => json({ detail: 'Session expired' }, 401),
      '/me/alerts': () => json({ detail: 'Session expired' }, 401),
    });
    start('/');
    expect(await screen.findByText(SESSION_ENDED)).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeTruthy();
    expect(window.location.pathname).toBe('/ui/signin');
  });

  it('moves a clinician from / to the ward', async () => {
    serve({
      '/auth/me': () => json({ email: 'doc@example.com', role: 'clinician', unit: 'mg/dL', has_profile: false }),
      '/cohort/risk': () => json({ as_of: '2026-10-06T12:00:00', patients: [] }),
      '/stats': () => json({ clock: 'wall' }),
    });
    start('/');
    expect(await screen.findByRole('heading', { name: 'Ward' })).toBeTruthy();
    expect(window.location.pathname).toBe('/ui/ward');
    expect(screen.getByText('Clinical')).toBeTruthy();
  });

  it('shows a person the 403 page on a staff route, with a way back', async () => {
    const fetchMock = serve({ '/auth/me': () => json(person(true)) });
    start('/ward');
    expect(await screen.findByRole('heading', { name: 'This page is for clinical staff' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Go to Today' }).getAttribute('href')).toMatch(/^\/ui\/?$/);
    // No staff endpoint is called for a person.
    await waitFor(() => expect(fetchMock.mock.calls.map(([u]) => String(u))).not.toContain('/cohort/risk'));
  });
});
