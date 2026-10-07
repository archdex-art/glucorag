import { describe, expect, it } from 'vitest';
import { formatCountdown, secondsLeft } from './pairing';

const NOW = Date.UTC(2026, 9, 8, 12, 0, 0);

describe('secondsLeft', () => {
  it('rounds part seconds up so the countdown reaches 0:00 only at expiry', () => {
    expect(secondsLeft('2026-10-08T12:10:00Z', NOW)).toBe(600);
    expect(secondsLeft('2026-10-08T12:00:00.200Z', NOW)).toBe(1);
  });

  it('reads offset times and the UTC form FastAPI sends', () => {
    expect(secondsLeft('2026-10-08T17:35:00+05:30', NOW)).toBe(300);
    expect(secondsLeft('2026-10-08T12:05:00.123456Z', NOW)).toBe(301);
  });

  it('is 0 once expired or unreadable', () => {
    expect(secondsLeft('2026-10-08T11:59:00Z', NOW)).toBe(0);
    expect(secondsLeft('not a time', NOW)).toBe(0);
  });
});

describe('formatCountdown', () => {
  it('shows minutes and zero-padded seconds', () => {
    expect(formatCountdown(600)).toBe('10:00');
    expect(formatCountdown(545)).toBe('9:05');
    expect(formatCountdown(59)).toBe('0:59');
    expect(formatCountdown(0)).toBe('0:00');
  });

  it('never goes negative', () => {
    expect(formatCountdown(-3)).toBe('0:00');
  });
});
