from __future__ import annotations

import pandas as pd

from config.settings import settings
from src.analysis.indicators.base import BaseIndicator


class BollingerBands(BaseIndicator):
    """Bollinger Bands (middle = MA, upper/lower = MA ± k * std)."""

    name = "bollinger"
    required_columns = ["close"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        period = settings.bb_period
        std_mul = settings.bb_std

        middle = df["close"].rolling(window=period).mean()
        std = df["close"].rolling(window=period).std()

        result = pd.DataFrame(index=df.index)
        result["bb_middle"] = middle
        result["bb_upper"] = middle + std_mul * std
        result["bb_lower"] = middle - std_mul * std
        return result
