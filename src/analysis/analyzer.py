from __future__ import annotations

from typing import List

import pandas as pd
from loguru import logger

from config.settings import settings
from src.analysis.indicators.base import BaseIndicator
from src.analysis.indicators.bollinger import BollingerBands
from src.analysis.indicators.ma import MovingAverage
from src.analysis.indicators.macd import MACD
from src.analysis.indicators.rsi import RSI
from src.core.exceptions import AnalysisError
from src.core.models.technical import TechnicalIndicators


class TechnicalAnalyzer:
    """Computes technical indicators via a configurable registry."""

    _AVAILABLE_INDICATORS: dict[str, BaseIndicator] = {
        "ma": MovingAverage(),
        "rsi": RSI(),
        "macd": MACD(),
        "bollinger": BollingerBands(),
    }

    def __init__(self) -> None:
        self._registry = self._build_registry()

    def _build_registry(self) -> dict[str, BaseIndicator]:
        """Select enabled indicators based on configuration."""
        enabled = settings.enabled_indicators
        registry: dict[str, BaseIndicator] = {}
        for name in enabled:
            indicator = self._AVAILABLE_INDICATORS.get(name)
            if indicator is None:
                logger.warning(f"Unknown indicator '{name}', skipping")
                continue
            registry[name] = indicator
        logger.info(f"TechnicalAnalyzer initialized with: {list(registry.keys())}")
        return registry

    @property
    def registered_names(self) -> List[str]:
        return list(self._registry.keys())

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def compute_single(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Compute a single indicator by name, appending its column(s) to df."""
        indicator = self._registry.get(name)
        if indicator is None:
            raise AnalysisError(f"Indicator '{name}' is not registered.")
        missing = set(indicator.required_columns) - set(df.columns)
        if missing:
            raise AnalysisError(f"Missing required columns for {name}: {missing}")
        result = indicator.compute(df)
        if isinstance(result, pd.Series):
            result = result.to_frame()
        return pd.concat([df, result], axis=1)

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all registered indicators, appending to df."""
        for name in self._registry:
            df = self.compute_single(name, df)
        return df

    # ------------------------------------------------------------------
    # Conversion to Pydantic models
    # ------------------------------------------------------------------

    def to_indicator_list(self, df: pd.DataFrame) -> list[TechnicalIndicators]:
        """Convert a DataFrame with indicator columns to TechnicalIndicators list."""
        results: list[TechnicalIndicators] = []
        column_map = {
            "ma_5": "ma_5",
            "ma_10": "ma_10",
            "ma_20": "ma_20",
            "ma_60": "ma_60",
            "rsi_14": "rsi_14",
            "macd_dif": "macd_dif",
            "macd_dea": "macd_dea",
            "macd_bar": "macd_bar",
            "bb_upper": "bb_upper",
            "bb_middle": "bb_middle",
            "bb_lower": "bb_lower",
        }
        for _, row in df.iterrows():
            kwargs: dict = {"code": row["code"], "date": row["date"]}
            for col, attr in column_map.items():
                if col in df.columns:
                    val = row[col]
                    kwargs[attr] = None if pd.isna(val) else float(val)
            results.append(TechnicalIndicators(**kwargs))
        return results
