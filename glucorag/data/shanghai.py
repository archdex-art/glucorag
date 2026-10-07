"""Loader for the ShanghaiT1DM / ShanghaiT2DM datasets (Zhao et al., Sci. Data 2023).

Expected layout (figshare 10.6084/m9.figshare.20444397, extracted)::

    root/Shanghai_T1DM/<pid>_<seg>_<date>.xls[x]
    root/Shanghai_T1DM_Summary.xlsx
    root/Shanghai_T2DM/...
    root/Shanghai_T2DM_Summary.xlsx

Each file is one recording segment (``series_id`` = file stem); ``patient_id`` is the
4-digit prefix. Demographics come from the summary sheet, keyed by ``series_id``.
"""

from pathlib import Path

import pandas as pd

GENDER_CODES = {1: "F", 2: "M"}
TYPE_CODES = {"T1DM": "T1D", "T2DM": "T2D"}
INTERVAL_MIN = 15
STATIC_FEATURES = ("gender", "age", "bmi", "diabetes_type")


def read_series(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path)
    cgm_col = next(c for c in raw.columns if str(c).strip().startswith("CGM"))
    stem = path.stem
    return pd.DataFrame(
        {
            "patient_id": stem.split("_")[0],
            "series_id": stem,
            "timestamp": pd.to_datetime(raw["Date"]),
            "glucose_mg_dl": pd.to_numeric(raw[cgm_col], errors="coerce"),
        }
    )


def read_summary(path: Path) -> pd.DataFrame:
    raw = pd.read_excel(path)
    return pd.DataFrame(
        {
            "series_id": raw["Patient Number"].astype(str).str.strip(),
            "patient_id": raw["Patient Number"].astype(str).str.split("_").str[0],
            "gender": raw["Gender (Female=1, Male=2)"].map(lambda v: GENDER_CODES.get(int(v))),
            "age": raw["Age (years)"].astype(float),
            "bmi": raw["BMI (kg/m2)"].astype(float),
            "diabetes_type": raw["Type of Diabetes"].astype(str).str.strip().map(TYPE_CODES),
        }
    )


def load_shanghai(root: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(cgm, profiles)`` for all T1DM and T2DM segments under ``root``."""
    root = Path(root)
    frames: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    for cohort in ("T1DM", "T2DM"):
        folder = root / f"Shanghai_{cohort}"
        summary = root / f"Shanghai_{cohort}_Summary.xlsx"
        if not folder.is_dir() or not summary.is_file():
            raise FileNotFoundError(f"Missing {folder} or {summary}")
        files = sorted(p for p in folder.glob("*.xls*") if not p.name.startswith("~$"))
        frames.extend(read_series(p) for p in files)
        summaries.append(read_summary(summary))
    cgm = pd.concat(frames, ignore_index=True)
    profiles = pd.concat(summaries, ignore_index=True)
    missing = set(cgm["series_id"]) - set(profiles["series_id"])
    if missing:
        raise ValueError(f"Series without demographics: {sorted(missing)}")
    if profiles[list(STATIC_FEATURES)].isna().any().any():
        raise ValueError("Summary sheets contain missing or unmapped demographic values.")
    return cgm, profiles
