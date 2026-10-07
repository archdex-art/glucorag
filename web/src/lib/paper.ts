/**
 * Reference results for EPS-TFT on ShanghaiDM.
 *
 * Source: Zhu et al., IEEE Transactions on Biomedical Circuits and Systems 18(2), 2024,
 * DOI 10.1109/TBCAS.2023.3348844 (EPS-TFT). Test RMSE: Table II (mean ± SD across subjects,
 * mg/dL). Cross-individual validation: the paper's cross-validation RMSE.
 */

export const PAPER_DATASET = 'shanghai';
export const PAPER_SOURCE = 'Zhu et al. 2024';

export interface PaperValue {
  mean: number;
  std: number | null;
}

/** Test-set RMSE by horizon (minutes). */
export const PAPER_RMSE: Readonly<Record<30 | 60, PaperValue>> = {
  30: { mean: 12.7, std: 3.8 },
  60: { mean: 21.7, std: 6.9 },
};

/** Cross-individual cross-validation RMSE by horizon (minutes). */
export const PAPER_CV_RMSE: Readonly<Record<30 | 60, PaperValue>> = {
  30: { mean: 14.7, std: null },
  60: { mean: 23.5, std: null },
};
