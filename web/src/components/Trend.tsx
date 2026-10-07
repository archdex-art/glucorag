import { ArrowDown, ArrowDownRight, ArrowRight, ArrowUp, ArrowUpRight, type LucideIcon } from 'lucide-react';
import { TREND_LABEL, trendOf, type TrendKey } from '../lib/trend';
import { ICON } from './icon';

const TREND_ICON: Record<TrendKey, LucideIcon> = {
  rising_quickly: ArrowUp,
  rising: ArrowUpRight,
  steady: ArrowRight,
  falling: ArrowDownRight,
  falling_quickly: ArrowDown,
};

/** Trend arrow; the label is spoken, and shown when `showLabel` is set. */
export function TrendIcon({ rate, showLabel = false }: { rate: number | null; showLabel?: boolean }) {
  if (rate === null) return null;
  const key = trendOf(rate);
  const Icon = TREND_ICON[key];
  return (
    <span className="trend">
      <Icon {...ICON} />
      <span className={showLabel ? undefined : 'visually-hidden'}>{TREND_LABEL[key]}</span>
    </span>
  );
}
