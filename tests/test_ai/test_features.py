from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.ai.features import FeatureEngineer


@pytest.fixture
def merged_df() -> pd.DataFrame:
    np.random.seed(42)
    n = 200
    close = 10.0 + np.cumsum(np.random.randn(n) * 0.15)
    dates = [date(2026, 1, 5) + timedelta(days=i) for i in range(n)]
    df = pd.DataFrame(
        {
            "code": "000001",
            "date": dates,
            "open": close - 0.05,
            "high": close + 0.1,
            "low": close - 0.1,
            "close": close,
            "volume": np.random.randint(100000, 2000000, n).astype(float),
            "amount": close * 1000000,
            "turnover": np.random.uniform(0.3, 2.0, n),
            "ma_5": pd.Series(close).rolling(5).mean(),
            "ma_10": pd.Series(close).rolling(10).mean(),
            "ma_20": pd.Series(close).rolling(20).mean(),
            "ma_60": pd.Series(close).rolling(60).mean(),
            "rsi_14": np.random.uniform(30, 70, n),
            "macd_dif": np.random.randn(n) * 0.1,
            "macd_dea": np.random.randn(n) * 0.08,
            "macd_bar": np.random.randn(n) * 0.05,
            "bb_upper": close + 0.5,
            "bb_middle": close,
            "bb_lower": close - 0.5,
        }
    )
    return df


class TestFeatureEngineer:
    def test_build_features_shape(self, merged_df):
        fe = FeatureEngineer(horizon=5)
        X, y = fe.build_features(merged_df)
        assert X.shape[0] > 0
        assert len(y) == X.shape[0]
        assert y.nunique() <= 3

    def test_labels_are_valid(self, merged_df):
        fe = FeatureEngineer(horizon=5)
        X, y = fe.build_features(merged_df)
        assert y.isin([0, 1, 2]).all()

    def test_no_nan_in_features(self, merged_df):
        fe = FeatureEngineer(horizon=5)
        X, y = fe.build_features(merged_df)
        assert not X.isna().any().any()

    def test_horizon_custom(self, merged_df):
        fe = FeatureEngineer(horizon=10)
        X, y = fe.build_features(merged_df)
        assert X.shape[0] > 0
