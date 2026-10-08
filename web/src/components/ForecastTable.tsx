import { ArrowDown, ArrowUp } from 'lucide-react';
import type { Prediction, Unit } from '../api/types';
import { chanceLabel, crossingMatrix, quantileIndex, sortForecast } from '../lib/forecast';
import { fmtQuantile } from '../lib/format';
import { MINUTE, formatTime } from '../lib/time';
import { formatGlucose } from '../lib/units';

interface Props {
  prediction: Prediction;
  hypoQuantile: number;
  hyperQuantile: number;
  /** Thresholds, mg/dL. */
  hypo: number;
  hyper: number;
  unit?: Unit;
  /** Staff read hypo/hyper; people read low/high. */
  audience?: 'staff' | 'person';
}

const MARK = { size: 12, strokeWidth: 2, 'aria-hidden': true } as const;

/** Every forecast quantile at every horizon; cells across a threshold are marked. People read chances, not quantile names. */
export function ForecastTable({ prediction, hypoQuantile, hyperQuantile, hypo, hyper, unit = 'mg/dL', audience = 'staff' }: Props) {
  const f = sortForecast(prediction);
  const marks = crossingMatrix(f, hypo, hyper);
  const hypoCol = quantileIndex(f.quantiles, hypoQuantile);
  const hyperCol = quantileIndex(f.quantiles, hyperQuantile);
  const person = audience === 'person';
  const [lowWord, highWord] = person ? ['low', 'high'] : ['hypo', 'hyper'];
  const g = (v: number | undefined) => (v === undefined || Number.isNaN(v) ? '—' : formatGlucose(v, unit));
  return (
    <div className="table-wrap">
      <table className="table table-num">
        <caption>
          Forecast from {formatTime(f.t0)}, {unit}. Cells at or below {formatGlucose(hypo, unit)} are marked{' '}
          <span className="cell-hypo">
            <ArrowDown {...MARK} /> low
          </span>
          , at or above {formatGlucose(hyper, unit)}{' '}
          <span className="cell-hyper">
            <ArrowUp {...MARK} /> high
          </span>
          .{' '}
          {person
            ? `Each column is a level with that chance of your glucose ending up below or above it. Low alerts watch the “${chanceLabel(hypoQuantile)}” column, high alerts the “${chanceLabel(hyperQuantile)}” column.`
            : `Alerts read ${fmtQuantile(hypoQuantile)} for hypo and ${fmtQuantile(hyperQuantile)} for hyper.`}
        </caption>
        <thead>
          <tr>
            <th scope="col">{person ? 'Time ahead' : 'Horizon'}</th>
            {f.quantiles.map((q, i) => (
              <th key={q} scope="col" className={i === hypoCol || i === hyperCol ? 'col-alert' : undefined}>
                {person ? chanceLabel(q) : fmtQuantile(q)}
                {i === hypoCol ? <span className="col-note">{lowWord} alert</span> : null}
                {i === hyperCol ? <span className="col-note">{highWord} alert</span> : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {f.horizons.map((h, hi) => (
            <tr key={h}>
              <th scope="row">
                {h} min <span className="muted">{formatTime(f.t0 + h * MINUTE)}</span>
              </th>
              {f.quantiles.map((q, qi) => {
                const mark = marks[hi]?.[qi] ?? null;
                return (
                  <td key={q} className={mark ? `cell-${mark}` : undefined}>
                    {mark === 'hypo' ? <ArrowDown {...MARK} /> : mark === 'hyper' ? <ArrowUp {...MARK} /> : null}
                    {g(f.values[hi]?.[qi])}
                    {mark ? (
                      <span className="visually-hidden">
                        {mark === 'hypo' ? `, at or below the ${lowWord} threshold` : `, at or above the ${highWord} threshold`}
                      </span>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
