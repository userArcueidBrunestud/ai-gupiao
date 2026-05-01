from __future__ import annotations

import pandas as pd

from config.settings import settings
from src.analysis.indicators.base import BaseIndicator


class RSI(BaseIndicator):
    """Relative Strength Index (Wilder's smoothing)."""

    name = "rsi"
    required_columns = ["close"]

    def compute(self, df: pd.DataFrame) -> pd.Series:
        period = settings.rsi_period
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100.0 - (100.0 / (1.0 + rs))
        rsi.name = f"rsi_{period}"
        return rsi
