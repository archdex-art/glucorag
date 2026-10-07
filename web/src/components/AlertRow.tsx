import { ChevronDown } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router-dom';
import type { AlertType, StoredAlert } from '../api/types';
import { ALERT_LABEL, alertSentence } from '../lib/alerts';
import { formatApiTime, formatTime, formatWhen, tryParseApiTime, type WallTime } from '../lib/time';
import { PriorityChip } from './PriorityChip';
import { AlertTypeIcon } from './StatusIcon';
import { ICON } from './icon';

interface Props {
  alert: StoredAlert;
  /** Link to the patient (off on the patient's own page). */
  showPatient: boolean;
  /**
   * Service "today": times on that day show without a date. Omit when rows are already grouped
   * under their day, so only the time shows.
   */
  today?: WallTime | null;
}

/** The secondary line: where the alert came from. */
function alertMeta(a: StoredAlert): string | null {
  if (a.type === 'data_gap') {
    const last = typeof a.details.last_reading === 'string' ? a.details.last_reading : null;
    return last ? `Last reading ${formatApiTime(last)}.` : null;
  }
  if (!a.t0) return null;
  return `Forecast made at ${formatApiTime(a.t0)}${a.model_version ? ` by model ${a.model_version}` : ''}.`;
}

/** One alert: time, patient, type, what it says and its priority; forecast details on expand. */
export function AlertRow({ alert: a, showPatient, today }: Props) {
  const [open, setOpen] = useState(false);
  const metaId = useId();
  const raised = tryParseApiTime(a.t_raised);
  const label = ALERT_LABEL[a.type as AlertType] ?? a.type;
  const meta = alertMeta(a);

  return (
    <li className={`alert-row${showPatient ? '' : ' alert-row-compact'}`}>
      <time className="alert-time num" dateTime={a.t_raised}>
        {raised === null ? '—' : today === undefined ? formatTime(raised) : formatWhen(raised, today)}
      </time>
      {showPatient ? (
        <Link className="alert-patient num" to={`/patients/${encodeURIComponent(a.patient_id)}`}>
          <span className="visually-hidden">Patient </span>
          {a.patient_id}
        </Link>
      ) : null}
      <span className="alert-type">
        <AlertTypeIcon type={a.type} />
        {label}
      </span>
      <span className="alert-detail">{alertSentence(a)}</span>
      <span className="alert-priority">
        <PriorityChip severity={a.severity} risk={a.type} />
      </span>
      {meta ? (
        <>
          <button
            type="button"
            className="icon-button disclosure"
            aria-expanded={open}
            aria-controls={metaId}
            aria-label="Details"
            title={open ? 'Hide details' : 'Show details'}
            onClick={() => setOpen(!open)}
          >
            <ChevronDown {...ICON} />
          </button>
          <p id={metaId} className="alert-meta num" hidden={!open}>
            {meta}
          </p>
        </>
      ) : null}
    </li>
  );
}
