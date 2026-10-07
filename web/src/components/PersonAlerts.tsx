import type { StoredAlert, Unit } from '../api/types';
import { PERSON_ALERT_LABEL, personAlertSentence } from '../lib/alerts';
import { formatWhen, tryParseApiTime, type WallTime } from '../lib/time';
import { AlertTypeIcon } from './StatusIcon';

interface Props {
  alerts: readonly StoredAlert[];
  unit: Unit;
  /** Times on this day show without a date. */
  today: WallTime | null;
}

/** A person's alerts, newest first: time, what was predicted, and the sentence in their unit. */
export function PersonAlerts({ alerts, unit, today }: Props) {
  return (
    <ul className="alert-list person-alerts">
      {alerts.map((a) => {
        const raised = tryParseApiTime(a.t_raised);
        return (
          <li key={a.id} className="person-alert">
            <time className="alert-time num" dateTime={a.t_raised}>
              {formatWhen(raised, today)}
            </time>
            <span className="alert-type">
              <AlertTypeIcon type={a.type} />
              {PERSON_ALERT_LABEL[a.type] ?? a.type}
            </span>
            <span className="alert-detail">{personAlertSentence(a, unit)}</span>
          </li>
        );
      })}
    </ul>
  );
}
