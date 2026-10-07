import numpy as np
import pandas as pd
import pytest

from glucorag.data.pipeline import SPECS, PreparedData
from glucorag.evaluate.cv import fold_data
from glucorag.evaluate.stats import (
    align_patients,
    cross_individual_folds,
    next_best,
    paired_test,
    patient_strata,
)
from glucorag.preprocess.normalize import StaticEncoder, ZNormalizer


def test_paired_t_test_matches_hand_computation():
    a = np.array([3.0, 5.0, 7.0, 9.0, 11.0])
    b = np.array([2.0, 3.0, 4.0, 5.0, 6.0])
    # d = [1..5]: mean 3, sd sqrt(2.5), t = 3 / (sqrt(2.5) / sqrt(5)) = 4.2426, df = 4
    res = paired_test(a, b)
    assert res.n == 5
    assert res.mean_difference == pytest.approx(3.0)
    assert res.t_statistic == pytest.approx(4.242640687)
    assert res.t_p == pytest.approx(0.0132356, rel=1e-4)
    assert res.differences_normal and res.significant


def test_lower_error_of_first_method_gives_negative_t():
    rng = np.random.default_rng(1)
    b = rng.uniform(15, 25, 30)
    res = paired_test(b - 1.0 + rng.normal(0, 0.2, 30), b)
    assert res.mean_difference < 0 and res.t_statistic < 0 and res.significant


def test_significance_requires_normal_differences():
    d = np.r_[np.linspace(0.9, 1.1, 15), 6.0]  # t-test p < 0.05 but one gross outlier
    res = paired_test(d, np.zeros_like(d))
    assert res.t_p < 0.05
    assert not res.differences_normal
    assert not res.significant


def test_paired_test_rejects_unpaired_input():
    with pytest.raises(ValueError):
        paired_test([1.0, 2.0, 3.0], [1.0, 2.0])


def test_next_best_excludes_reference():
    scores = {"EPS-TFT": 12.0, "N-BEATS": 12.5, "LR": 14.0}
    assert next_best(scores, "EPS-TFT") == "N-BEATS"
    with pytest.raises(ValueError):
        next_best({"EPS-TFT": 1.0}, "EPS-TFT")


def test_align_patients_pairs_by_patient_id():
    a = pd.DataFrame(
        {"horizon_min": [30, 30, 30, 60], "patient_id": ["p2", "p1", "p3", "p1"],
         "RMSE": [2.0, 1.0, 3.0, 9.0]}
    )
    b = pd.DataFrame(
        {"horizon_min": [30, 30], "patient_id": ["p1", "p2"], "RMSE": [10.0, 20.0]}
    )
    x, y = align_patients({"a": a, "b": b}, ("a", "b"), 30, "RMSE")
    assert x.tolist() == [1.0, 2.0] and y.tolist() == [10.0, 20.0]


def _profiles(n_t1d: int = 12, n_t2d: int = 100) -> pd.DataFrame:
    rows = []
    for i in range(n_t1d + n_t2d):
        pid = f"{i:04d}"
        dtype = "T1D" if i < n_t1d else "T2D"
        for seg in range(1 + i % 3):  # several series per patient
            rows.append({"patient_id": pid, "series_id": f"{pid}_{seg}", "diabetes_type": dtype,
                         "gender": "F", "age": 50.0 + i % 20, "bmi": 24.0})
    return pd.DataFrame(rows)


def test_patient_strata_one_label_per_patient_and_rejects_conflicts():
    strata = patient_strata(_profiles())
    assert len(strata) == 112 and strata.value_counts().to_dict() == {"T2D": 100, "T1D": 12}
    bad = _profiles(1, 1)
    bad.loc[bad["series_id"] == "0001_1", "diabetes_type"] = "T1D"
    with pytest.raises(ValueError):
        patient_strata(bad)


def test_cross_individual_folds_partition_patients_with_stratification():
    strata = patient_strata(_profiles())
    folds = cross_individual_folds(strata, n_folds=5, seed=0)
    assert len(folds) == 5
    tested: list[str] = []
    for train, test in folds:
        assert not set(train) & set(test)
        assert set(train) | set(test) == set(strata.index)
        counts = strata.loc[test].value_counts()
        assert counts["T2D"] == 20 and counts["T1D"] in (2, 3)
        tested += test
    assert sorted(tested) == sorted(strata.index)  # every patient tested exactly once
    assert folds == cross_individual_folds(strata, n_folds=5, seed=0)  # deterministic


def _prepared() -> PreparedData:
    profiles = _profiles(2, 4)
    frames = []
    for _, row in profiles.iterrows():
        ts = pd.date_range("2024-01-01", periods=20, freq="15min")
        level = 100.0 if row["patient_id"] in ("0000", "0002") else 200.0
        frames.append(pd.DataFrame({
            "patient_id": row["patient_id"], "series_id": row["series_id"], "timestamp": ts,
            "glucose_mg_dl": level + np.arange(20.0), "observed": True,
            "time_norm": 0.0, "glucose_z": 0.0,
        }))
    full = pd.concat(frames, ignore_index=True)
    order = full.groupby("series_id").cumcount()
    train, val, test = (
        pd.DataFrame(full[mask]) for mask in (order < 12, (order >= 12) & (order < 16), order >= 16)
    )
    spec = SPECS["shanghai"]
    return PreparedData(spec, train, val, test, profiles,
                        ZNormalizer(0.0, 1.0, True), StaticEncoder(spec.static_features))


def test_fold_data_has_no_patient_leakage_and_refits_on_training_patients():
    data = _prepared()
    train_p, test_p = ["0000", "0002"], ["0001", "0003", "0004", "0005"]
    fd = fold_data(data, train_p, test_p)
    assert set(fd.train["patient_id"]) == set(train_p) == set(fd.val["patient_id"])
    assert set(fd.test["patient_id"]) == set(test_p)
    # held-out patients are scored on their whole recordings
    assert len(fd.test) == len(pd.concat([data.train, data.val, data.test]).query(
        "patient_id in @test_p"))
    # train/val stay chronological per series
    last_train = fd.train.groupby("series_id")["timestamp"].max()
    first_val = fd.val.groupby("series_id")["timestamp"].min()
    assert (last_train < first_val.loc[last_train.index]).all()
    # normalization uses training patients only (their glucose is ~100-111, others ~200+)
    assert fd.glucose_norm.mu == pytest.approx(fd.train["glucose_mg_dl"].mean())
    assert fd.glucose_norm.mu < 150.0
    assert fd.test["glucose_z"].to_numpy() == pytest.approx(
        fd.glucose_norm.transform(fd.test["glucose_mg_dl"]).to_numpy())
    with pytest.raises(ValueError):
        fold_data(data, ["0000"], ["0000", "0001"])
