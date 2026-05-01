from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.core.exceptions import DataFetchError
from src.data.akshare_fetcher import AkshareFetcher


class TestAkshareFetcher:
    def test_fetch_daily_data_returns_list(self, mock_akshare_df):
        with patch("src.data.akshare_fetcher.ak.stock_zh_a_hist", return_value=mock_akshare_df):
            with patch("src.data.akshare_fetcher.time.sleep", return_value=None):
                fetcher = AkshareFetcher()
                result = fetcher.fetch_daily_data("000001", "2026-01-01", "2026-01-31")
        assert len(result) == 10
        assert all(r.code == "000001" for r in result)
        assert result[0].open == 10.0

    def test_fetch_daily_data_empty(self):
        with patch("src.data.akshare_fetcher.ak.stock_zh_a_hist", return_value=None):
            with patch("src.data.akshare_fetcher.time.sleep", return_value=None):
                fetcher = AkshareFetcher()
                result = fetcher.fetch_daily_data("000001", "2026-01-01", "2026-01-31")
        assert result == []

    def test_fetch_daily_data_raises_on_error(self):
        with patch(
            "src.data.akshare_fetcher.ak.stock_zh_a_hist",
            side_effect=ConnectionError("timeout"),
        ):
            fetcher = AkshareFetcher()
            with pytest.raises(DataFetchError, match="timeout"):
                fetcher.fetch_daily_data("000001", "2026-01-01", "2026-01-31")

    def test_source_name(self):
        fetcher = AkshareFetcher()
        assert fetcher.source_name == "akshare"

    def test_fetch_stock_list(self):
        mock_spot = pd.DataFrame(
            {
                "代码": ["000001", "600000", "000002"],
                "名称": ["平安银行", "浦发银行", "万科A"],
            }
        )
        with patch("src.data.akshare_fetcher.ak.stock_zh_a_spot_em", return_value=mock_spot):
            fetcher = AkshareFetcher()
            result = fetcher.fetch_stock_list()
        assert len(result) == 3
        assert result[0].code == "000001"
        assert result[0].name == "平安银行"
        assert result[0].market == "sz"
        assert result[1].market == "sh"
