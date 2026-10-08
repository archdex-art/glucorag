"""Runtime service settings, read from ``GLUCORAG_*`` environment variables.

``GLUCORAG_API_KEYS`` is a comma-separated list; ``GLUCORAG_MODEL_PATH`` points at a
registered artifact directory (``models/<version>``). Alert thresholds default to the
shared ``settings.alert_thresholds``. ``GLUCORAG_PHONE_APK`` / ``GLUCORAG_WATCH_APK`` name
app files offered at ``/download/phone.apk`` and ``/download/watch.apk``.
"""

from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from glucorag.core.config import settings
from glucorag.risk.detectors import RiskConfig
from glucorag.service import ServiceConfig


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GLUCORAG_", extra="ignore", protected_namespaces=(), populate_by_name=True
    )

    model_path: Path | None = None
    sim_report: Path | None = Field(
        default=None, description="in-silico report.json shown on the dashboard model page"
    )
    web_dir: Path = Field(
        default=Path(__file__).parent / "static", description="built dashboard (web/ dist)"
    )
    db_path: Path = Path("data/runtime/glucorag.sqlite")
    api_keys: Annotated[list[str], NoDecode] = Field(default_factory=list)
    device: str = "cpu"
    clock: Literal["wall", "data"] = Field(
        default="wall", description="'data' = replay mode: latest reading defines time"
    )
    hypo_mg_dl: float = settings.alert_thresholds.hypo_mg_dl
    hyper_mg_dl: float = settings.alert_thresholds.hyper_mg_dl
    hypo_quantile: float = Field(default=0.25, gt=0, lt=1)
    hyper_quantile: float = Field(default=0.75, gt=0, lt=1)
    data_gap_min: int = settings.alert_thresholds.data_gap_min
    alert_cooldown_min: float = Field(default=30.0, ge=0)
    max_future_skew_s: float = Field(default=120.0, ge=0)
    watchdog_interval_s: float = Field(default=60.0, ge=0, description="0 disables")
    max_batch: int = Field(default=5000, gt=0)
    allow_signup: bool = Field(default=True, description="people may create their own account")
    cookie_secure: bool | None = Field(
        default=None, description="Secure session cookie; unset = only when served over HTTPS"
    )
    session_days: int = Field(default=14, gt=0, le=90)
    import_max_days: int = Field(default=30, gt=0, description="CSV import keeps the last N days")
    public_url: str | None = Field(
        default=None,
        description="address phones use to reach this server (pairing QR), e.g. "
        "http://192.168.1.20:8000; unset = guessed from the request",
    )
    phone_apk_path: Path | None = Field(
        default=None, validation_alias="GLUCORAG_PHONE_APK",
        description="phone app file offered at /download/phone.apk; unset = link to releases",
    )
    watch_apk_path: Path | None = Field(
        default=None, validation_alias="GLUCORAG_WATCH_APK",
        description="watch app file offered at /download/watch.apk; unset = link to releases",
    )
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    @field_validator("api_keys", mode="before")
    @classmethod
    def _split_keys(cls, v: object) -> object:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    @field_validator("public_url", mode="before")
    @classmethod
    def _strip_url(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().rstrip("/") or None
        return v

    def service_config(self) -> ServiceConfig:
        return ServiceConfig(
            risk=RiskConfig(
                hypo_mg_dl=self.hypo_mg_dl,
                hyper_mg_dl=self.hyper_mg_dl,
                hypo_quantile=self.hypo_quantile,
                hyper_quantile=self.hyper_quantile,
            ),
            data_gap_min=self.data_gap_min,
            alert_cooldown=timedelta(minutes=self.alert_cooldown_min),
            max_future_skew=timedelta(seconds=self.max_future_skew_s),
        )
