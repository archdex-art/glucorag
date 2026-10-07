import { describe, expect, it } from 'vitest';
import { FALLBACK_TIME_ZONE, detectTimeZone, timeZoneOptions } from './timezone';

describe('time-zone detection', () => {
  it('returns the browser zone', () => {
    expect(detectTimeZone(() => 'Europe/London')).toBe('Europe/London');
    expect(detectTimeZone(() => 'America/Argentina/Buenos_Aires')).toBe('America/Argentina/Buenos_Aires');
    expect(detectTimeZone(() => 'Etc/GMT+5')).toBe('Etc/GMT+5');
  });

  it('falls back to UTC when the browser has no answer or throws', () => {
    expect(FALLBACK_TIME_ZONE).toBe('UTC');
    expect(detectTimeZone(() => undefined)).toBe('UTC');
    expect(detectTimeZone(() => '')).toBe('UTC');
    expect(detectTimeZone(() => '   ')).toBe('UTC');
    expect(detectTimeZone(() => 'not a zone!')).toBe('UTC');
    expect(
      detectTimeZone(() => {
        throw new RangeError('no Intl');
      }),
    ).toBe('UTC');
  });

  it('uses the real Intl API by default', () => {
    expect(detectTimeZone()).toMatch(/^[A-Za-z_]+(\/[A-Za-z0-9_+-]+)*$/);
  });

  it('lists every zone with the detected one and UTC included, sorted and unique', () => {
    const zones = timeZoneOptions('Mars/Olympus_Mons');
    if (zones.length === 0) return; // Runtime without Intl.supportedValuesOf: the page falls back to a text field.
    expect(zones).toContain('Mars/Olympus_Mons');
    expect(zones).toContain('UTC');
    expect(new Set(zones).size).toBe(zones.length);
    expect([...zones].sort()).toEqual(zones);
  });
});
