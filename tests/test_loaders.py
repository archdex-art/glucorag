from pathlib import Path

import pytest

from glucorag.data.ohio import load_ohio

XML = """<patient id="{pid}" weight="99" insulin_type="Novalog">
  <glucose_level>
    <event ts="07-12-2021 01:17:00" value="101"/>
    <event ts="07-12-2021 01:22:00" value="98"/>
  </glucose_level>
</patient>"""


def _write(root: Path, pid: str) -> None:
    for split in ("training", "testing"):
        (root / f"{pid}-ws-{split}.xml").write_text(XML.format(pid=pid))


def test_ohio_parses_day_first_timestamps_and_joins_demographics(tmp_path):
    _write(tmp_path, "559")
    csv = tmp_path / "demo.csv"
    csv.write_text("patient_id,age,gender\n559,30,female\n")
    train, test, profiles = load_ohio(tmp_path, csv)
    assert train["timestamp"].iloc[0].month == 12 and train["timestamp"].iloc[0].day == 7
    assert train["glucose_mg_dl"].tolist() == [101, 98]
    assert set(profiles["series_id"]) == {"559_train", "559_test"}
    assert profiles["gender"].unique().tolist() == ["F"]


def test_ohio_requires_demographics_for_every_patient(tmp_path):
    _write(tmp_path, "559")
    _write(tmp_path, "563")
    csv = tmp_path / "demo.csv"
    csv.write_text("patient_id,age,gender\n559,30,F\n")
    with pytest.raises(ValueError, match="563"):
        load_ohio(tmp_path, csv)
