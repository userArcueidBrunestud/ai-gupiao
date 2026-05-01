from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.analysis.analyzer import TechnicalAnalyzer
from src.core.exceptions import AnalysisError


@pytest.fixture
def ohlc_df() -> pd.DataFrame:
    """Minimal OHLC DataFrame for indicator computation."""
    import numpy as np

    np.random.seed(42)
    dates = [date(2026, 1, 5) + timedelta(days=i) for i in range(120)]
    close = 10.0 + np.cumsum(np.random.randn(120) * 0.1)
    df = pd.DataFrame(
        {
            "code": "000001",
            "date": dates,
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": np.random.randint(100000, 1000000, 120),
            "amount": close * np.random.randint(100000, 1000000, 120),
        }
    )
    return df


class TestTechnicalAnalyzer:
    def test_registry_has_enabled_indicators(self):
        analyzer = TechnicalAnalyzer()
        assert len(analyzer.registered_names) > 0

    def test_compute_single_ma(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        result = analyzer.compute_single("ma", ohlc_df)
        assert "ma_5" in result.columns

    def test_compute_single_rsi(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        result = analyzer.compute_single("rsi", ohlc_df)
        col = f"rsi_{analyzer._registry['rsi'].compute(ohlc_df).name}"
        # RSI series is named rsi_14
        cols_before = set(ohlc_df.columns) | {"rsi_14"}
        assert set(result.columns) == cols_before

    def test_compute_single_macd(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        result = analyzer.compute_single("macd", ohlc_df)
        assert "macd_dif" in result.columns

    def test_compute_single_bollinger(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        result = analyzer.compute_single("bollinger", ohlc_df)
        assert "bb_upper" in result.columns

    def test_compute_all(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        result = analyzer.compute_all(ohlc_df)
        for col in ("ma_5", "rsi_14", "macd_dif", "bb_middle"):
            assert col in result.columns

    def test_compute_unknown_indicator(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        with pytest.raises(AnalysisError, match="not registered"):
            analyzer.compute_single("unknown", ohlc_df)

    def test_to_indicator_list(self, ohlc_df):
        analyzer = TechnicalAnalyzer()
        df = analyzer.compute_all(ohlc_df)
        indicators = analyzer.to_indicator_list(df)
        assert len(indicators) == len(df)
        assert isinstance(indicators[0].rsi_14, (float, type(None)))
