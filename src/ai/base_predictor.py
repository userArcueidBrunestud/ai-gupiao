from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd


class BasePredictor(ABC):
    """Abstract interface for ML prediction models."""

    @abstractmethod
    def train(self, X: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
        """Train the model. Returns training metrics."""
        ...

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return predicted class labels."""
        ...

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return predicted class probabilities."""
        ...

    @abstractmethod
    def save(self, path: str) -> None:
        """Persist the model to disk."""
        ...

    @abstractmethod
    def load(self, path: str) -> None:
        """Load the model from disk."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier."""
        ...
