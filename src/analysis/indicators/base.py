from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseIndicator(ABC):
    """Abstract base for a single technical indicator."""

    name: str = ""
    required_columns: list[str] = ["close"]

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the indicator values and return a named Series."""
        ...
