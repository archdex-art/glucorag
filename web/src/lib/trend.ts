/** CGM trend arrows from the rate of change (FreeStyle Libre conventions, 15-min sensor). */

export type TrendKey = 'rising_quickly' | 'rising' | 'steady' | 'falling' | 'falling_quickly';

export const TREND_LABEL: Record<TrendKey, string> = {
  rising_quickly: 'rising quickly',
  rising: 'rising',
  steady: 'steady',
  falling: 'falling',
  falling_quickly: 'falling quickly',
};

/** Rate in mg/dL per minute. */
export function trendOf(rate: number): TrendKey {
  if (rate > 2) return 'rising_quickly';
  if (rate > 1) return 'rising';
  if (rate >= -1) return 'steady';
  if (rate >= -2) return 'falling';
  return 'falling_quickly';
}
