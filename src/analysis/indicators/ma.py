from __future__ import annotations

import pandas as pd

from config.settings import settings
from src.analysis.indicators.base import BaseIndicator


class MovingAverage(BaseIndicator):
    """Simple Moving Average for configured periods."""

    name = "ma"
    required_columns = ["close"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a DataFrame with one MA column per period."""
        result = pd.DataFrame(index=df.index)
        for period in settings.ma_periods:
            result[f"ma_{period}"] = df["close"].rolling(window=period).mean()
        return result
