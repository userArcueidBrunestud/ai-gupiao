from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

from config.settings import settings
from src.ai.base_predictor import BasePredictor
from src.core.exceptions import ModelError


class SklearnPredictor(BasePredictor):
    """Random Forest classifier predictor with sklearn backend."""

    _LABEL_MAP = {0: "down", 1: "flat", 2: "up"}
    _LABEL_MAP_INV = {"down": 0, "flat": 1, "up": 2}

    def __init__(self) -> None:
        self._model = RandomForestClassifier(
            n_estimators=settings.rf_n_estimators,
            max_depth=settings.rf_max_depth,
            random_state=42,
            class_weight="balanced",
            n_jobs=-1,
        )
        self._scaler = StandardScaler()
        self._trained = False
        self._feature_names: list[str] = []

    @property
    def model_name(self) -> str:
        return f"RandomForest(n={settings.rf_n_estimators}, d={settings.rf_max_depth})"

    @property
    def feature_names(self) -> list[str]:
        return self._feature_names

    # ------------------------------------------------------------------
    # Train / Predict
    # ------------------------------------------------------------------

    def train(self, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
        self._feature_names = list(X.columns)
        X_scaled = self._scaler.fit_transform(X)
        self._model.fit(X_scaled, y)
        self._trained = True
        logger.info(
            f"Model trained: {len(X)} samples, {X.shape[1]} features, "
            f"classes={list(self._model.classes_)}"
        )
        return {
            "n_samples": len(X),
            "n_features": X.shape[1],
            "n_classes": len(self._model.classes_),
            "feature_importances": dict(
                zip(self._feature_names, self._model.feature_importances_)
            ),
        }

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._check_trained()
        X_scaled = self._scaler.transform(X[self._feature_names])
        return self._model.predict(X_scaled)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        self._check_trained()
        X_scaled = self._scaler.transform(X[self._feature_names])
        return self._model.predict_proba(X_scaled)

    def predict_with_confidence(self, X: pd.DataFrame) -> list[dict[str, str | float]]:
        """Return list of {label, confidence} dicts for each sample."""
        probs = self.predict_proba(X)
        results = []
        for prob_vec in probs:
            idx = int(np.argmax(prob_vec))
            label = self._LABEL_MAP.get(self._model.classes_[idx], "flat")
            confidence = float(prob_vec[idx])
            results.append({"label": label, "confidence": confidence})
        return results

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        self._check_trained()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        bundle = {
            "model": self._model,
            "scaler": self._scaler,
            "feature_names": self._feature_names,
        }
        joblib.dump(bundle, path)
        logger.info(f"Model saved to {path}")

    def load(self, path: str) -> None:
        try:
            bundle = joblib.load(path)
        except Exception as e:
            raise ModelError(f"Failed to load model from {path}: {e}") from e
        self._model = bundle["model"]
        self._scaler = bundle["scaler"]
        self._feature_names = bundle["feature_names"]
        self._trained = True
        logger.info(f"Model loaded from {path} ({len(self._feature_names)} features)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_trained(self) -> None:
        if not self._trained:
            raise ModelError("Model is not trained yet.")
