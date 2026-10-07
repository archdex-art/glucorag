import type { ReactNode } from 'react';

export interface RangeSegment {
  /** Zone class suffix (very_low, low, target, high, very_high). */
  zone: string;
  label: string;
  range: string;
  /** Whole percent. */
  pct: number;
}

interface Props {
  segments: RangeSegment[];
  /** Accessible name of the bar, e.g. "Time in ranges, last 6 h". */
  title: string;
  caption?: ReactNode;
}

/** Labels narrower than this share sit in the legend list only. */
const MIN_LABEL_PCT = 3;

/** AGP stacked bar of time per range, low to high, with a legend that lists every share. */
export function TimeInRanges({ segments, title, caption }: Props) {
  const visible = segments.filter((s) => s.pct > 0);
  const spoken = segments.map((s) => `${s.label} ${s.pct}%`).join(', ');
  return (
    <figure className="tir">
      <div className="tir-bar" role="img" aria-label={`${title}: ${spoken}`}>
        {visible.map((s) => (
          <span key={s.zone} className={`tir-seg zone-${s.zone}`} style={{ flexGrow: s.pct }} />
        ))}
      </div>
      <div className="tir-labels num" aria-hidden="true">
        {visible.map((s) => (
          <span key={s.zone} style={{ flexGrow: s.pct }}>
            {s.pct >= MIN_LABEL_PCT ? `${s.pct}%` : ''}
          </span>
        ))}
      </div>
      <ul className="tir-legend">
        {segments.map((s) => (
          <li key={s.zone} className={`zone-${s.zone}`}>
            <span className="swatch swatch-fill" aria-hidden="true" />
            <span>
              {s.label} <span className="legend-range num">{s.range}</span>
            </span>
            <span className="num tir-pct">{s.pct}%</span>
          </li>
        ))}
      </ul>
      {caption ? <figcaption>{caption}</figcaption> : null}
    </figure>
  );
}
