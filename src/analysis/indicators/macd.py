from __future__ import annotations

import pandas as pd

from config.settings import settings
from src.analysis.indicators.base import BaseIndicator


class MACD(BaseIndicator):
    """MACD (Moving Average Convergence Divergence)."""

    name = "macd"
    required_columns = ["close"]

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        fast = settings.macd_fast
        slow = settings.macd_slow
        signal = settings.macd_signal

        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        bar = 2.0 * (dif - dea)

        result = pd.DataFrame(index=df.index)
        result["macd_dif"] = dif
        result["macd_dea"] = dea
        result["macd_bar"] = bar
        return result
