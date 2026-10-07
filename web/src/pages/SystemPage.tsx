import type { ReactNode } from 'react';
import { useHealth, useStats } from '../api/hooks';
import type { ServiceStats } from '../api/types';
import { Facts } from '../components/Facts';
import { PageHeader } from '../components/PageHeader';
import { ErrorState, Skeleton } from '../components/States';
import { useRefresh } from '../components/refresh';
import { fmtInt, fmtNumber, fmtQuantile, humanize } from '../lib/format';
import { formatApiTime, formatDuration } from '../lib/time';

const ms = (v: number | null) => (v === null ? '—' : `${fmtNumber(v, 1)} ms`);

function counts(data: Record<string, number>, empty: string): [string, ReactNode][] {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return entries.length ? entries.map(([k, v]) => [k ? humanize(k) : 'Unlabelled', fmtInt(v)]) : [[empty, '0']];
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="facts-group" aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function Groups({ s, health }: { s: ServiceStats; health: ReactNode }) {
  const t = s.thresholds;
  return (
    <div className="facts-grid">
      <Group title="Service">
        <Facts
          items={[
            ['Health', health],
            ['Model', s.model_version],
            ['Uptime', formatDuration(s.uptime_s)],
            ['Started', formatApiTime(s.started_at)],
            ['Clock', s.clock === 'data' ? 'Replay data (times are dataset times)' : 'Live (wall clock)'],
            // The data clock reads datetime.min until the first reading arrives.
            ['Service time', s.as_of.startsWith('0001-') ? 'No reading received yet' : formatApiTime(s.as_of)],
          ]}
        />
      </Group>
      <Group title="Throughput">
        <Facts items={Object.entries(s.counters).map(([k, v]) => [humanize(k), fmtInt(v)])} />
      </Group>
      <Group title="Latency">
        <Facts
          items={[
            ['Median (p50)', ms(s.latency.p50_ms)],
            ['p95', ms(s.latency.p95_ms)],
            ['Slowest', ms(s.latency.max_ms)],
            ['Mean cycle', ms(s.latency.cycle_mean_ms)],
            ['Cycles sampled', fmtInt(s.latency.samples)],
          ]}
        />
      </Group>
      <Group title="Alerts by type">
        <Facts items={counts(s.alerts_by_type, 'No alerts')} />
      </Group>
      <Group title="Data gaps by source">
        <Facts items={counts(s.data_gaps_by_source, 'No data gaps')} />
      </Group>
      <Group title="Rejected readings">
        <Facts items={counts(s.rejected_by_reason, 'None rejected')} />
      </Group>
      <Group title="Storage">
        <Facts items={Object.entries(s.storage).map(([k, v]) => [humanize(k), fmtInt(v)])} />
      </Group>
      <Group title="Thresholds">
        <Facts
          items={[
            ['Hypo alert', `${fmtQuantile(t.hypo_quantile)} at or below ${t.hypo_mg_dl} mg/dL`],
            ['Hyper alert', `${fmtQuantile(t.hyper_quantile)} at or above ${t.hyper_mg_dl} mg/dL`],
            ['Not reporting after', `${t.data_gap_min} min without a reading`],
          ]}
        />
      </Group>
    </div>
  );
}

export function SystemPage() {
  const { paused } = useRefresh();
  const stats = useStats(paused);
  const health = useHealth(paused);
  const healthText = health.isError ? (
    <span className="zt-low">Not responding</span>
  ) : health.data ? (
    <span className="zt-target">{health.data.status === 'ok' ? 'Healthy' : humanize(health.data.status)}</span>
  ) : (
    'Checking'
  );

  return (
    <>
      <PageHeader title="System" refresh={{ updatedAt: stats.dataUpdatedAt }} />
      <div className="sheet sheet-pad">
        {stats.isPending ? <Skeleton label="Loading service statistics" rows={6} /> : null}
        {stats.isError ? (
          <ErrorState error={stats.error} title="Service statistics could not be loaded." onRetry={() => void stats.refetch()} />
        ) : null}
        {stats.data ? <Groups s={stats.data} health={healthText} /> : null}
      </div>
    </>
  );
}
