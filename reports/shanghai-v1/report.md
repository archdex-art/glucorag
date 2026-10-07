# Evaluation report: shanghai-v1

- Dataset: shanghai (15-min CGM), test split
- Test windows: 24151 from 112 patients (targets restricted to real CGM observations)
- Metrics computed per patient, reported as mean ± sample STD across patients; point forecast = 0.5 quantile for EPS-TFT variants.
- Data hash matches training artifact: True

## 30-minute prediction horizon

| Method | RMSE | MAE | MAPE (%) | gRMSE |
|---|---|---|---|---|
| EPS-TFT w/o covariate encoder | 11.99 ± 2.96 | 8.58 ± 2.26 | 6.68 ± 1.86 | 12.93 ± 3.68 |
| LSTM | 12.02 ± 2.82 | 8.74 ± 2.11 | 6.96 ± 2.10 | 13.01 ± 3.59 |
| EPS-TFT | 12.04 ± 3.02 | 8.71 ± 2.37 | 6.87 ± 2.30 | 13.07 ± 3.90 |
| EPS-TFT w/o LSTM decoder | 12.07 ± 3.42 | 8.73 ± 2.63 | 6.97 ± 2.90 | 13.09 ± 4.61 |
| N-HiTS | 12.29 ± 3.06 | 8.86 ± 2.29 | 6.98 ± 2.11 | 13.22 ± 3.72 |
| N-BEATS | 12.31 ± 3.17 | 8.81 ± 2.38 | 6.90 ± 2.11 | 13.29 ± 3.87 |
| SVR | 12.51 ± 3.41 | 8.97 ± 2.46 | 7.06 ± 2.31 | 13.58 ± 4.30 |
| XGBoost | 12.51 ± 3.15 | 9.08 ± 2.38 | 7.44 ± 3.76 | 13.69 ± 4.32 |
| LR | 12.63 ± 3.06 | 9.28 ± 2.25 | 7.42 ± 2.23 | 13.64 ± 3.76 |

## 60-minute prediction horizon

| Method | RMSE | MAE | MAPE (%) | gRMSE |
|---|---|---|---|---|
| EPS-TFT w/o LSTM decoder | 20.92 ± 6.31 | 15.03 ± 4.89 | 11.90 ± 5.26 | 23.24 ± 8.43 |
| EPS-TFT | 21.21 ± 6.01 | 15.31 ± 4.80 | 12.12 ± 5.06 | 23.83 ± 8.11 |
| EPS-TFT w/o covariate encoder | 21.42 ± 5.67 | 15.27 ± 4.21 | 11.82 ± 3.70 | 24.16 ± 7.68 |
| LSTM | 21.51 ± 5.21 | 15.60 ± 3.85 | 12.52 ± 4.57 | 24.15 ± 7.19 |
| SVR | 22.14 ± 6.30 | 15.76 ± 4.53 | 12.29 ± 4.39 | 25.10 ± 8.58 |
| XGBoost | 22.26 ± 6.02 | 16.25 ± 4.71 | 13.59 ± 8.92 | 25.30 ± 9.12 |
| N-HiTS | 22.32 ± 5.83 | 16.22 ± 4.22 | 12.82 ± 4.33 | 25.20 ± 7.91 |
| N-BEATS | 22.40 ± 5.83 | 16.40 ± 4.18 | 13.19 ± 5.05 | 25.39 ± 7.95 |
| LR | 22.93 ± 5.80 | 16.95 ± 4.16 | 13.73 ± 4.94 | 25.90 ± 7.86 |

## Comparison with the paper (Table II / Appendix A, RMSE mg/dL)

| Method | Horizon | Paper | This run |
|---|---|---|---|
| EPS-TFT | 30 min | 12.7 ± 3.8 | 12.04 ± 3.02 |
| EPS-TFT | 60 min | 21.7 ± 6.9 | 21.21 ± 6.01 |
| EPS-TFT w/o LSTM decoder | 60 min | 22.0 | 20.92 ± 6.31 |
| EPS-TFT w/o covariate encoder | 60 min | 22.4 | 21.42 ± 5.67 |

## RMSE by diabetes type

| Method | T1D 30 min | T1D 60 min | T2D 30 min | T2D 60 min |
|---|---|---|---|---|
| EPS-TFT | 14.30 ± 3.26 | 27.62 ± 7.65 | 11.76 ± 2.89 | 20.45 ± 5.34 |
| EPS-TFT w/o covariate encoder | 13.18 ± 3.65 | 25.08 ± 8.43 | 11.85 ± 2.86 | 20.98 ± 5.13 |
| EPS-TFT w/o LSTM decoder | 14.30 ± 5.45 | 26.24 ± 10.44 | 11.80 ± 3.03 | 20.28 ± 5.35 |
| LR | 13.25 ± 3.57 | 25.67 ± 8.36 | 12.56 ± 3.00 | 22.60 ± 5.38 |
| SVR | 14.37 ± 5.49 | 26.00 ± 10.08 | 12.29 ± 3.03 | 21.67 ± 5.59 |
| XGBoost | 13.99 ± 4.51 | 26.40 ± 9.37 | 12.34 ± 2.93 | 21.76 ± 5.34 |
| LSTM | 13.33 ± 3.59 | 25.25 ± 7.81 | 11.86 ± 2.69 | 21.06 ± 4.66 |
| N-BEATS | 13.43 ± 3.88 | 25.56 ± 8.40 | 12.18 ± 3.07 | 22.02 ± 5.38 |
| N-HiTS | 13.18 ± 3.58 | 25.15 ± 8.27 | 12.19 ± 3.00 | 21.99 ± 5.42 |

## Significance (paired per-patient RMSE)

Shapiro–Wilk on paired differences, then paired two-sided t-test of EPS-TFT vs the next-best method (Wilcoxon signed-rank shown for robustness).

| Horizon | Comparator | n | mean Δ RMSE | Shapiro p | normal | t | t-test p | Wilcoxon p | significant |
|---|---|---|---|---|---|---|---|---|---|
| 30 min | LSTM | 112 | +0.021 | 1.55e-08 | False | 0.169 | 0.866 | 0.236 | False |
| 60 min | LSTM | 112 | -0.296 | 7.7e-09 | False | -0.925 | 0.357 | 0.00921 | False |

## Explainability (EPS-TFT, test windows)

Encoder VSN importance:

| Variable | Mean selection weight |
|---|---|
| glucose | 0.875 |
| time_of_day | 0.125 |

Mean attention by position (minutes relative to forecast origin):

| -105 | -90 | -75 | -60 | -45 | -30 | -15 | 0 | 15 | 30 | 45 | 60 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.103 | 0.077 | 0.089 | 0.084 | 0.091 | 0.090 | 0.096 | 0.109 | 0.100 | 0.084 | 0.053 | 0.024 |

## Notes

- Baselines trained on the same 75501 train / 24196 val windows; LR/SVR/XGBoost are single-horizon (one model per horizon) on look-back glucose + sin/cos time of day; LSTM/N-BEATS/N-HiTS are multi-horizon, trained with MSE and early stopping on validation (patience 10).
- SVR is fit on a seeded uniform subsample of at most 10000 training windows (kernel SVR scales quadratically).
