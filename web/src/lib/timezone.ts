/** The browser's IANA time zone, used to read import files whose times carry no offset. */

export const FALLBACK_TIME_ZONE = 'UTC';

/**
 * The resolved IANA zone, or UTC when the browser reports none (some locked-down browsers) or
 * something that is not a zone name. `resolve` is injectable for tests.
 */
export function detectTimeZone(
  resolve: () => string | undefined = () => Intl.DateTimeFormat().resolvedOptions().timeZone,
): string {
  try {
    const tz = resolve()?.trim();
    return tz && /^[A-Za-z_]+(?:\/[A-Za-z0-9_+-]+)*$/.test(tz) ? tz : FALLBACK_TIME_ZONE;
  } catch {
    return FALLBACK_TIME_ZONE;
  }
}

/** Every zone the browser knows, with `current` and UTC always present; empty when unsupported. */
export function timeZoneOptions(current: string): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  let zones: string[];
  try {
    zones = intl.supportedValuesOf?.('timeZone') ?? [];
  } catch {
    return [];
  }
  if (zones.length === 0) return [];
  return [...new Set([...zones, current, FALLBACK_TIME_ZONE])].sort();
}
