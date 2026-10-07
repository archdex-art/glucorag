import pytest
from _runtime import tiny_artifact
from fastapi.testclient import TestClient

from glucorag.api.app import create_app
from glucorag.api.settings import ApiSettings

KEY = "k"


@pytest.fixture
def make_client(tmp_path):
    """Factory for API clients sharing one model and database under ``tmp_path``."""
    model = tiny_artifact(tmp_path / "models", [40, 50, 60, 90, 120, 130, 140])

    def make(**overrides):
        base = {"model_path": model, "db_path": tmp_path / "db.sqlite", "api_keys": [KEY],
                "clock": "data", "watchdog_interval_s": 0}
        return TestClient(create_app(ApiSettings(**(base | overrides))))
    return make
