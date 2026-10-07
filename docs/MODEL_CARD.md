# Model card: `shanghai-v1` (EPS-TFT)

**Research use only.** Not a medical device. See `docs/RISK_REGISTER.md`.

## Overview
- **Architecture:** a Temporal Fusion Transformer, reimplemented following Zhu et al., *IEEE TBioCAS* 18(2), 2024 (DOI 10.1109/TBCAS.2023.3348844). Components:
  - variable selection networks and GRN/GLU gating;
  - a static covariate encoder;
  - an LSTM encoder and decoder;
  - interpretable multi-head attention with a causal mask;
  - an output head with 7 quantiles: 0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98.
- **Inputs:**
  - the last 120 min of CGM (8 steps at 15 min);
  - time of day for the past and the next 60 min;
  - static features: gender, age, BMI, diabetes type.
- **Output:** glucose in mg/dL at 15, 30, 45 and 60 min, for each quantile. Quantiles are sorted at serving time.
- **Training:**
  - Adam (lr 1e-3), quantile loss, batch 256, early stopping with patience 20.
  - Stopped at epoch 47 of a 200-epoch budget.
  - d_model 64, 4 heads, dropout 0.1, seed 0.
  - Hyperparameters were not tuned. `glucorag.train.tune` (Optuna HyperBand) is available but was not run for v1.
- **Artifact:** `models/shanghai-v1/` (`model.pt`, `meta.json`). `meta.json` records the normalizers, the static encoding, the data hash, the weights checksum and the evaluation results.

## Data
- **Dataset:** ShanghaiT1DM + ShanghaiT2DM (Zhao et al., *Sci. Data* 2023; figshare 10.6084/m9.figshare.20444397).
  - 112 patients (12 T1D, 100 T2D) and 125 recording segments.
  - Abbott FreeStyle Libre, 15-min sampling.
- **Preprocessing:**
  - readings are placed on a regular grid for each segment;
  - gaps of up to 60 min are filled by causal linear extrapolation; longer gaps are left missing and no windows are built across them;
  - values are clipped to 40–400 mg/dL;
  - glucose is z-normalized; time of day is scaled to [0, 1).
- **Split (per segment, chronological):** the last 20% is the test set, and the last 25% of the remainder is the validation set. Normalizers are fitted on the training split only.
- **Test scoring:** only windows whose targets are real readings (not imputed) are scored. That gives 24,151 test windows.

## Performance (test split; per-patient RMSE, mean ± STD across 112 patients)
| Model | RMSE 30 min | RMSE 60 min | Paper 30 / 60 min |
|---|---|---|---|
| EPS-TFT (v1) | 12.04 ± 3.02 | 21.21 ± 6.01 | 12.7 ± 3.8 / 21.7 ± 6.9 |
| LSTM (next best) | 12.02 ± 2.82 | 21.51 ± 5.21 | — |
| No covariate encoder | 11.99 ± 2.96 | 21.42 ± 5.67 | — / 22.4 |
| No LSTM decoder | 12.07 ± 3.42 | 20.92 ± 6.31 | — / 22.0 |

- The full tables are in `reports/shanghai-v1/report.md`. They add MAE, MAPE and gRMSE, six baselines, results by diabetes type, and explainability.
- **Cross-individual 5-fold CV (unseen patients):** RMSE 14.05 at 30 min and 26.09 at 60 min. The paper reports 14.7 / 23.5.
- **Significance:** EPS-TFT is not significantly better than LSTM. Paired t-test p = 0.87 at 30 min and p = 0.36 at 60 min, and the paired differences are not normal. The paper's p < 0.05 claim is **not reproduced**.
- **Ablations:** the paper's ordering is **not reproduced**; the differences are within noise.
- **T1D accuracy:** EPS-TFT is worse on T1D (60-min RMSE 27.6) than LSTM (25.3) or the model without the covariate encoder (25.1). The cohort is 89% T2D, which likely explains this.
- **Feature importance (encoder VSN):** glucose 0.875, time of day 0.125.

## In-silico decision support (paper Appendix B, hardware-free)
- **Setup:** simglucose 0.2.11, 10 virtual adults over 90 days. The 60-min median forecast suspends basal insulin when it is ≤ 70 mg/dL.
- **Time below 70 mg/dL:** 4.6% → 3.6%. The paper reports 5.3% → 1.9%.
- **Time in range:** 93.0% → 93.0%.
- **CVGA A+B:** 42.0% → 47.4%.
- **CVGA D+E:** 20.9% → 24.6%. The paper reports a 9-point improvement; here it gets worse.
- Details: `reports/sim/report.md`.

## Intended use and limits
- **Intended use:** research on population-level forecasting from Libre-like 15-min CGM, in cohorts similar to ShanghaiDM (adult Chinese, mostly T2D).
- **Out of scope:**
  - clinical decisions;
  - automated insulin delivery;
  - 5-min sensors (would need a separate 5-min model, e.g. trained on OhioT1DM under its DUA);
  - pediatric populations;
  - transfer across populations (the paper notes this limitation too).
- **Release status:** `python -m glucorag.release` blocks promotion of v1 on the `significance` gate. Accuracy, integrity, serving parity (0.0 mg/dL over 200 windows) and the in-silico gate pass. Promotion requires either a model that passes the significance gate or a documented waiver.
