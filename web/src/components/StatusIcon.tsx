import {
  CircleCheck,
  CircleDashed,
  Hourglass,
  TrendingDown,
  TrendingUp,
  TriangleAlert,
  WifiOff,
  type LucideIcon,
} from 'lucide-react';
import type { AlertType, CohortStatus, RiskType } from '../api/types';
import { ICON } from './icon';

const STATUS_ICON: Record<CohortStatus, LucideIcon> = {
  at_risk: TriangleAlert,
  data_gap: WifiOff,
  warming_up: Hourglass,
  ok: CircleCheck,
  no_data: CircleDashed,
};

/** Decorative: the status is always spelled out next to it. */
export function StatusIcon({ status, risk }: { status: CohortStatus; risk?: RiskType | null }) {
  const Icon = STATUS_ICON[status];
  const tone = status === 'at_risk' ? `tone-${risk ?? 'hyper'}` : `status-${status}`;
  return <Icon {...ICON} className={`status-icon ${tone}`} />;
}

const ALERT_ICON: Record<AlertType, LucideIcon> = {
  hypo: TrendingDown,
  hyper: TrendingUp,
  data_gap: WifiOff,
};

const SHORT_LABEL: Record<AlertType, string> = { hypo: 'Hypo', hyper: 'Hyper', data_gap: 'Data gap' };

function isAlertType(t: string): t is AlertType {
  return t in ALERT_ICON;
}

/** Icon plus a short label for one active alert type. */
export function AlertTag({ type }: { type: string }) {
  if (!isAlertType(type)) return <span className="alert-tag">{type}</span>;
  const Icon = ALERT_ICON[type];
  return (
    <span className={`alert-tag tone-${type}`}>
      <Icon {...ICON} />
      {SHORT_LABEL[type]}
    </span>
  );
}

export function AlertTypeIcon({ type }: { type: string }) {
  const Icon = isAlertType(type) ? ALERT_ICON[type] : TriangleAlert;
  return <Icon {...ICON} className={`status-icon tone-${type}`} />;
}
