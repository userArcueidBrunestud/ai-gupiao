from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.models.stock import StockBasic, StockDaily


class BaseFetcher(ABC):
    """Abstract interface for stock data sources."""

    @abstractmethod
    def fetch_stock_list(self) -> list[StockBasic]:
        """Fetch the full list of A-share stocks."""
        ...

    @abstractmethod
    def fetch_daily_data(
        self, code: str, start_date: str, end_date: str
    ) -> list[StockDaily]:
        """Fetch daily K-line data for a single stock."""
        ...

    @abstractmethod
    def fetch_realtime(self, code: str) -> StockDaily:
        """Fetch real-time quote for a single stock."""
        ...

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identifier for this data source, used in logs and storage tags."""
        ...
