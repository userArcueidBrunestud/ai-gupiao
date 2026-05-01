from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from config.settings import settings
from src.core.exceptions import FeatureError


class FeatureEngineer:
    """Construct ML feature matrix and labels from OHLCV + indicator data."""

    _LABEL_MAP = {"down": 0, "flat": 1, "up": 2}

    def __init__(self, horizon: int | None = None) -> None:
        self.horizon = horizon or settings.prediction_horizon
        self._lag_periods = [1, 2, 3, 5, 10]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_features(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
        """
        Build feature matrix X and label vector y from merged OHLCV+indicator DataFrame.

        Returns (X, y) where y contains 0/1/2 for down/flat/up.
        """
        df = df.copy()
        df = self._add_price_features(df)
        df = self._add_volume_features(df)
        df = self._add_lag_features(df)
        df = self._add_rolling_features(df)
        y = self._build_labels(df)
        # Drop non-feature columns
        exclude = {"code", "date"}
        feature_cols = [c for c in df.columns if c not in exclude and not c.startswith("label_")]
        X = df[feature_cols].copy()
        # Drop rows where y is NaN (last horizon days)
        valid_mask = y.notna()
        X = X.loc[valid_mask]
        y = y.loc[valid_mask]
        # Fill remaining NaN in features
        X = X.ffill().bfill().fillna(0.0)
        logger.info(f"Built features: {X.shape[0]} samples, {X.shape[1]} features")
        return X, y

    # ------------------------------------------------------------------
    # Feature blocks
    # ------------------------------------------------------------------

    def _add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        close = df["close"]
        df["returns_1d"] = close.pct_change()
        df["returns_5d"] = close.pct_change(5)
        df["amplitude"] = (df["high"] - df["low"]) / df["close"]
        # Price position relative to MAs
        for col in ["ma_5", "ma_10", "ma_20", "ma_60"]:
            if col in df.columns:
                df[f"close_vs_{col}"] = close / df[col] - 1.0
        return df

    def _add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df["volume_ma_5"] = df["volume"].rolling(5).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma_5"].replace(0, np.nan)
        if "turnover" in df.columns:
            df["turnover_ma_5"] = df["turnover"].rolling(5).mean()
        return df

    def _add_lag_features(self, df: pd.DataFrame) -> pd.DataFrame:
        cols_to_lag = [
            "returns_1d",
            "rsi_14",
            "macd_dif",
            "macd_bar",
        ]
        for col in cols_to_lag:
            if col not in df.columns:
                continue
            for lag in self._lag_periods:
                df[f"{col}_lag{lag}"] = df[col].shift(lag)
        return df

    def _add_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rolling mean/std of returns."""
        for window in [5, 10, 20]:
            if "returns_1d" in df.columns:
                df[f"returns_roll_mean_{window}"] = (
                    df["returns_1d"].rolling(window).mean()
                )
                df[f"returns_roll_std_{window}"] = (
                    df["returns_1d"].rolling(window).std()
                )
        return df

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def _build_labels(self, df: pd.DataFrame) -> pd.Series:
        """Future N-day return direction: >2% up, <-2% down, else flat."""
        future_close = df["close"].shift(-self.horizon)
        future_return = future_close / df["close"] - 1.0
        labels = pd.Series(index=df.index, dtype="int64")
        labels[future_return > 0.02] = self._LABEL_MAP["up"]
        labels[future_return < -0.02] = self._LABEL_MAP["down"]
        labels[(future_return >= -0.02) & (future_return <= 0.02)] = self._LABEL_MAP["flat"]
        labels.name = "label"
        return labels

    @staticmethod
    def label_names() -> dict:
        return {0: "down", 1: "flat", 2: "up"}
