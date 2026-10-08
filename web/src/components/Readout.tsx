import type { ReactNode } from 'react';
import type { ForecastBand, Unit } from '../api/types';
import { bandAt } from '../lib/envelope';
import { fmtQuantile } from '../lib/format';
import { formatGlucose, formatRateIn } from '../lib/units';
import { zoneOf } from '../lib/zones';
import { TrendIcon } from './Trend';

interface Props {
  current: number | null;
  /** mg/dL per minute. */
  trend: number | null;
  band: ForecastBand | null;
  /** The current value is old: show it, but not as "now". */
  stale: boolean;
  unit?: Unit;
  /** `row`: three columns (staff). `stack`: Now above the two forecast values (a person's Today). */
  layout?: 'row' | 'stack';
  /** Under the Now value, e.g. "4 min ago". */
  age?: ReactNode;
  /** Shown in the forecast cells when there is no band; default "No current forecast". */
  noForecast?: string;
  /** People read "range"; staff read the quantile names. */
  audience?: 'staff' | 'person';
}

/** `old` values are not current, so they take ink-2 instead of their zone colour. */
function Value({ v, unit, large, old }: { v: number | null; unit: Unit; large?: boolean; old?: boolean }) {
  if (v === null) return <span className="readout-value readout-none">—</span>;
  return (
    <>
      <span className={`readout-value num ${old ? 'readout-none' : `zt-${zoneOf(v)}`}${large ? ' readout-large' : ''}`}>
        {formatGlucose(v, unit)}
      </span>
      <span className="unit">{unit}</span>
    </>
  );
}

/** Now, in 30 min and in 60 min: value coloured by zone, with trend or forecast band. */
export function Readout({
  current,
  trend,
  band,
  stale,
  unit = 'mg/dL',
  layout = 'row',
  age,
  noForecast = 'No current forecast',
  audience = 'staff',
}: Props) {
  const horizons = [30, 60].map((h) => ({ h, point: band ? bandAt(band, h) : null }));
  const bandName = band ? `${fmtQuantile(band.low_quantile)}–${fmtQuantile(band.high_quantile)}` : null;
  const rate = trend !== null ? formatRateIn(trend, unit) : null;
  return (
    <div className={`readout-wrap readout-${layout}`}>
      <dl className="readout">
        <div className="readout-cell readout-now">
          <dt>{stale ? 'Last value' : 'Now'}</dt>
          <dd>
            <span className="readout-line">
              <Value v={current} unit={unit} large old={stale} />
            </span>
            {rate !== null && !stale ? (
              <span className="readout-sub">
                <TrendIcon rate={trend} showLabel />
                <span className="num">
                  {rate} {unit} per min
                </span>
              </span>
            ) : null}
            {age ? <span className="readout-sub readout-age num">{age}</span> : null}
          </dd>
        </div>
        {horizons.map(({ h, point }) => (
          <div key={h} className="readout-cell">
            <dt>In {h} min</dt>
            <dd>
              <span className="readout-line">
                <Value v={point?.median ?? null} unit={unit} />
              </span>
              <span className="readout-sub num">
                {point ? (
                  <>
                    <span className="visually-hidden">
                      {audience === 'person' ? 'Likely range: ' : `Band ${bandName}: `}
                    </span>
                    {formatGlucose(point.low, unit)}–{formatGlucose(point.high, unit)}
                  </>
                ) : (
                  noForecast
                )}
              </span>
            </dd>
          </div>
        ))}
      </dl>
      {bandName ? (
        <p className="caption">
          {audience === 'person'
            ? 'Values are the most likely level; the range under each is where you will probably be.'
            : `Values are the median forecast; ranges are the ${bandName} band the alerts use.`}
        </p>
      ) : null}
    </div>
  );
}
