# In-silico PLGM trial (paper Appendix B, hardware-free)

- Simulator: simglucose 0.2.11 (UVA/Padova adult cohort), 10 virtual adults x 90 days, seed 0
- Forecaster: `shanghai-v1` (shanghai, 15-min CGM, look-back 120 min); suspend basal when the q=0.5 forecast at 60 min is <= 70 mg/dL, decision every 5 min
- Carb counting error per meal ~ N(1.2, 0.3); 15 g rescue carbs when CGM < 54 mg/dL (at most every 15 min), both arms
- Wall-clock runtime: 205 s

## Cohort outcomes (true simulated BG; TBR/TIR/TAR = patient mean, CVGA pooled over patient-days)

| Metric | Open loop | PLGM | Paper open loop | Paper PLGM |
|---|---|---|---|---|
| TBR <70 mg/dL (%) | 4.6 | 3.6 | 5.3 | 1.9 |
| TIR 70-180 mg/dL (%) | 93.0 | 93.0 | 74.6 | 75.2 |
| TAR >180 mg/dL (%) | 2.4 | 3.4 | - | - |
| Mean BG (mg/dL) | 115.0 | 119.0 | - | - |
| CVGA A+B (%) | 42.0 | 47.4 | 71 | 80 |
| CVGA D+E (%) | 20.9 | 24.6 | - | -9 pts vs open loop |
| Basal suspended (% time) | 0.0 | 4.9 | - | - |
| Basal / bolus insulin (U/day) | 30.0 / 29.4 | 28.6 / 29.6 | - | - |
| Rescue carbs (g/day) | 17.5 | 13.9 | - | - |
| 60-min forecast RMSE vs BG (mg/dL) | - | 29.8 | - | - |

## Per patient

| Patient | Arm | TBR | TIR | TAR | A+B | D+E | Suspended | Forecast RMSE |
|---|---|---|---|---|---|---|---|---|
| adult#001 | open_loop | 6.2 | 92.0 | 1.8 | 27 | 29 | 0.0 | n/a |
| adult#001 | plgm | 5.6 | 91.4 | 3.0 | 31 | 46 | 8.5 | 30.5 |
| adult#002 | open_loop | 5.7 | 94.3 | 0.0 | 36 | 0 | 0.0 | n/a |
| adult#002 | plgm | 4.2 | 95.8 | 0.0 | 47 | 0 | 4.3 | 25.8 |
| adult#003 | open_loop | 1.9 | 97.5 | 0.7 | 60 | 11 | 0.0 | n/a |
| adult#003 | plgm | 1.4 | 97.6 | 1.0 | 64 | 9 | 3.1 | 29.7 |
| adult#004 | open_loop | 1.7 | 92.8 | 5.5 | 63 | 31 | 0.0 | n/a |
| adult#004 | plgm | 1.1 | 92.5 | 6.4 | 66 | 30 | 3.3 | 35.2 |
| adult#005 | open_loop | 4.9 | 94.3 | 0.8 | 27 | 11 | 0.0 | n/a |
| adult#005 | plgm | 4.4 | 94.5 | 1.1 | 31 | 13 | 5.2 | 29.3 |
| adult#006 | open_loop | 5.8 | 90.3 | 3.8 | 34 | 24 | 0.0 | n/a |
| adult#006 | plgm | 4.4 | 87.5 | 8.1 | 38 | 38 | 5.6 | 28.0 |
| adult#007 | open_loop | 1.0 | 98.6 | 0.3 | 83 | 1 | 0.0 | n/a |
| adult#007 | plgm | 0.2 | 98.4 | 1.4 | 96 | 0 | 3.5 | 26.1 |
| adult#008 | open_loop | 6.9 | 93.1 | 0.0 | 37 | 1 | 0.0 | n/a |
| adult#008 | plgm | 4.2 | 95.7 | 0.1 | 47 | 2 | 8.0 | 27.3 |
| adult#009 | open_loop | 8.0 | 85.7 | 6.3 | 7 | 67 | 0.0 | n/a |
| adult#009 | plgm | 7.5 | 85.6 | 6.9 | 9 | 70 | 4.1 | 34.2 |
| adult#010 | open_loop | 3.5 | 91.4 | 5.1 | 47 | 33 | 0.0 | n/a |
| adult#010 | plgm | 3.4 | 91.0 | 5.6 | 47 | 38 | 3.0 | 30.0 |

## Differences from the paper's trial

- Simulator: open-source simglucose 0.2.11 (2008 UVA/Padova adult parameter set) instead of the paper's UVA/Padova T1D simulator; no hardware: the wristband/USB link is replaced by an in-process call of the production `ForecastEngine` (float32 PyTorch, not the quantized edge build).
- Forecaster: trained on shanghai (15-min CGM) and applied zero-shot to simulated T1D adults (no fine-tuning on simulator data); a 15-min model, whereas the paper's trial used a 5-min model: the engine is fed the 5-min GuardianRT CGM trace strided to 15 min (8 samples of look-back); suspension decisions are still made every 5 min.
- Static covariates: simglucose has age and weight but not height or sex, so every virtual adult is T1D with Quest-table age, ShanghaiDM T1D median BMI (20.9) and majority gender (M).
- Therapy and scenario: simglucose RandomScenario meals (seeded) and its basal-bolus rule with a per-meal carb-counting error chosen so the open-loop TBR is close to the paper's, plus rescue carbs for level-2 hypoglycemia (without them simglucose BG can collapse to 0 and stay there); the paper does not specify its scenario, baseline therapy or hypotreatment. Simglucose adults under this therapy spend much less time above range than the paper's cohort, so TIR/CVGA baselines are not directly comparable.
- Duration: 90 days (paper: 3 months).
- Outcomes are computed on true simulated BG at 5-min resolution; CVGA uses one point per patient-day pooled over the cohort (the paper's Fig. 8 shows one virtual adult; per-patient CVGA is in the table above and `report.json`).
