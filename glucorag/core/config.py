from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AlertThresholds(BaseModel):
    hypo_mg_dl: float = Field(default=70.0, description="Hypo threshold (<=)")
    hyper_mg_dl: float = Field(default=180.0, description="Hyper threshold (>=)")
    data_gap_min: int = Field(default=60, description="Gap minutes before suspend")


class ModelConfig(BaseModel):
    lookback_min: int = 120
    horizons_min: list[int] = [30, 60]
    quantiles: list[float] = [0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98]
    cgm_sampling_interval_min: int = Field(
        default=5, description="Expected sampling interval (5 or 15)"
    )

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GLUCORAG_", env_nested_delimiter="__")
    
    environment: Literal["dev", "prod", "test"] = "dev"
    alert_thresholds: AlertThresholds = AlertThresholds()
    model: ModelConfig = ModelConfig()

settings = AppSettings()
