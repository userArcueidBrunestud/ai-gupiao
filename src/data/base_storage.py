from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import pandas as pd

from src.core.models.stock import StockDaily
from src.core.models.technical import TechnicalIndicators


class BaseStorage(ABC):
    """Abstract interface for data persistence."""

    # --- Daily price data ---

    @abstractmethod
    def save_daily_data(self, data: list[StockDaily]) -> int:
        """Persist daily bars. Returns rows written (upsert semantics)."""
        ...

    @abstractmethod
    def get_daily_data(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[StockDaily]:
        """Query daily bars by stock code and optional date range."""
        ...

    @abstractmethod
    def get_latest_date(self, code: str) -> Optional[date]:
        """Return the latest data date for a stock (used for incremental updates)."""
        ...

    # --- Technical indicator data ---

    @abstractmethod
    def save_indicators(self, data: list[TechnicalIndicators]) -> int:
        ...

    @abstractmethod
    def get_indicators(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[TechnicalIndicators]:
        ...

    # --- Combined query ---

    @abstractmethod
    def get_merged_dataframe(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> pd.DataFrame:
        """LEFT JOIN daily_prices + technical_indicators, return wide DataFrame."""
        ...
