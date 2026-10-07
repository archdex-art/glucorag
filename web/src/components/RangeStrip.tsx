import type { CSSProperties } from 'react';
import { envelope, type Band } from '../lib/envelope';
import { ZONES, ZONE_LABEL, logPosition, zoneOf } from '../lib/zones';

interface Props {
  /** Latest reading, mg/dL. */
  current?: number | null;
  /** Next-hour forecast band; absent when there is no fresh forecast. */
  band?: Band | null;
  size: 'row' | 'compact';
}

const GEOMETRY = {
  row: { h: 28, track: 12, base: 2, band: 10, tick: 20, dot: 4 },
  compact: { h: 20, track: 8, base: 2, band: 8, tick: 14, dot: 3.5 },
} as const;

/** Strip position of a value, as an SVG percentage. */
function x(v: number): string {
  return `${(logPosition(v) * 100).toFixed(3)}%`;
}

/** Strip width between two values, as an SVG percentage. */
function span(from: number, to: number): string {
  return `${((logPosition(to) - logPosition(from)) * 100).toFixed(3)}%`;
}

function describe(current: number | null, band: Band | null): string {
  const env = band ? envelope(band) : null;
  if (current === null && !env) return 'No readings.';
  const now =
    current !== null
      ? `${env ? 'Now' : 'Last value'} ${Math.round(current)} mg/dL, ${ZONE_LABEL[zoneOf(current)]}.`
      : '';
  if (!env) return `${now} No current forecast.`;
  const median = env.median60 !== null ? ` 60-minute median ${Math.round(env.median60)} mg/dL.` : '';
  return `${now} Next hour forecast band ${Math.round(env.low)} to ${Math.round(env.high)} mg/dL.${median}`.trim();
}

/** Log-scaled 40–400 mg/dL strip: zones, next-hour band, 60-min median and the current value. */
export function RangeStrip({ current = null, band = null, size }: Props) {
  const g = GEOMETRY[size];
  const env = band ? envelope(band) : null;
  const median = env?.median60 ?? null;
  const mid = g.h / 2;
  const trackY = mid - g.track / 2;
  // Moving geometry is set through CSS properties so that position changes transition.
  const style = (props: Record<string, string>) => props as CSSProperties;

  return (
    <svg
      className={`strip strip-${size}${env ? '' : ' strip-muted'}`}
      role="img"
      aria-label={describe(current, band)}
      width="100%"
      height={g.h}
    >
      {ZONES.map((z) => (
        <g key={z.key} className={`zone-${z.key}`}>
          <rect className="strip-tint" x={x(z.from)} y={trackY} width={span(z.from, z.to)} height={g.track} />
          <rect className="strip-base" x={x(z.from)} y={trackY + g.track - g.base} width={span(z.from, z.to)} height={g.base} />
        </g>
      ))}
      {ZONES.slice(1).map((z) => (
        <rect key={z.key} className="strip-gap" x={x(z.from)} y={trackY} width={1} height={g.track} transform="translate(-0.5 0)" />
      ))}
      {env ? (
        <rect
          className="strip-band strip-move"
          style={style({ x: x(env.low), width: span(env.low, env.high) })}
          y={mid - g.band / 2}
          height={g.band}
          rx={2}
        />
      ) : null}
      {current !== null && median !== null ? (
        <rect
          className="strip-ink strip-move"
          style={style({ x: x(Math.min(current, median)), width: span(Math.min(current, median), Math.max(current, median)) })}
          y={mid - 0.75}
          height={1.5}
        />
      ) : null}
      {median !== null ? (
        <rect
          className="strip-ink strip-move"
          style={style({ x: x(median) })}
          y={mid - g.tick / 2}
          width={2}
          height={g.tick}
          transform="translate(-1 0)"
        />
      ) : null}
      {current !== null ? (
        <circle
          className={`strip-move ${env ? 'strip-dot' : 'strip-dot-hollow'}`}
          style={style({ cx: x(current) })}
          cy={mid}
          r={env ? g.dot : g.dot - 0.75}
        />
      ) : null}
    </svg>
  );
}
