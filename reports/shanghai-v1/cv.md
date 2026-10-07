# Cross-individual 5-fold validation: shanghai-v1

Folds split patients (stratified by diabetes type); EPS-TFT is retrained per fold on the chronological train/val portions of the training patients and tested on the full recordings of the held-out patients.

| Fold | Test patients | Epochs | RMSE 30 min | RMSE 60 min |
|---|---|---|---|---|
| 1 | 23 | 41 | 14.14 ± 3.34 | 26.26 ± 6.54 |
| 2 | 23 | 60 | 14.07 ± 3.01 | 26.61 ± 5.90 |
| 3 | 22 | 44 | 13.74 ± 2.67 | 25.19 ± 5.83 |
| 4 | 22 | 38 | 14.28 ± 2.39 | 26.32 ± 5.09 |
| 5 | 22 | 40 | 14.02 ± 2.54 | 26.08 ± 4.59 |

| Aggregate | 30 min | 60 min |
|---|---|---|
| Mean of fold means | 14.05 | 26.09 |
| All held-out patients (mean ± STD) | 14.05 ± 2.77 | 26.10 ± 5.56 |
| Paper (mean RMSE) | 14.7 | 23.5 |
