from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # --- Database ---
    db_path: Path = Field(default=Path("data/stock.db"))

    # --- Data Acquisition ---
    data_start_date: str = Field(default="2020-01-01")
    fetch_batch_delay: float = Field(default=0.5)
    enable_eastmoney_patch: bool = Field(default=True)

    # --- Technical Indicators ---
    ma_periods: List[int] = Field(default=[5, 10, 20, 60])
    rsi_period: int = Field(default=14)
    macd_fast: int = Field(default=12)
    macd_slow: int = Field(default=26)
    macd_signal: int = Field(default=9)
    bb_period: int = Field(default=20)
    bb_std: float = Field(default=2.0)
    enabled_indicators: List[str] = Field(
        default=["ma", "rsi", "macd", "bollinger"]
    )

    # --- AI / ML ---
    prediction_horizon: int = Field(default=5)
    train_test_split: float = Field(default=0.8)
    model_dir: Path = Field(default=Path("data/models"))
    rf_n_estimators: int = Field(default=200)
    rf_max_depth: int = Field(default=10)

    # --- Logging ---
    log_level: str = Field(default="INFO")
    log_rotation: str = Field(default="10 MB")
    log_retention: str = Field(default="7 days")

    @classmethod
    def _json_field_parser(cls, raw: str) -> list:
        """Parse env-var JSON list fields (pydantic-settings doesn't auto-parse)."""
        if isinstance(raw, list):
            return raw
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    @classmethod
    def parse_ma_periods(cls, raw: str | list) -> list[int]:
        return cls._json_field_parser(raw)

    @classmethod
    def parse_enabled_indicators(cls, raw: str | list) -> list[str]:
        return cls._json_field_parser(raw)


settings = Settings()
