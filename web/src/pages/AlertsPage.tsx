import { Download } from 'lucide-react';
import { useId, useMemo, useState } from 'react';
import { useAlerts, useCohort } from '../api/hooks';
import type { AlertQuery, AlertType, StoredAlert } from '../api/types';
import { useApi } from '../auth/context';
import { AlertRow } from '../components/AlertRow';
import { PageHeader } from '../components/PageHeader';
import { Empty, ErrorState, Skeleton } from '../components/States';
import { ICON } from '../components/icon';
import { useRefresh } from '../components/refresh';
import { sortAlertsNewestFirst } from '../lib/alerts';
import { saveBlob } from '../lib/download';
import { PRIORITY_LABEL, SEVERITY_OF, type Priority } from '../lib/priority';
import { formatDay, tryParseApiTime } from '../lib/time';

const LIMIT = 500;

/** Consecutive alerts (newest first) grouped under their day. */
function groupByDay(alerts: StoredAlert[]): { day: string; alerts: StoredAlert[] }[] {
  const groups: { day: string; alerts: StoredAlert[] }[] = [];
  for (const a of alerts) {
    const t = tryParseApiTime(a.t_raised);
    const day = t === null ? 'Unknown date' : formatDay(t);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.alerts.push(a);
    else groups.push({ day, alerts: [a] });
  }
  return groups;
}

export function AlertsPage() {
  const api = useApi();
  const { paused } = useRefresh();
  const [type, setType] = useState<AlertType | ''>('');
  const [patient, setPatient] = useState('');
  const [priority, setPriority] = useState<Priority | ''>('');
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const ids = { type: useId(), patient: useId(), priority: useId() };

  const query = useMemo<AlertQuery>(
    () => ({ limit: LIMIT, ...(type ? { type } : {}), ...(patient ? { patient_id: patient } : {}) }),
    [type, patient],
  );
  const alerts = useAlerts(query, paused);
  const cohort = useCohort(paused);
  const patientIds = useMemo(
    () => (cohort.data?.patients.map((p) => p.patient_id) ?? []).sort((a, b) => a.localeCompare(b, 'en', { numeric: true })),
    [cohort.data],
  );

  const groups = useMemo(() => {
    const list = alerts.data ?? [];
    const filtered = priority ? list.filter((a) => a.severity === SEVERITY_OF[priority]) : list;
    return groupByDay(sortAlertsNewestFirst(filtered));
  }, [alerts.data, priority]);

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await api.exportBlob('alerts', 'csv', patient ? { patient_id: patient } : {});
      saveBlob(blob, `glucorag_alerts${patient ? `_${patient}` : ''}.csv`);
    } catch (err) {
      setExportError(err);
    } finally {
      setExporting(false);
    }
  }

  const filtered = type !== '' || patient !== '' || priority !== '';

  return (
    <>
      <PageHeader title="Alerts" refresh={{ updatedAt: alerts.dataUpdatedAt }} />
      <div className="sheet">
        <div className="toolbar">
          <form className="filters" aria-label="Alert filters" onSubmit={(e) => e.preventDefault()}>
            <div className="field">
              <label htmlFor={ids.type}>Type</label>
              <select id={ids.type} value={type} onChange={(e) => setType(e.target.value as AlertType | '')}>
                <option value="">All types</option>
                <option value="hyper">Hyper predicted</option>
                <option value="hypo">Hypo predicted</option>
                <option value="data_gap">Data gap</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor={ids.patient}>Patient</label>
              <select id={ids.patient} value={patient} onChange={(e) => setPatient(e.target.value)}>
                <option value="">All patients</option>
                {patientIds.map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor={ids.priority}>Priority</label>
              <select id={ids.priority} value={priority} onChange={(e) => setPriority(e.target.value as Priority | '')}>
                <option value="">All priorities</option>
                {(Object.keys(PRIORITY_LABEL) as Priority[]).map((p) => (
                  <option key={p} value={p}>
                    {PRIORITY_LABEL[p]}
                  </option>
                ))}
              </select>
            </div>
          </form>
          <div className="export">
            <button type="button" className="button" onClick={() => void exportCsv()} disabled={exporting} aria-describedby={`${ids.type}-export`}>
              <Download {...ICON} />
              {exporting ? 'Exporting' : 'Export CSV'}
            </button>
            <span id={`${ids.type}-export`} className="caption">
              Every alert type{patient ? ` for patient ${patient}` : ', all patients'}
            </span>
          </div>
        </div>
        {exportError ? (
          <div className="sheet-pad">
            <ErrorState error={exportError} title="The export failed." onRetry={() => void exportCsv()} />
          </div>
        ) : null}

        {alerts.isPending ? <Skeleton label="Loading alerts" variant="rows" rows={6} /> : null}
        {alerts.isError ? (
          <div className="sheet-pad">
            <ErrorState error={alerts.error} title="The alerts could not be loaded." onRetry={() => void alerts.refetch()} />
          </div>
        ) : null}
        {alerts.data && groups.length === 0 ? (
          <Empty>
            {filtered ? (
              <>
                <p>No alert matches these filters.</p>
                <button
                  type="button"
                  className="button"
                  onClick={() => {
                    setType('');
                    setPatient('');
                    setPriority('');
                  }}
                >
                  Clear filters
                </button>
              </>
            ) : (
              <p>No alerts yet. Alerts appear here when a forecast crosses 70 or 180 mg/dL or a sensor stops reporting.</p>
            )}
          </Empty>
        ) : null}
        {groups.map((g) => (
          <section key={g.day} className="day-group" aria-label={g.day}>
            <h2 className="num">{g.day}</h2>
            <ul className="alert-list">
              {g.alerts.map((a) => (
                <AlertRow key={a.id} alert={a} showPatient />
              ))}
            </ul>
          </section>
        ))}
        {alerts.data && alerts.data.length >= LIMIT ? (
          <p className="caption sheet-pad">Showing the {LIMIT} most recent alerts. Export the CSV for the full list.</p>
        ) : null}
      </div>
    </>
  );
}
