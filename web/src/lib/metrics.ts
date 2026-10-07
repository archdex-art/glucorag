import { asNumber, isRecord } from './format';

export interface MeanStd {
  mean: number;
  std: number | null;
}

/** `{mean, std}` or a bare number. */
export function asMeanStd(v: unknown): MeanStd | null {
  const n = asNumber(v);
  if (n !== null) return { mean: n, std: null };
  if (isRecord(v)) {
    const mean = asNumber(v.mean);
    if (mean !== null) return { mean, std: asNumber(v.std) };
  }
  return null;
}

/** horizon → metric → mean±std, e.g. `summary` in meta.json `metrics.test`. */
export type HorizonMetrics = { horizon: string; metrics: Record<string, MeanStd> }[];

export function asHorizonMetrics(v: unknown): HorizonMetrics | null {
  if (!isRecord(v)) return null;
  const rows: HorizonMetrics = [];
  for (const [horizon, metrics] of Object.entries(v)) {
    if (!isRecord(metrics)) return null;
    const parsed: Record<string, MeanStd> = {};
    for (const [name, value] of Object.entries(metrics)) {
      const ms = asMeanStd(value);
      if (!ms) return null;
      parsed[name] = ms;
    }
    if (!Object.keys(parsed).length) return null;
    rows.push({ horizon, metrics: parsed });
  }
  return rows.length ? rows.sort((a, b) => Number(a.horizon) - Number(b.horizon)) : null;
}

export function metricNames(rows: HorizonMetrics): string[] {
  const names: string[] = [];
  for (const r of rows) for (const k of Object.keys(r.metrics)) if (!names.includes(k)) names.push(k);
  return names;
}

export function fmtMeanStd(m: MeanStd | undefined, digits = 2): string {
  if (!m) return '—';
  return m.std === null ? m.mean.toFixed(digits) : `${m.mean.toFixed(digits)} ± ${m.std.toFixed(digits)}`;
}
