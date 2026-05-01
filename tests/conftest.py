from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from src.core.models.stock import StockBasic, StockDaily
from src.core.models.technical import TechnicalIndicators


# ================================================================
# Sample data fixtures
# ================================================================


@pytest.fixture
def sample_stock_basic() -> StockBasic:
    return StockBasic(code="000001", name="平安银行", market="sz")


@pytest.fixture
def sample_daily_bars() -> list[StockDaily]:
    base = date(2026, 1, 5)
    codes = ["000001", "000001"]
    data = []
    for i in range(20):
        data.append(
            StockDaily(
                code="000001",
                date=base + timedelta(days=i),
                open=10.0 + i * 0.1,
                high=10.5 + i * 0.1,
                low=9.8 + i * 0.1,
                close=10.2 + i * 0.1,
                volume=1000000 + i * 10000,
                amount=10200000.0 + i * 100000,
                turnover=0.5 + i * 0.01,
            )
        )
    return data


@pytest.fixture
def sample_indicators() -> list[TechnicalIndicators]:
    base = date(2026, 1, 5)
    return [
        TechnicalIndicators(
            code="000001",
            date=base + timedelta(days=i),
            ma_5=10.1,
            ma_10=9.9,
            rsi_14=55.0,
            macd_dif=0.15,
            macd_dea=0.10,
            macd_bar=0.05,
        )
        for i in range(20)
    ]


# ================================================================
# In-memory SQLite storage fixture
# ================================================================


@pytest.fixture
def temp_db() -> str:
    """Return a path for a temporary SQLite database file."""
    import tempfile

    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    import os

    os.close(fd)
    yield tmp_path
    # Clean up WAL / SHM if they exist
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(tmp_path) + suffix) if suffix else Path(tmp_path)
        try:
            p.unlink(missing_ok=True)
        except PermissionError:
            pass


@pytest.fixture
def storage(temp_db):
    """A SQLiteStorage backed by a temp file, with connection cleanup."""
    from src.data.sqlite_storage import SQLiteStorage

    s = SQLiteStorage(db_path=temp_db)
    yield s
    # Close the connection so the temp file can be cleaned up
    try:
        s._conn.close()
    except Exception:
        pass


# ================================================================
# Mock akshare fixture helpers
# ================================================================


@pytest.fixture
def mock_akshare_df():
    """Return a minimal DataFrame mimicking akshare's stock_zh_a_hist output."""
    import numpy as np
    import pandas as pd

    dates = pd.date_range("2026-01-05", periods=10, freq="B")
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": [10.0] * 10,
            "最高": [10.5] * 10,
            "最低": [9.8] * 10,
            "收盘": [10.2] * 10,
            "成交量": [1000000] * 10,
            "成交额": [10200000.0] * 10,
            "换手率": [0.5] * 10,
        }
    )
