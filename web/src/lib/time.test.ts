import { afterAll, describe, expect, it } from 'vitest';
import {
  HOUR,
  formatApiTime,
  formatDateTime,
  formatElapsed,
  formatTime,
  formatWhen,
  isZoned,
  parseApiTime,
  timeTicks,
  toApiTime,
} from './time';

const ORIGINAL_TZ = process.env.TZ;
afterAll(() => {
  process.env.TZ = ORIGINAL_TZ;
});

// Node re-reads TZ on assignment, so each zone below really changes the browser-local offset.
const ZONES = ['UTC', 'America/Los_Angeles', 'Asia/Kolkata', 'Pacific/Chatham', 'Europe/Berlin'];

describe('naive API datetimes', () => {
  it.each(ZONES)('display exactly as written whatever the browser zone (%s)', (zone) => {
    process.env.TZ = zone;
    expect(formatApiTime('2021-08-06T12:58:00')).toBe('6 Aug 2021, 12:58');
    expect(formatApiTime('2021-08-06T12:58:07.123456', true)).toBe('6 Aug 2021, 12:58:07');
    // A wall time that does not exist in Berlin/LA (spring-forward gap) must survive unchanged.
    expect(formatApiTime('2021-03-28T02:30:00')).toBe('28 Mar 2021, 02:30');
    expect(formatApiTime('2021-03-14T02:30:00')).toBe('14 Mar 2021, 02:30');
  });

  it('parses to the field-for-field UTC epoch and round-trips to query strings', () => {
    const t = parseApiTime('2020-11-14T20:10:00');
    expect(t).toBe(Date.UTC(2020, 10, 14, 20, 10, 0));
    expect(toApiTime(t)).toBe('2020-11-14T20:10:00');
    expect(toApiTime(t - 6 * HOUR)).toBe('2020-11-14T14:10:00');
    // Windows across midnight and month ends stay calendar-correct.
    expect(toApiTime(parseApiTime('2021-03-01T01:00:00') - 3 * HOUR)).toBe('2021-02-28T22:00:00');
  });

  it('accepts space separators and missing seconds; rejects garbage', () => {
    expect(parseApiTime('2021-08-06 12:58')).toBe(Date.UTC(2021, 7, 6, 12, 58));
    expect(() => parseApiTime('06/08/2021 12:58')).toThrow();
    expect(formatApiTime(null)).toBe('—');
    expect(formatApiTime('not a date')).toBe('—');
  });
});

describe('zoned API datetimes (audit times)', () => {
  it('converts the instant to browser-local wall time', () => {
    process.env.TZ = 'Asia/Kolkata'; // UTC+05:30, no DST
    expect(isZoned('2026-10-05T13:22:16.187356Z')).toBe(true);
    expect(isZoned('2026-10-05T13:22:16')).toBe(false);
    expect(formatApiTime('2026-10-05T13:22:16.187356Z', true)).toBe('5 Oct 2026, 18:52:16');
    expect(formatApiTime('2026-10-05T09:59:06.381293+00:00')).toBe('5 Oct 2026, 15:29');
    expect(formatApiTime('2026-10-05T09:59:06-04:00')).toBe('5 Oct 2026, 19:29');

    process.env.TZ = 'UTC';
    expect(formatApiTime('2026-10-05T13:22:16Z')).toBe('5 Oct 2026, 13:22');
  });

  it('orders naive and zoned values on one wall-clock axis', () => {
    process.env.TZ = 'UTC';
    expect(parseApiTime('2026-10-05T13:22:16Z')).toBe(parseApiTime('2026-10-05T13:22:16'));
    expect(formatDateTime(null)).toBe('—');
  });
});

describe('chart time ticks', () => {
  it('fall on whole wall-clock hours inside the window', () => {
    const end = parseApiTime('2022-01-27T12:33:00');
    const ticks = timeTicks(end - 7 * HOUR, end);
    expect(ticks.map((t) => formatTime(t))).toEqual([
      '06:00', '07:00', '08:00', '09:00', '10:00', '11:00', '12:00',
    ]);
  });

  it('widen the step for multi-day windows and stay within the limit', () => {
    const end = parseApiTime('2022-01-27T12:33:00');
    const ticks = timeTicks(end - 73 * HOUR, end);
    expect(ticks.length).toBeLessThanOrEqual(9);
    expect(ticks[1]! - ticks[0]!).toBe(12 * HOUR);
    expect(formatDateTime(ticks[0]!)).toBe('24 Jan 2022, 12:00');
    expect(timeTicks(end, end)).toEqual([]);
  });
});

describe('reading-form times', () => {
  it('shows only the time on the reference day, the full date otherwise', () => {
    const today = parseApiTime('2022-01-27T11:33:00');
    expect(formatWhen(parseApiTime('2022-01-27T00:00:00'), today)).toBe('00:00');
    expect(formatWhen(parseApiTime('2022-01-26T23:59:00'), today)).toBe('26 Jan 2022, 23:59');
    expect(formatWhen(parseApiTime('2022-01-27T09:05:07'), null)).toBe('27 Jan 2022, 09:05');
    expect(formatWhen(null, today)).toBe('—');
  });

  it('formats elapsed minutes as minutes, hours and minutes, then days', () => {
    expect(formatElapsed(4.4)).toBe('4 min');
    expect(formatElapsed(59.6)).toBe('1 h');
    expect(formatElapsed(130)).toBe('2 h 10 min');
    expect(formatElapsed(47 * 60 + 59)).toBe('47 h 59 min');
    expect(formatElapsed(49 * 24 * 60 + 300)).toBe('49 days');
    expect(formatElapsed(null)).toBe('—');
  });
});
