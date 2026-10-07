"""Loader for OhioT1DM (Marling & Bunescu, 2018/2020). Requires a signed DUA; not bundled.

Expected layout: ``root/**/<pid>-ws-training.xml`` and ``root/**/<pid>-ws-testing.xml``.
Demographics are not in the XML; supply a CSV with ``patient_id,age,gender`` (gender F/M).
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

INTERVAL_MIN = 5
STATIC_FEATURES = ("gender", "age")
TS_FORMAT = "%d-%m-%Y %H:%M:%S"


def load_ohio_xml(path: str | Path, split: str) -> pd.DataFrame:
    root = ET.parse(path).getroot()
    pid = root.attrib["id"]
    node = root.find("glucose_level")
    events = [] if node is None else node.findall("event")
    return pd.DataFrame(
        {
            "patient_id": pid,
            "series_id": f"{pid}_{split}",
            "timestamp": pd.to_datetime([e.attrib["ts"] for e in events], format=TS_FORMAT),
            "glucose_mg_dl": pd.to_numeric([e.attrib["value"] for e in events], errors="coerce"),
        }
    )


def load_ohio(
    root: str | Path, profiles_csv: str | Path
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return ``(train_cgm, test_cgm, profiles)``; profiles keyed by ``series_id``."""
    root = Path(root)
    train_files = sorted(root.rglob("*-ws-training.xml"))
    test_files = sorted(root.rglob("*-ws-testing.xml"))
    if not train_files or not test_files:
        raise FileNotFoundError(f"No OhioT1DM XML files found under {root}")
    train = pd.concat([load_ohio_xml(p, "train") for p in train_files], ignore_index=True)
    test = pd.concat([load_ohio_xml(p, "test") for p in test_files], ignore_index=True)

    demo = pd.read_csv(profiles_csv, dtype={"patient_id": str})
    demo["gender"] = demo["gender"].astype(str).str.upper().str[0]
    rows = [
        {"series_id": sid, "patient_id": pid}
        for sid, pid in pd.concat([train, test])[["series_id", "patient_id"]]
        .drop_duplicates()
        .itertuples(index=False)
    ]
    profiles = pd.DataFrame(rows).merge(demo[["patient_id", "age", "gender"]], on="patient_id")
    missing = set(train["patient_id"]) | set(test["patient_id"])
    missing -= set(profiles["patient_id"])
    if missing:
        raise ValueError(f"Patients without demographics: {sorted(missing)}")
    return train, test, profiles
