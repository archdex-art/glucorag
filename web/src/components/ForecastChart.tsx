import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Unit } from '../api/types';
import type { ChartRow } from '../lib/forecast';
import { QUANTILE_RIBBONS, type RibbonNames } from '../lib/ribbons';
import { HOUR, formatAxisTime, formatDateTime, timeTicks, type WallTime } from '../lib/time';
import { formatGlucose, toMgDl, toUnit } from '../lib/units';
import { HIGH_MAX, LOW_BELOW, SCALE_MIN, TARGET_MAX, VERY_LOW_BELOW } from '../lib/zones';

interface Props {
  rows: ChartRow[];
  start: WallTime;
  end: WallTime;
  t0: WallTime | null;
  /** Label of the t0 rule: "Now" while the forecast is current. */
  t0Label: string;
  /** Target range edges drawn as rules (the service's hypo/hyper thresholds), mg/dL. */
  low: number;
  high: number;
  height: number;
  maxTicks: number;
  /** Display unit for the axis, rules and tooltip. Data stays in mg/dL. */
  unit?: Unit;
  ribbons?: RibbonNames;
}

interface TipProps {
  active?: boolean;
  label?: number | string;
  payload?: readonly { payload?: ChartRow }[];
  unit: Unit;
  ribbons: RibbonNames;
}

function ChartTooltip({ active, label, payload, unit, ribbons }: TipProps) {
  const row = payload?.[0]?.payload;
  if (!active || !row || typeof label !== 'number') return null;
  const g = (v: number) => formatGlucose(v, unit);
  const lines: [string, string][] = [];
  if (row.glucose != null) lines.push(['Reading', `${g(row.glucose)} ${unit}`]);
  if (row.median != null) lines.push([ribbons.median, `${g(row.median)} ${unit}`]);
  if (row.inner) lines.push([ribbons.inner, `${g(row.inner[0])}–${g(row.inner[1])}`]);
  if (row.mid) lines.push([ribbons.mid, `${g(row.mid[0])}–${g(row.mid[1])}`]);
  if (row.outer) lines.push([ribbons.outer, `${g(row.outer[0])}–${g(row.outer[1])}`]);
  if (!lines.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="num">{formatDateTime(label)}</p>
      <dl>
        {lines.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="num">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

const AXIS = { fill: 'var(--ink-2)', fontSize: 12 };

/**
 * Top of the value axis, mg/dL: at least 300 mg/dL (16.7 mmol/L), rounded up to a step that
 * reads as a round number in the display unit.
 */
function axisTop(maxMgDl: number, unit: Unit): number {
  if (unit === 'mmol/L') return toMgDl(Math.max(17, Math.ceil(toUnit(maxMgDl, unit) / 2) * 2 + 1), unit);
  return Math.max(300, Math.ceil(maxMgDl / 50) * 50);
}

export function ForecastChart({
  rows,
  start,
  end,
  t0,
  t0Label,
  low,
  high,
  height,
  maxTicks,
  unit = 'mg/dL',
  ribbons = QUANTILE_RIBBONS,
}: Props) {
  const multiDay = end - start > 24 * HOUR;
  const ticks = timeTicks(start, end, maxTicks);
  const values = rows.flatMap((r) => [r.glucose, r.outer?.[0], r.outer?.[1], r.median]);
  const finite = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const yMin = Math.min(SCALE_MIN, Math.floor(Math.min(...finite, SCALE_MIN) / 20) * 20);
  const yMax = axisTop(Math.max(...finite, 0), unit);
  const yTicks = [VERY_LOW_BELOW, LOW_BELOW, TARGET_MAX, HIGH_MAX, yMax].filter((v) => v > yMin);
  const zones: [string, number, number][] = [
    ['very-low', yMin, VERY_LOW_BELOW],
    ['low', VERY_LOW_BELOW, LOW_BELOW],
    ['target', LOW_BELOW, TARGET_MAX],
    ['high', TARGET_MAX, HIGH_MAX],
    ['very-high', HIGH_MAX, yMax],
  ];
  const rule = (value: number, tone: 'low' | 'high') => ({
    value: formatGlucose(value, unit),
    position: 'right' as const,
    fill: `var(--zone-${tone}-text)`,
    fontSize: 12,
    fontWeight: 600,
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 20, right: 40, bottom: 4, left: 0 }}>
        {zones.map(([z, y1, y2]) => (
          <ReferenceArea key={z} y1={y1} y2={y2} fill={`var(--zone-${z}-tint)`} fillOpacity={1} stroke="none" ifOverflow="hidden" />
        ))}
        <CartesianGrid vertical={false} stroke="var(--line)" />
        <XAxis
          dataKey="t"
          type="number"
          domain={[start, end]}
          allowDataOverflow
          tickFormatter={(t: number) => formatAxisTime(t, multiDay)}
          stroke="var(--line-strong)"
          tick={AXIS}
          tickLine={false}
          ticks={ticks}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[yMin, yMax]}
          ticks={yTicks}
          tickFormatter={(v: number) => formatGlucose(v, unit)}
          stroke="var(--line-strong)"
          tick={AXIS}
          tickLine={false}
          axisLine={false}
          width={44}
          allowDataOverflow
        />
        <ReferenceLine y={low} stroke="var(--zone-low-text)" strokeWidth={1.5} label={rule(low, 'low')} />
        <ReferenceLine y={high} stroke="var(--zone-high-text)" strokeWidth={1.5} label={rule(high, 'high')} />
        <Area dataKey="outer" name={ribbons.outer} stroke="none" fill="var(--p-outer)" fillOpacity={1} connectNulls isAnimationActive={false} activeDot={false} />
        <Area dataKey="mid" name={ribbons.mid} stroke="none" fill="var(--p-mid)" fillOpacity={1} connectNulls isAnimationActive={false} activeDot={false} />
        <Area dataKey="inner" name={ribbons.inner} stroke="none" fill="var(--p-inner)" fillOpacity={1} connectNulls isAnimationActive={false} activeDot={false} />
        <Line
          dataKey="median"
          name={ribbons.median}
          stroke="var(--p-median)"
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
          connectNulls
          isAnimationActive={false}
        />
        <Line
          dataKey="glucose"
          name="Readings"
          stroke="var(--ink)"
          strokeWidth={2}
          dot={false}
          connectNulls={false}
          isAnimationActive={false}
        />
        {t0 !== null ? (
          <ReferenceLine
            x={t0}
            stroke="var(--ink)"
            strokeDasharray="2 3"
            label={{ value: t0Label, position: 'insideTopRight', fill: 'var(--ink)', fontSize: 12, fontWeight: 600 }}
          />
        ) : null}
        <Tooltip
          content={<ChartTooltip unit={unit} ribbons={ribbons} />}
          wrapperStyle={{ outline: 'none' }}
          cursor={{ stroke: 'var(--ink-2)', strokeDasharray: '3 3' }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
