import type { ReactNode } from 'react';

/** Term/value pairs in a two-column definition list. */
export function Facts({ items, label }: { items: [string, ReactNode][]; label?: string }) {
  return (
    <dl className="facts" aria-label={label}>
      {items.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd className="num">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
