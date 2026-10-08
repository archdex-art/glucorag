# Zero-shot foundation-model benchmark: shanghai (shanghai-v1)

Research prototype; not a medical device. Nothing here is used by the app.

- Data: shanghai (15-min CGM), the test split of the evaluation report: 24151 windows from 112 patients, targets restricted to real CGM observations. Data hash matches the artifact: True.
- Every model forecasts from the same origin as EPS-TFT. Context = the prepared glucose series (mg/dL) ending at the origin: 120 min (EPS-TFT's look-back) and a longer context, cut at the most recent unimputed gap.
- Point forecast = 0.5 quantile for every probabilistic model. Metrics are computed per patient and reported as mean ± sample STD across patients (same code as the evaluation report).
- EPS-TFT re-run from the artifact on CPU; |RMSE − stored report| = 0.000 mg/dL at 30 min, 0.000 mg/dL at 60 min.
- Generated 2026-10-08T09:42:14.870188+00:00 on macOS-26.6.2-arm64-arm-64bit; packages: torch 2.14.1, chronos-forecasting 2.3.2, timesfm 3.0.2, transformers 5.19.0.

## Models and runtime

| Method | Weights (revision) | Params | Licence | Device | Load (s) | Inference (s) | ms / window |
|---|---|---|---|---|---|---|---|
| EPS-TFT | `models/shanghai-v1` | 286 k | this project | cpu | – | 0.7 | 0.03 |
| Persistence (last value) | – | – | n/a | cpu | 0.0 | 0.0 | 0.00 |
| Chronos-Bolt small, 120 min context | `amazon/chronos-bolt-small` @ `772f3d25d3` | 47.7 M | Apache-2.0 | cpu | 2.0 | 4.3 | 0.18 |
| Chronos-Bolt small, 24 h context | `amazon/chronos-bolt-small` @ `772f3d25d3` | 47.7 M | Apache-2.0 | cpu | 2.0 | 7.4 | 0.31 |
| Chronos-Bolt small, 128 h context | `amazon/chronos-bolt-small` @ `772f3d25d3` | 47.7 M | Apache-2.0 | cpu | 2.0 | 26.5 | 1.10 |
| Chronos-Bolt base, 120 min context | `amazon/chronos-bolt-base` @ `5d9f166d69` | 205.3 M | Apache-2.0 | cpu | 0.1 | 13.7 | 0.57 |
| Chronos-Bolt base, 24 h context | `amazon/chronos-bolt-base` @ `5d9f166d69` | 205.3 M | Apache-2.0 | cpu | 0.1 | 25.9 | 1.07 |
| Chronos-Bolt base, 128 h context | `amazon/chronos-bolt-base` @ `5d9f166d69` | 205.3 M | Apache-2.0 | cpu | 0.1 | 97.9 | 4.05 |
| Chronos-2, 120 min context | `amazon/chronos-2` @ `29ec3766d3` | 119.5 M | Apache-2.0 | cpu | 1.0 | 14.7 | 0.61 |
| Chronos-2, 24 h context | `amazon/chronos-2` @ `29ec3766d3` | 119.5 M | Apache-2.0 | cpu | 1.0 | 32.2 | 1.33 |
| Chronos-2, 128 h context | `amazon/chronos-2` @ `29ec3766d3` | 119.5 M | Apache-2.0 | cpu | 1.0 | 135.6 | 5.62 |
| TimesFM 2.5, 120 min context | `google/timesfm-2.5-200m-pytorch` @ `1d952420fb` | 231.3 M | Apache-2.0 | cpu | 1.3 | 20.1 | 0.83 |
| TimesFM 2.5, 24 h context | `google/timesfm-2.5-200m-pytorch` @ `1d952420fb` | 231.3 M | Apache-2.0 | cpu | 1.3 | 50.1 | 2.07 |
| TimesFM 2.5, 128 h context | `google/timesfm-2.5-200m-pytorch` @ `1d952420fb` | 231.3 M | Apache-2.0 | cpu | 1.3 | 265.9 | 11.01 |
| TimesFM 3.0, 120 min context | `google/timesfm-3.0-pytorch` @ `43046b85ec` | 330.7 M | TimesFM Non-Commercial License v1.0 (research/benchmarking only) | cpu | 1.4 | 36.9 | 1.53 |
| TimesFM 3.0, 24 h context | `google/timesfm-3.0-pytorch` @ `43046b85ec` | 330.7 M | TimesFM Non-Commercial License v1.0 (research/benchmarking only) | cpu | 1.4 | 57.9 | 2.40 |
| TimesFM 3.0, 128 h context | `google/timesfm-3.0-pytorch` @ `43046b85ec` | 330.7 M | TimesFM Non-Commercial License v1.0 (research/benchmarking only) | cpu | 1.4 | 204.4 | 8.46 |

## 30-minute prediction horizon

| Method | RMSE | MAE | MAPE (%) | gRMSE |
|---|---|---|---|---|
| TimesFM 3.0, 128 h context | 11.64 ± 3.00 | 8.34 ± 2.33 | 6.45 ± 1.74 | 12.55 ± 3.60 |
| EPS-TFT w/o covariate encoder † | 11.99 ± 2.96 | 8.58 ± 2.26 | 6.68 ± 1.86 | 12.93 ± 3.68 |
| LSTM † | 12.02 ± 2.82 | 8.74 ± 2.11 | 6.96 ± 2.10 | 13.01 ± 3.59 |
| **EPS-TFT** | 12.04 ± 3.02 | 8.71 ± 2.37 | 6.87 ± 2.30 | 13.07 ± 3.90 |
| EPS-TFT w/o LSTM decoder † | 12.07 ± 3.42 | 8.73 ± 2.63 | 6.97 ± 2.90 | 13.09 ± 4.61 |
| TimesFM 2.5, 128 h context | 12.08 ± 3.11 | 8.67 ± 2.40 | 6.69 ± 1.80 | 12.99 ± 3.73 |
| N-HiTS † | 12.29 ± 3.06 | 8.86 ± 2.29 | 6.98 ± 2.11 | 13.22 ± 3.72 |
| N-BEATS † | 12.31 ± 3.17 | 8.81 ± 2.38 | 6.90 ± 2.11 | 13.29 ± 3.87 |
| Chronos-2, 128 h context | 12.38 ± 3.31 | 8.83 ± 2.48 | 6.80 ± 1.80 | 13.25 ± 3.89 |
| SVR † | 12.51 ± 3.41 | 8.97 ± 2.46 | 7.06 ± 2.31 | 13.58 ± 4.30 |
| XGBoost † | 12.51 ± 3.15 | 9.08 ± 2.38 | 7.44 ± 3.76 | 13.69 ± 4.32 |
| LR † | 12.63 ± 3.06 | 9.28 ± 2.25 | 7.42 ± 2.23 | 13.64 ± 3.76 |
| TimesFM 3.0, 24 h context | 12.73 ± 3.19 | 9.04 ± 2.45 | 6.92 ± 1.82 | 13.71 ± 3.90 |
| TimesFM 2.5, 24 h context | 12.75 ± 3.22 | 9.06 ± 2.46 | 6.95 ± 1.83 | 13.78 ± 3.95 |
| Chronos-Bolt base, 128 h context | 13.05 ± 3.53 | 9.30 ± 2.67 | 7.12 ± 1.90 | 14.00 ± 4.21 |
| Chronos-Bolt small, 128 h context | 13.48 ± 3.66 | 9.60 ± 2.79 | 7.33 ± 1.96 | 14.40 ± 4.26 |
| Chronos-2, 24 h context | 13.71 ± 3.61 | 9.76 ± 2.68 | 7.47 ± 1.94 | 14.55 ± 4.18 |
| Chronos-Bolt base, 24 h context | 14.52 ± 3.97 | 10.30 ± 2.98 | 7.81 ± 2.01 | 15.51 ± 4.78 |
| Chronos-Bolt base, 120 min context | 14.65 ± 4.08 | 10.24 ± 2.99 | 7.72 ± 2.11 | 15.66 ± 4.83 |
| Chronos-Bolt small, 24 h context | 14.84 ± 4.10 | 10.57 ± 3.14 | 8.01 ± 2.11 | 15.81 ± 4.87 |
| Chronos-2, 120 min context | 14.88 ± 4.16 | 10.35 ± 2.99 | 7.79 ± 2.11 | 15.84 ± 4.91 |
| Chronos-Bolt small, 120 min context | 15.00 ± 4.24 | 10.48 ± 3.11 | 7.87 ± 2.17 | 16.14 ± 5.10 |
| Persistence (last value) | 15.73 ± 4.59 | 11.06 ± 3.43 | 8.31 ± 2.38 | 17.08 ± 5.60 |
| TimesFM 2.5, 120 min context | 17.60 ± 5.13 | 12.15 ± 3.54 | 9.11 ± 2.51 | 19.41 ± 6.59 |
| TimesFM 3.0, 120 min context | 17.73 ± 5.06 | 12.25 ± 3.54 | 9.28 ± 2.61 | 18.59 ± 5.68 |

## 60-minute prediction horizon

| Method | RMSE | MAE | MAPE (%) | gRMSE |
|---|---|---|---|---|
| TimesFM 3.0, 128 h context | 19.88 ± 5.74 | 14.11 ± 4.29 | 10.80 ± 3.10 | 22.19 ± 7.26 |
| Chronos-2, 128 h context | 20.48 ± 6.09 | 14.47 ± 4.50 | 11.01 ± 3.18 | 22.69 ± 7.55 |
| TimesFM 2.5, 128 h context | 20.69 ± 6.03 | 14.71 ± 4.56 | 11.23 ± 3.28 | 23.07 ± 7.62 |
| EPS-TFT w/o LSTM decoder † | 20.92 ± 6.31 | 15.03 ± 4.89 | 11.90 ± 5.26 | 23.24 ± 8.43 |
| **EPS-TFT** | 21.21 ± 6.01 | 15.31 ± 4.80 | 12.12 ± 5.06 | 23.83 ± 8.11 |
| Chronos-Bolt base, 128 h context | 21.26 ± 6.32 | 15.11 ± 4.74 | 11.50 ± 3.40 | 23.58 ± 7.93 |
| Chronos-Bolt small, 128 h context | 21.37 ± 6.28 | 15.15 ± 4.73 | 11.50 ± 3.35 | 23.60 ± 7.74 |
| EPS-TFT w/o covariate encoder † | 21.42 ± 5.67 | 15.27 ± 4.21 | 11.82 ± 3.70 | 24.16 ± 7.68 |
| LSTM † | 21.51 ± 5.21 | 15.60 ± 3.85 | 12.52 ± 4.57 | 24.15 ± 7.19 |
| SVR † | 22.14 ± 6.30 | 15.76 ± 4.53 | 12.29 ± 4.39 | 25.10 ± 8.58 |
| XGBoost † | 22.26 ± 6.02 | 16.25 ± 4.71 | 13.59 ± 8.92 | 25.30 ± 9.12 |
| N-HiTS † | 22.32 ± 5.83 | 16.22 ± 4.22 | 12.82 ± 4.33 | 25.20 ± 7.91 |
| N-BEATS † | 22.40 ± 5.83 | 16.40 ± 4.18 | 13.19 ± 5.05 | 25.39 ± 7.95 |
| TimesFM 2.5, 24 h context | 22.59 ± 6.51 | 16.05 ± 4.94 | 12.12 ± 3.61 | 25.28 ± 8.45 |
| TimesFM 3.0, 24 h context | 22.60 ± 6.37 | 16.02 ± 4.80 | 12.07 ± 3.43 | 25.18 ± 8.19 |
| LR † | 22.93 ± 5.80 | 16.95 ± 4.16 | 13.73 ± 4.94 | 25.90 ± 7.86 |
| Chronos-2, 24 h context | 23.76 ± 6.86 | 16.90 ± 5.08 | 12.79 ± 3.62 | 26.05 ± 8.42 |
| Chronos-Bolt base, 24 h context | 24.83 ± 7.57 | 17.70 ± 5.71 | 13.23 ± 3.77 | 27.37 ± 9.53 |
| Chronos-Bolt small, 24 h context | 24.94 ± 7.65 | 17.68 ± 5.77 | 13.19 ± 3.83 | 27.44 ± 9.56 |
| Chronos-Bolt base, 120 min context | 25.17 ± 7.65 | 17.85 ± 5.70 | 13.38 ± 4.03 | 27.83 ± 9.58 |
| Chronos-Bolt small, 120 min context | 25.31 ± 7.79 | 18.04 ± 5.89 | 13.54 ± 4.17 | 28.11 ± 9.85 |
| Persistence (last value) | 25.95 ± 8.22 | 18.51 ± 6.21 | 13.90 ± 4.40 | 28.79 ± 10.31 |
| Chronos-2, 120 min context | 26.06 ± 7.83 | 18.30 ± 5.75 | 13.64 ± 4.03 | 28.44 ± 9.53 |
| TimesFM 2.5, 120 min context | 28.57 ± 8.89 | 20.44 ± 6.64 | 15.30 ± 4.68 | 32.00 ± 11.48 |
| TimesFM 3.0, 120 min context | 33.57 ± 10.78 | 23.24 ± 7.52 | 17.53 ± 5.62 | 35.57 ± 12.08 |

† Trained baselines copied from `reports/shanghai-v1/metrics.json` (same split and windows) for context; not re-run here.

## 80% prediction interval (q0.1–q0.9)

Nominal coverage 80%; below / above = % of targets under q0.1 / over q0.9 (nominal 10 each). Persistence has no interval.

| Method | 30 min coverage (%) | 30 min width (mg/dL) | 30 min below / above (%) | 60 min coverage (%) | 60 min width (mg/dL) | 60 min below / above (%) |
|---|---|---|---|---|---|---|
| EPS-TFT | 77.96 ± 6.94 | 26.99 ± 6.42 | 10.0 / 12.0 | 77.12 ± 8.64 | 46.76 ± 11.33 | 11.5 / 11.4 |
| Chronos-Bolt small, 120 min context | 71.89 ± 3.43 | 33.34 ± 10.38 | 15.4 / 12.7 | 64.83 ± 6.09 | 47.85 ± 15.10 | 19.8 / 15.4 |
| Chronos-Bolt small, 24 h context | 77.53 ± 3.75 | 32.28 ± 9.85 | 9.3 / 13.1 | 75.30 ± 4.85 | 49.78 ± 16.05 | 9.9 / 14.8 |
| Chronos-Bolt small, 128 h context | 83.47 ± 4.59 | 32.98 ± 9.26 | 7.9 / 8.7 | 79.79 ± 6.01 | 46.69 ± 14.60 | 10.2 / 10.0 |
| Chronos-Bolt base, 120 min context | 73.85 ± 3.54 | 33.71 ± 10.68 | 13.6 / 12.5 | 66.80 ± 5.41 | 49.19 ± 15.85 | 17.8 / 15.4 |
| Chronos-Bolt base, 24 h context | 79.75 ± 3.79 | 32.86 ± 10.09 | 7.0 / 13.3 | 75.25 ± 5.09 | 49.11 ± 15.84 | 8.7 / 16.0 |
| Chronos-Bolt base, 128 h context | 84.21 ± 4.40 | 32.64 ± 9.20 | 7.2 / 8.6 | 80.44 ± 5.41 | 46.91 ± 14.20 | 9.7 / 9.8 |
| Chronos-2, 120 min context | 74.28 ± 3.60 | 33.52 ± 10.29 | 12.6 / 13.2 | 69.21 ± 4.22 | 50.73 ± 15.99 | 15.0 / 15.8 |
| Chronos-2, 24 h context | 75.57 ± 3.06 | 27.70 ± 7.52 | 12.3 / 12.2 | 76.35 ± 4.35 | 47.64 ± 13.95 | 10.8 / 12.9 |
| Chronos-2, 128 h context | 74.65 ± 5.03 | 24.78 ± 6.81 | 14.1 / 11.3 | 77.59 ± 5.56 | 42.18 ± 12.91 | 11.8 / 10.6 |
| TimesFM 2.5, 120 min context | 56.36 ± 4.46 | 24.45 ± 7.25 | 20.5 / 23.2 | 46.13 ± 6.32 | 31.24 ± 9.85 | 25.3 / 28.6 |
| TimesFM 2.5, 24 h context | 82.13 ± 4.29 | 32.34 ± 9.23 | 10.1 / 7.8 | 80.21 ± 4.48 | 51.06 ± 15.77 | 9.5 / 10.3 |
| TimesFM 2.5, 128 h context | 80.77 ± 5.84 | 29.41 ± 8.94 | 11.3 / 8.0 | 78.94 ± 6.59 | 45.84 ± 15.36 | 11.4 / 9.7 |
| TimesFM 3.0, 120 min context | 51.44 ± 4.76 | 21.53 ± 6.14 | 21.0 / 27.5 | 42.77 ± 7.25 | 31.78 ± 9.53 | 23.9 / 33.3 |
| TimesFM 3.0, 24 h context | 79.24 ± 3.37 | 28.77 ± 7.87 | 10.9 / 9.9 | 81.29 ± 4.02 | 52.05 ± 15.38 | 8.6 / 10.1 |
| TimesFM 3.0, 128 h context | 77.81 ± 3.82 | 26.00 ± 7.18 | 12.9 / 9.3 | 79.77 ± 5.24 | 45.03 ± 13.70 | 11.2 / 9.0 |

## Paired test vs EPS-TFT (per-patient RMSE)

Shapiro–Wilk on the paired differences, paired two-sided t-test and Wilcoxon signed-rank, as in the evaluation report. Negative Δ means EPS-TFT has the lower error.

| Horizon | Method | n | mean Δ RMSE (EPS-TFT − method) | Shapiro p | t-test p | Wilcoxon p | significant (paper criterion) |
|---|---|---|---|---|---|---|---|
| 30 min | Persistence (last value) | 112 | -3.70 | 0.00348 | 1.19e-24 | 3.11e-17 | False |
| 30 min | Chronos-Bolt small, 120 min context | 112 | -2.96 | 0.000934 | 6.84e-23 | 2.21e-16 | False |
| 30 min | Chronos-Bolt small, 24 h context | 112 | -2.80 | 0.000194 | 5.97e-23 | 1.23e-16 | False |
| 30 min | Chronos-Bolt small, 128 h context | 112 | -1.44 | 0.0122 | 1.07e-12 | 4.22e-12 | False |
| 30 min | Chronos-Bolt base, 120 min context | 112 | -2.61 | 0.00082 | 6.42e-21 | 1.36e-15 | False |
| 30 min | Chronos-Bolt base, 24 h context | 112 | -2.48 | 7.39e-05 | 1.62e-20 | 8.06e-16 | False |
| 30 min | Chronos-Bolt base, 128 h context | 112 | -1.01 | 0.00036 | 3.88e-08 | 2.39e-09 | False |
| 30 min | Chronos-2, 120 min context | 112 | -2.84 | 0.000408 | 3.27e-23 | 1.96e-16 | False |
| 30 min | Chronos-2, 24 h context | 112 | -1.68 | 1.05e-06 | 1.27e-15 | 1.25e-13 | False |
| 30 min | Chronos-2, 128 h context | 112 | -0.35 | 2.75e-07 | 0.0328 | 0.000661 | False |
| 30 min | TimesFM 2.5, 120 min context | 112 | -5.56 | 0.000501 | 1.52e-33 | 5.12e-19 | False |
| 30 min | TimesFM 2.5, 24 h context | 112 | -0.71 | 6.59e-09 | 8.2e-06 | 1.07e-08 | False |
| 30 min | TimesFM 2.5, 128 h context | 112 | -0.04 | 6.83e-09 | 0.778 | 0.0653 | False |
| 30 min | TimesFM 3.0, 120 min context | 112 | -5.69 | 0.259 | 1.58e-34 | 4.86e-19 | True |
| 30 min | TimesFM 3.0, 24 h context | 112 | -0.69 | 1.31e-09 | 7.29e-06 | 1.23e-08 | False |
| 30 min | TimesFM 3.0, 128 h context | 112 | +0.40 | 1.54e-09 | 0.00322 | 0.0404 | False |
| 60 min | Persistence (last value) | 112 | -4.73 | 3.61e-05 | 4.46e-15 | 1.62e-13 | False |
| 60 min | Chronos-Bolt small, 120 min context | 112 | -4.09 | 3.14e-06 | 1.5e-13 | 7e-13 | False |
| 60 min | Chronos-Bolt small, 24 h context | 112 | -3.72 | 4.53e-05 | 2.65e-12 | 4.22e-12 | False |
| 60 min | Chronos-Bolt small, 128 h context | 112 | -0.16 | 7.09e-06 | 0.669 | 0.0623 | False |
| 60 min | Chronos-Bolt base, 120 min context | 112 | -3.95 | 3.4e-06 | 6e-13 | 1.84e-12 | False |
| 60 min | Chronos-Bolt base, 24 h context | 112 | -3.61 | 5.59e-06 | 2.44e-12 | 4.39e-12 | False |
| 60 min | Chronos-Bolt base, 128 h context | 112 | -0.04 | 2.31e-06 | 0.907 | 0.14 | False |
| 60 min | Chronos-2, 120 min context | 112 | -4.85 | 9.08e-06 | 2.87e-16 | 1.19e-13 | False |
| 60 min | Chronos-2, 24 h context | 112 | -2.54 | 1.27e-07 | 1.49e-08 | 1.86e-09 | False |
| 60 min | Chronos-2, 128 h context | 112 | +0.73 | 2.75e-08 | 0.0537 | 0.501 | False |
| 60 min | TimesFM 2.5, 120 min context | 112 | -7.36 | 4.23e-05 | 4.15e-24 | 2.27e-16 | False |
| 60 min | TimesFM 2.5, 24 h context | 112 | -1.38 | 4.68e-09 | 0.000376 | 5.67e-07 | False |
| 60 min | TimesFM 2.5, 128 h context | 112 | +0.53 | 4.49e-10 | 0.143 | 0.979 | False |
| 60 min | TimesFM 3.0, 120 min context | 112 | -12.35 | 0.062 | 7.67e-31 | 3.13e-18 | True |
| 60 min | TimesFM 3.0, 24 h context | 112 | -1.39 | 1.31e-09 | 0.000259 | 1.44e-07 | False |
| 60 min | TimesFM 3.0, 128 h context | 112 | +1.34 | 5.09e-09 | 0.000235 | 0.0012 | False |

## Context actually used

| Context | Steps | Min length | Median length | Full length (%) |
|---|---|---|---|---|
| 120 min | 8 | 8 | 8 | 100.0 |
| 24 h | 96 | 96 | 96 | 100.0 |
| 128 h | 512 | 206 | 512 | 93.7 |

## Not run

| Model | Source | Licence / weights | Why not |
|---|---|---|---|
| GluFormer (Lutsker et al., Nature 2026) | https://github.com/Guylu/GluFormer | Code Apache-2.0; no weights | No pretrained checkpoint is published: the official repository holds training/inference code, demo CSVs and a small tokenised sample tensor, and no weights are on the Hugging Face Hub. The GlucoFM paper (arXiv:2605.30865v2, App. B) also reports that official GluFormer checkpoints were unavailable and retrains it. Zero-shot evaluation is impossible without the authors' weights; retraining on our data would no longer be zero-shot. |
| GlucoFM (Li et al., arXiv:2605.30865, NeurIPS 2026) | https://arxiv.org/abs/2605.30865 | Official weights not released | The authors state that code will be released; no official weights are public. Community reconstructions exist (sfourdrinier/opencgm, eugenehp/glucofm-encoder, MIT) but are encoder-only representation models (128-d embeddings of one-day, 288-point 5-min windows) with no forecasting head, and they are not the authors' model, so there is no zero-shot forecast to evaluate. |
| Moirai 1.1 / 2.0 (Salesforce) | https://huggingface.co/Salesforce/moirai-2.0-R-small | Weights CC-BY-NC-4.0 (research use allowed) | Runnable in principle, but its package uni2ts 2.0.0 pins torch<2.5, numpy~=1.26 and scipy~=1.11, which conflict with this project's environment (torch 2.14, numpy 2.5 when checked); it would need a separate virtualenv. Chronos and TimesFM cover the general-purpose models instead. |

## Discussion

- 30 min: the best zero-shot model is TimesFM 3.0, 128 h context with RMSE 11.64 mg/dL vs 12.04 for EPS-TFT (0.40 mg/dL lower; paired per-patient Wilcoxon p = 0.0404, t-test p = 0.00322; paper criterion not met, paired differences not normal). Across all 15 foundation-model rows, 13 are significantly worse than EPS-TFT and 1 significantly better (Wilcoxon p < 0.05).
- 60 min: the best zero-shot model is TimesFM 3.0, 128 h context with RMSE 19.88 mg/dL vs 21.21 for EPS-TFT (1.34 mg/dL lower; paired per-patient Wilcoxon p = 0.0012, t-test p = 0.000235; paper criterion not met, paired differences not normal). Across all 15 foundation-model rows, 10 are significantly worse than EPS-TFT and 1 significantly better (Wilcoxon p < 0.05).
- Cost: TimesFM 3.0, 128 h context has 330.7 M parameters and needs 8.46 ms per forecast on cpu, vs 286 k and 0.03 ms for EPS-TFT, and it reads 128 h of history instead of 120 min.
- Persistence (last value) scores 25.95 mg/dL RMSE at 60 min; 12 of 15 foundation-model rows beat it.
- Longest vs shortest context (128 h vs 120 min) changes 60-min RMSE by: Chronos-Bolt small -3.94; Chronos-Bolt base -3.91; Chronos-2 -5.58; TimesFM 2.5 -7.89; TimesFM 3.0 -13.69 mg/dL.
- With EPS-TFT's own 120 min context, 10 of 10 foundation-model/horizon pairs are significantly worse than EPS-TFT (Wilcoxon p < 0.05).
- Reading: glucose history beyond 120 min carries signal that EPS-TFT's 120 min look-back discards. Retraining EPS-TFT with a longer look-back is the cheaper experiment before considering a foundation model in the product (whose licence would not allow TimesFM 3.0 there anyway).
- Best permissively licensed model at 60 min: Chronos-2, 128 h context (Apache-2.0), RMSE 20.48 vs 21.21 mg/dL for EPS-TFT (Wilcoxon p = 0.501).
- The nominal 80% interval (q0.1–q0.9) covers 77.1% of 60-min targets for EPS-TFT and 79.8% for TimesFM 3.0, 128 h context (range over all foundation-model rows 42.8–81.3%).
- For context, the best trained model in `reports/shanghai-v1/metrics.json` at 60 min is EPS-TFT w/o LSTM decoder (20.92 mg/dL).

Caveats:

- EPS-TFT and the trained baselines were fit on the training split of the same dataset; the foundation models are zero-shot and see glucose only (no time of day, no static covariates). Fine-tuned foundation models could do better; that is not tested here.
- Rows with a context longer than 120 min see history EPS-TFT never sees (the longest reach into the train/validation part of the same series). That favours the foundation models; it is still causal (nothing after the forecast origin).
- ShanghaiDM is public (2023). Whether it is in any model's pretraining corpus is not documented, so leakage in favour of the foundation models cannot be ruled out.
- 15-min sampling and a 2–4-step horizon are short for these models; the 120-min context is only 8 points, below their input patch sizes (16–32), so they rely on padding there.
- Per-patient means weight every patient equally; STD is across patients (sample STD), as in the evaluation report. The paper's significance criterion needs normal paired differences (Shapiro–Wilk); when that fails, read the Wilcoxon p.
- Runtime is wall-clock inference over all test windows on the listed device, excluding data preparation; load time includes reading cached weights (first run also downloads them).
- Research only: none of these models is used by the app, and TimesFM 3.0 weights are licensed for non-commercial, non-production use only.
