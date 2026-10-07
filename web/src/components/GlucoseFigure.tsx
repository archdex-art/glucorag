import type { Unit } from '../api/types';
import type { ChartRow } from '../lib/forecast';
import { PERSON_RIBBONS } from '../lib/ribbons';
import { useMediaQuery } from '../lib/useMediaQuery';
import type { WallTime } from '../lib/time';
import { formatGlucose } from '../lib/units';
import { ForecastChart } from './ForecastChart';

interface Props {
  rows: ChartRow[];
  start: WallTime;
  end: WallTime;
  t0: WallTime | null;
  t0Label: string;
  hypo: number;
  hyper: number;
  unit: Unit;
  withFan: boolean;
  /** Spoken description of the chart. */
  summary: string;
  height?: { wide: number; narrow: number };
}

/** A person's glucose chart with its legend: readings, and the forecast fan when there is one. */
export function GlucoseFigure({ rows, start, end, t0, t0Label, hypo, hyper, unit, withFan, summary, height = { wide: 340, narrow: 260 } }: Props) {
  const narrow = useMediaQuery('(max-width: 599.98px)');
  return (
    <figure className="chart">
      <p className="visually-hidden">{summary}</p>
      <div className="chart-plot" aria-hidden="true">
        <ForecastChart
          rows={rows}
          start={start}
          end={end}
          t0={t0}
          t0Label={t0Label}
          low={hypo}
          high={hyper}
          height={narrow ? height.narrow : height.wide}
          maxTicks={narrow ? 4 : 7}
          unit={unit}
          ribbons={PERSON_RIBBONS}
        />
      </div>
      <figcaption className="chart-legend" aria-hidden="true">
        <span className="key key-reading">Readings</span>
        {withFan ? (
          <>
            <span className="key key-median">{PERSON_RIBBONS.median}</span>
            <span className="key ribbon-inner">Likely, {PERSON_RIBBONS.inner}</span>
            <span className="key ribbon-mid">{PERSON_RIBBONS.mid}</span>
            <span className="key ribbon-outer">{PERSON_RIBBONS.outer}</span>
          </>
        ) : null}
        <span className="key-note num">
          Lines at {formatGlucose(hypo, unit)} and {formatGlucose(hyper, unit)} {unit}; backgrounds show the glucose zones.
        </span>
      </figcaption>
    </figure>
  );
}
