import { afterAll, beforeEach, describe, expect, it } from 'vitest';
import type { Device } from '../api/types';
import { describeDevice } from './devices';

const ORIGINAL_TZ = process.env.TZ;
beforeEach(() => {
  process.env.TZ = 'UTC';
});
afterAll(() => {
  process.env.TZ = ORIGINAL_TZ;
});

const NOW = Date.UTC(2026, 9, 6, 15, 0, 0);

function device(lastUsed: string | null, created = '2026-10-06T09:12:00+00:00'): Device {
  return { id: 1, device: 'Pixel 8', created_at: created, last_used_at: lastUsed };
}

describe('describeDevice', () => {
  it('says when a phone has not been used yet', () => {
    expect(describeDevice(device(null), NOW)).toBe('Connected 6 Oct 2026. Not used yet.');
  });

  it('says just now under a minute, including a clock slightly ahead', () => {
    expect(describeDevice(device('2026-10-06T14:59:30+00:00'), NOW)).toBe('Connected 6 Oct 2026. Last used just now.');
    expect(describeDevice(device('2026-10-06T15:00:20+00:00'), NOW)).toBe('Connected 6 Oct 2026. Last used just now.');
  });

  it('counts whole minutes ago', () => {
    expect(describeDevice(device('2026-10-06T14:56:00+00:00'), NOW)).toBe('Connected 6 Oct 2026. Last used 4 min ago.');
    expect(describeDevice(device('2026-10-06T14:55:10+00:00'), NOW)).toBe('Connected 6 Oct 2026. Last used 4 min ago.');
  });

  it('counts hours ago earlier the same day', () => {
    expect(describeDevice(device('2026-10-06T12:50:00+00:00'), NOW)).toBe('Connected 6 Oct 2026. Last used 2 h 10 min ago.');
  });

  it('gives the day and time on another day', () => {
    expect(describeDevice(device('2026-10-05T14:05:00+00:00', '2026-10-01T08:00:00+00:00'), NOW)).toBe(
      'Connected 1 Oct 2026. Last used 5 Oct, 14:05.',
    );
  });

  it('counts minutes across midnight rather than naming yesterday', () => {
    const justAfterMidnight = Date.UTC(2026, 9, 6, 0, 2, 0);
    expect(describeDevice(device('2026-10-05T23:59:00+00:00', '2026-10-01T08:00:00+00:00'), justAfterMidnight)).toBe(
      'Connected 1 Oct 2026. Last used 3 min ago.',
    );
  });

  it('adds the year when the last use was in another year', () => {
    expect(describeDevice(device('2025-10-05T14:05:00+00:00', '2025-09-01T08:00:00+00:00'), NOW)).toBe(
      'Connected 1 Sep 2025. Last used 5 Oct 2025, 14:05.',
    );
  });

  it('shows dates and times in the browser time zone', () => {
    process.env.TZ = 'Asia/Kolkata';
    // 20:00 UTC on 4 Oct is 01:30 on 5 Oct in India; 08:35 UTC on 5 Oct is 14:05 there.
    expect(describeDevice(device('2026-10-05T08:35:00+00:00', '2026-10-04T20:00:00+00:00'), NOW)).toBe(
      'Connected 5 Oct 2026. Last used 5 Oct, 14:05.',
    );
  });
});
