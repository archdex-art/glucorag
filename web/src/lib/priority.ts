/**
 * Backend severity → the word clinicians read. "Low" is never shown for severity: it collides
 * with low glucose.
 */

export type Priority = 'urgent' | 'soon' | 'watch';

export const PRIORITY_LABEL: Record<Priority, string> = {
  urgent: 'Urgent',
  soon: 'Soon',
  watch: 'Watch',
};

const BY_SEVERITY: Record<string, Priority> = { high: 'urgent', medium: 'soon', low: 'watch' };

export function priorityOf(severity: string | null | undefined): Priority | null {
  return severity ? (BY_SEVERITY[severity] ?? null) : null;
}

/** Inverse for filters: the severity value a priority stands for. */
export const SEVERITY_OF: Record<Priority, string> = { urgent: 'high', soon: 'medium', watch: 'low' };
