"""Significance testing and cross-individual cross-validation folds.

Follows the paper's Discussion: Shapiro-Wilk on the paired per-patient differences, then a
paired t-test of EPS-TFT against the next-best method; 5-fold cross-individual validation on
ShanghaiDM stratified by diabetes type.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import stats
from sklearn.model_selection import StratifiedKFold


@dataclass(frozen=True)
class PairedTestResult:
    n: int
    mean_difference: float  # mean(a - b); negative means ``a`` has lower error
    shapiro_w: float
    shapiro_p: float
    differences_normal: bool  # Shapiro-Wilk does not reject normality at ``alpha``
    t_statistic: float
    t_p: float
    wilcoxon_p: float  # reported alongside in case normality is rejected
    alpha: float

    @property
    def significant(self) -> bool:
        """Paper's criterion: paired t-test p < alpha (with normality not rejected)."""
        return self.differences_normal and self.t_p < self.alpha

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"significant": self.significant}


def paired_test(
    a: npt.ArrayLike,
    b: npt.ArrayLike,
    alpha: float = 0.05,
    alternative: Literal["two-sided", "less", "greater"] = "two-sided",
) -> PairedTestResult:
    """Shapiro-Wilk on ``a - b`` followed by a paired t-test (and Wilcoxon signed-rank).

    ``a`` and ``b`` are per-patient errors aligned by patient.
    """
    x = np.asarray(a, dtype=np.float64)
    y = np.asarray(b, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("Paired samples must be 1-D arrays of equal length")
    if x.size < 3:
        raise ValueError("Shapiro-Wilk needs at least 3 paired samples")
    diff = x - y
    shapiro = stats.shapiro(diff)
    ttest = stats.ttest_rel(x, y, alternative=alternative)
    wilcoxon_p = (
        float(stats.wilcoxon(x, y, alternative=alternative).pvalue)
        if np.any(diff != 0)
        else 1.0
    )
    return PairedTestResult(
        n=int(x.size),
        mean_difference=float(diff.mean()),
        shapiro_w=float(shapiro.statistic),
        shapiro_p=float(shapiro.pvalue),
        differences_normal=bool(shapiro.pvalue >= alpha),
        t_statistic=float(ttest.statistic),
        t_p=float(ttest.pvalue),
        wilcoxon_p=wilcoxon_p,
        alpha=alpha,
    )


def next_best(mean_scores: Mapping[str, float], exclude: str) -> str:
    """Method with the lowest mean error other than ``exclude``."""
    candidates = {k: v for k, v in mean_scores.items() if k != exclude}
    if not candidates:
        raise ValueError("No competing method to compare against")
    return min(candidates, key=lambda k: candidates[k])


def align_patients(
    per_patient: Mapping[str, pd.DataFrame], methods: tuple[str, str], horizon_min: int,
    metric: str,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Per-patient ``metric`` of two methods at one horizon, aligned on common patients."""
    series = []
    for method in methods:
        frame = per_patient[method]
        frame = frame[frame["horizon_min"] == horizon_min]
        series.append(frame.set_index("patient_id")[metric])
    joined = pd.concat(series, axis=1, join="inner").sort_index()
    return joined.iloc[:, 0].to_numpy(np.float64), joined.iloc[:, 1].to_numpy(np.float64)


def patient_strata(profiles: pd.DataFrame, stratum_col: str = "diabetes_type") -> pd.Series:
    """One stratum label per patient (profiles have one row per series)."""
    per_patient = profiles.groupby("patient_id")[stratum_col].unique()
    inconsistent = per_patient[per_patient.map(len) > 1]
    if len(inconsistent):
        raise ValueError(f"Patients with conflicting {stratum_col}: {list(inconsistent.index)}")
    return per_patient.map(lambda v: v[0]).sort_index()


def cross_individual_folds(
    strata: pd.Series, n_folds: int = 5, seed: int = 0
) -> list[tuple[list[Any], list[Any]]]:
    """Stratified K-fold over patients: ``[(train_patients, test_patients), ...]``.

    ``strata`` maps patient_id -> stratum (e.g. from :func:`patient_strata`). Patients are the
    unit, so all series of a patient land in the same fold; each patient is tested once.
    """
    patients = strata.index.to_numpy()
    labels = strata.to_numpy()
    splitter = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    return [
        (sorted(patients[tr].tolist()), sorted(patients[te].tolist()))
        for tr, te in splitter.split(patients, labels)
    ]
