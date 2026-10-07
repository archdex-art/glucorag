/**
 * Where the newest readings came from, remembered on this device so Today can say
 * "Last reading 4 min ago, from your import". The service does not record a reading's source,
 * so the hint holds only while no newer reading has arrived since this device added data.
 */

import { tryParseApiTime } from './time';

export type DataSource = 'import' | 'sample' | 'manual';

const KEY = 'glucorag.dataSource';

const PHRASE: Record<DataSource, string> = {
  import: 'from your import',
  sample: 'from the sample data',
  manual: 'entered by you',
};

interface Stored {
  email: string;
  source: DataSource;
  /** Latest reading time the source produced (ISO). */
  last: string;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function rememberSource(email: string, source: DataSource, last: string): void {
  try {
    storage()?.setItem(KEY, JSON.stringify({ email, source, last } satisfies Stored));
  } catch {
    // Storage full or blocked: the hint is optional.
  }
}

export function forgetSource(): void {
  try {
    storage()?.removeItem(KEY);
  } catch {
    // Nothing to forget.
  }
}

/** "from your import", or null when the hint is missing, for someone else, or outdated. */
export function sourcePhrase(email: string, lastReading: string | null): string | null {
  let stored: Partial<Stored> | null;
  try {
    stored = JSON.parse(storage()?.getItem(KEY) ?? 'null') as Partial<Stored> | null;
  } catch {
    return null;
  }
  if (!stored || stored.email !== email || !stored.source || !(stored.source in PHRASE)) return null;
  const mine = tryParseApiTime(stored.last);
  const latest = tryParseApiTime(lastReading);
  if (mine === null || latest === null || latest > mine) return null;
  return PHRASE[stored.source];
}
