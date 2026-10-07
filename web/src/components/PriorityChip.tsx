import { PRIORITY_LABEL, priorityOf } from '../lib/priority';

interface Props {
  severity: string | null | undefined;
  /** Which zone colour an Urgent chip takes; neutral when absent (e.g. a data gap). */
  risk?: string | null;
}

/** Urgent: filled in the risk's zone colour. Soon: outlined. Watch: plain text. */
export function PriorityChip({ severity, risk }: Props) {
  const p = priorityOf(severity);
  if (!p) return null;
  const tone = risk === 'hypo' || risk === 'hyper' ? risk : 'neutral';
  return <span className={`chip chip-${p} tone-${tone}`}>{PRIORITY_LABEL[p]}</span>;
}
