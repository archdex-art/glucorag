/**
 * API datetimes.
 *
 * Event times (readings, t0, t_raised, as_of) are *naive* ISO strings in the server's local
 * wall-clock (dataset time in replay mode). They must be shown exactly as written, whatever
 * the browser's time zone. Audit times (created_at, started_at) carry an offset/`Z`.
 *
 * Internally every datetime becomes a "wall time": milliseconds whose **UTC** fields equal the
 * wall-clock fields to display. Naive strings map field-for-field (no shift); aware strings are
 * converted to the browser's local wall-clock. All formatting uses `timeZone: 'UTC'`.
 */

export type WallTime = number;

const ISO_RE =
  /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?)?\s*(Z|[+-]\d{2}(?::?\d{2})?)?$/i;

export const MINUTE = 60_000;
export const HOUR = 60 * MINUTE;
export const DAY = 24 * HOUR;

/** True if the string carries an explicit UTC offset or `Z`. */
export function isZoned(value: string): boolean {
  const m = ISO_RE.exec(value.trim());
  return Boolean(m?.[8]);
}

function offsetMinutes(tz: string): number {
  if (tz.toUpperCase() === 'Z') return 0;
  const sign = tz.startsWith('-') ? -1 : 1;
  const digits = tz.slice(1).replace(':', '');
  const h = Number(digits.slice(0, 2));
  const m = digits.length > 2 ? Number(digits.slice(2, 4)) : 0;
  return sign * (h * 60 + m);
}

/** Parse an API datetime into a WallTime. Throws on malformed input. */
export function parseApiTime(value: string): WallTime {
  const m = ISO_RE.exec(value.trim());
  if (!m) throw new Error(`Invalid datetime: ${value}`);
  const [, y, mo, d, h = '0', mi = '0', s = '0', frac = '', tz] = m;
  const ms = Number((frac + '000').slice(0, 3));
  const fields = Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s), ms);
  if (!tz) return fields;
  const instant = fields - offsetMinutes(tz) * MINUTE;
  // Shift the absolute instant into the browser's local wall-clock.
  return instant - new Date(instant).getTimezoneOffset() * MINUTE;
}

export function tryParseApiTime(value: string | null | undefined): WallTime | null {
  if (!value) return null;
  try {
    return parseApiTime(value);
  } catch {
    return null;
  }
}

const pad = (n: number, width = 2) => String(n).padStart(width, '0');

/** Naive ISO string (`YYYY-MM-DDTHH:MM:SS`) for API query parameters. */
export function toApiTime(t: WallTime): string {
  const d = new Date(t);
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`
  );
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** `27 Jan 2022`. */
export function formatDay(t: WallTime): string {
  const d = new Date(t);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function formatTime(t: WallTime, seconds = false): string {
  const d = new Date(t);
  const base = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  return seconds ? `${base}:${pad(d.getUTCSeconds())}` : base;
}

/** `27 Jan 2022, 11:33` (seconds optional). */
export function formatDateTime(t: WallTime | null, seconds = false): string {
  if (t === null || Number.isNaN(t)) return '—';
  return `${formatDay(t)}, ${formatTime(t, seconds)}`;
}

export function sameDay(a: WallTime, b: WallTime): boolean {
  return Math.floor(a / DAY) === Math.floor(b / DAY);
}

/** Time only when `t` falls on the same day as `today`, else the full date and time. */
export function formatWhen(t: WallTime | null, today: WallTime | null, seconds = false): string {
  if (t === null || Number.isNaN(t)) return '—';
  return today !== null && sameDay(t, today) ? formatTime(t, seconds) : formatDateTime(t, seconds);
}

const TICK_STEPS = [15, 30, 60, 120, 180, 360, 720, 1440].map((m) => m * MINUTE);

/** Axis ticks on round wall-clock boundaries (e.g. whole hours), at most `maxTicks`. */
export function timeTicks(start: WallTime, end: WallTime, maxTicks = 9): WallTime[] {
  if (!(end > start)) return [];
  const step = TICK_STEPS.find((s) => (end - start) / s <= maxTicks) ?? 1440 * MINUTE * Math.ceil((end - start) / (maxTicks * 1440 * MINUTE));
  const ticks: WallTime[] = [];
  for (let t = Math.ceil(start / step) * step; t <= end; t += step) ticks.push(t);
  return ticks;
}

/** Short axis label: time, prefixed with the day when the span covers several days. */
export function formatAxisTime(t: WallTime, multiDay: boolean): string {
  const d = new Date(t);
  const hm = formatTime(t);
  return multiDay ? `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${hm}` : hm;
}

/** Format an API datetime string for display (naive → as written; zoned → browser local). */
export function formatApiTime(value: string | null | undefined, seconds = false): string {
  return formatDateTime(tryParseApiTime(value), seconds);
}

export function epochToWall(epochMs: number): WallTime {
  return epochMs - new Date(epochMs).getTimezoneOffset() * MINUTE;
}

/** Elapsed minutes in reading form: `45 min`, `2 h 10 min`, `49 days`. */
export function formatElapsed(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return '—';
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
  return `${Math.floor(h / 24)} days`;
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d} d ${h} h ${m} min`;
  if (h > 0) return `${h} h ${m} min`;
  if (m > 0) return `${m} min ${s % 60} s`;
  return `${s} s`;
}
