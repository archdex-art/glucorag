/** Names of the forecast chart's three ribbons, outer to inner, plus the median line. */
export interface RibbonNames {
  outer: string;
  mid: string;
  inner: string;
  median: string;
}

/** Staff read the quantile levels. */
export const QUANTILE_RIBBONS: RibbonNames = {
  outer: 'q0.02–q0.98',
  mid: 'q0.10–q0.90',
  inner: 'q0.25–q0.75',
  median: 'Median forecast',
};

/** People read how many outcomes in 100 each band holds. */
export const PERSON_RIBBONS: RibbonNames = {
  outer: '96 in 100',
  mid: '80 in 100',
  inner: '50 in 100',
  median: 'Middle of the forecast',
};
