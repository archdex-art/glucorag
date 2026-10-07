import json

from glucorag.core.config import AppSettings
from glucorag.core.schemas import Alert, CGMRecord, PatientProfile, Prediction


def test_cgm_record_roundtrip():
    data = {
        "patient_id": "P001",
        "timestamp": "2024-01-01T12:00:00Z",
        "glucose_mg_dl": 125.5
    }
    record = CGMRecord.model_validate(data)
    assert record.patient_id == "P001"
    assert record.glucose_mg_dl == 125.5
    
    dumped = json.loads(record.model_dump_json())
    assert dumped["patient_id"] == "P001"
    assert dumped["glucose_mg_dl"] == 125.5
    assert dumped["timestamp"] == "2024-01-01T12:00:00Z"


def test_patient_profile_roundtrip():
    data = {
        "patient_id": "P002",
        "age": 45,
        "gender": "F",
        "bmi": 24.5,
        "diabetes_type": "T2D"
    }
    profile = PatientProfile.model_validate(data)
    assert profile.bmi == 24.5
    assert profile.diabetes_type == "T2D"
    
    dumped = profile.model_dump(mode="json")
    assert dumped["bmi"] == 24.5


def test_prediction_roundtrip():
    data = {
        "patient_id": "P003",
        "t0": "2024-01-01T12:00:00Z",
        "horizons": [30, 60],
        "quantiles": [0.25, 0.5, 0.75],
        "values": [
            [110.0, 115.0, 120.0],
            [105.0, 112.0, 125.0]
        ],
        "model_version": "v1.0"
    }
    pred = Prediction.model_validate(data)
    assert len(pred.values) == 2
    assert len(pred.values[0]) == 3
    assert pred.model_version == "v1.0"


def test_alert_roundtrip():
    alert = Alert(
        patient_id="P004",
        type="hypo",
        horizon_min=30,
        severity="high"
    )
    assert alert.type == "hypo"
    assert alert.t_raised is not None
    
    dumped = alert.model_dump(mode="json")
    assert dumped["type"] == "hypo"


def test_config_defaults():
    settings = AppSettings()
    assert settings.environment == "dev"
    assert settings.alert_thresholds.hypo_mg_dl == 70.0
    assert settings.model.lookback_min == 120
