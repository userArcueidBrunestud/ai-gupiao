from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.ai.features import FeatureEngineer
from src.ai.sklearn_predictor import SklearnPredictor
from src.core.exceptions import ModelError


@pytest.fixture
def training_data():
    """Generate synthetic OHLCV data, build features, return X/y."""
    np.random.seed(42)
    n = 300
    close = 10.0 + np.cumsum(np.random.randn(n) * 0.15)
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
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
    fe = FeatureEngineer(horizon=5)
    return fe.build_features(df)


class TestSklearnPredictor:
    def test_train_and_predict(self, training_data):
        X, y = training_data
        split = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split], X.iloc[split:]
        y_train, y_test = y.iloc[:split], y.iloc[split:]

        predictor = SklearnPredictor()
        metrics = predictor.train(X_train, y_train)
        assert metrics["n_samples"] == len(X_train)
        assert metrics["n_features"] > 0
        assert "feature_importances" in metrics

        preds = predictor.predict(X_test)
        assert len(preds) == len(X_test)
        assert all(p in (0, 1, 2) for p in preds)

    def test_predict_proba(self, training_data):
        X, y = training_data
        split = int(len(X) * 0.8)
        X_train = X.iloc[:split]
        y_train = y.iloc[:split]

        predictor = SklearnPredictor()
        predictor.train(X_train, y_train)
        probs = predictor.predict_proba(X.iloc[split:])
        assert probs.shape[1] == predictor._model.n_classes_

    def test_predict_with_confidence(self, training_data):
        X, y = training_data
        X_train, y_train = X.iloc[:240], y.iloc[:240]

        predictor = SklearnPredictor()
        predictor.train(X_train, y_train)
        results = predictor.predict_with_confidence(X.iloc[-1:])
        assert len(results) == 1
        assert "label" in results[0]
        assert "confidence" in results[0]
        assert results[0]["label"] in ("up", "down", "flat")

    def test_save_and_load(self, training_data):
        X, y = training_data
        X_train, y_train = X.iloc[:240], y.iloc[:240]

        predictor = SklearnPredictor()
        predictor.train(X_train, y_train)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.joblib"
            predictor.save(str(path))
            assert path.exists()

            loaded = SklearnPredictor()
            loaded.load(str(path))
            assert loaded.feature_names == predictor.feature_names

            preds_orig = predictor.predict(X.iloc[-5:])
            preds_loaded = loaded.predict(X.iloc[-5:])
            assert np.array_equal(preds_orig, preds_loaded)

    def test_predict_before_train_raises(self):
        predictor = SklearnPredictor()
        with pytest.raises(ModelError, match="not trained"):
            predictor.predict(pd.DataFrame({"a": [1]}))
