import type { Device } from '../api/types';
import { HOUR, MINUTE, epochToWall, formatDateTime, formatDay, formatDayMonth, formatElapsed, formatTime, sameDay, tryParseApiTime } from './time';

function lastUsed(used: number, now: number): string {
  const minutes = Math.floor((now - used) / MINUTE);
  if (minutes < 1) return 'just now';
  if (now - used < HOUR || sameDay(used, now)) return `${formatElapsed(minutes)} ago`;
  if (new Date(used).getUTCFullYear() === new Date(now).getUTCFullYear()) return `${formatDayMonth(used)}, ${formatTime(used)}`;
  return formatDateTime(used);
}

/** `Connected 6 Oct 2026. Last used 4 min ago.`, in the browser's time zone; `now` is epoch ms. */
export function describeDevice(d: Device, now: number): string {
  const created = tryParseApiTime(d.created_at);
  const used = tryParseApiTime(d.last_used_at);
  const connected = created === null ? '' : `Connected ${formatDay(created)}. `;
  return `${connected}${used === null ? 'Not used yet.' : `Last used ${lastUsed(used, epochToWall(now))}.`}`;
}
