import type { Unit } from '../api/types';
import type { TimeInRanges as Tir } from '../lib/tir';
import { TIR_ORDER } from '../lib/tir';
import { ZONE_RANGE } from '../lib/units';
import { ZONES } from '../lib/zones';
import { TimeInRanges } from './TimeInRanges';

/** The AGP time-in-ranges bar in the reader's unit, with the consensus targets as caption. */
export function RangesSummary({ tir, unit, windowLabel }: { tir: Tir; unit: Unit; windowLabel: string }) {
  const low = tir.pct.very_low + tir.pct.low;
  return (
    <TimeInRanges
      title={`Time in ranges, ${windowLabel}`}
      segments={TIR_ORDER.map((z) => ({
        zone: z,
        label: ZONES.find((x) => x.key === z)?.label ?? z,
        range: ZONE_RANGE[unit][z],
        pct: tir.pct[z],
      }))}
      caption={
        <>
          Targets: over 70% in range, under 4% low. {windowLabel.charAt(0).toUpperCase() + windowLabel.slice(1)}:{' '}
          {tir.pct.target}% in range, {low}% low, from {tir.count.toLocaleString('en-US')} readings. Ranges in {unit}.
        </>
      }
    />
  );
}
