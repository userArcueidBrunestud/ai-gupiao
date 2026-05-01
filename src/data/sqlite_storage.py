from __future__ import annotations

import sqlite3
from datetime import date
from typing import Optional

import pandas as pd
from loguru import logger

from config.settings import settings
from src.core.exceptions import StorageError
from src.core.models.stock import StockDaily
from src.core.models.technical import TechnicalIndicators
from src.data.base_storage import BaseStorage

# ---------------------------------------------------------------------------
# DDL templates
# ---------------------------------------------------------------------------

DDL_DAILY_PRICES = """
CREATE TABLE IF NOT EXISTS daily_prices (
    code     TEXT    NOT NULL,
    date     TEXT    NOT NULL,
    open     REAL    NOT NULL,
    high     REAL    NOT NULL,
    low      REAL    NOT NULL,
    close    REAL    NOT NULL,
    volume   INTEGER NOT NULL DEFAULT 0,
    amount   REAL    NOT NULL DEFAULT 0,
    turnover REAL,
    PRIMARY KEY (code, date)
);
"""

DDL_ANALYSIS_CACHE = """
CREATE TABLE IF NOT EXISTS analysis_cache (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (code, date)
);
"""

DDL_TECHNICAL_INDICATORS = """
CREATE TABLE IF NOT EXISTS technical_indicators (
    code        TEXT NOT NULL,
    date        TEXT NOT NULL,
    ma_5        REAL,
    ma_10       REAL,
    ma_20       REAL,
    ma_60       REAL,
    rsi_14      REAL,
    macd_dif    REAL,
    macd_dea    REAL,
    macd_bar    REAL,
    bb_upper    REAL,
    bb_middle   REAL,
    bb_lower    REAL,
    PRIMARY KEY (code, date)
);
"""

# ---------------------------------------------------------------------------
# SQLite Storage
# ---------------------------------------------------------------------------


class SQLiteStorage(BaseStorage):
    """Local SQLite-based data persistence."""

    def __init__(self, db_path: str | None = None) -> None:
        db_path = db_path or str(settings.db_path)
        self._db_path = db_path

        # Ensure parent directory exists
        import os

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_tables()

    def _init_tables(self) -> None:
        try:
            self._conn.execute(DDL_DAILY_PRICES)
            self._conn.execute(DDL_TECHNICAL_INDICATORS)
            self._conn.execute(DDL_ANALYSIS_CACHE)
            self._conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to init tables: {e}") from e

    # ------------------------------------------------------------------
    # Daily prices
    # ------------------------------------------------------------------

    def save_daily_data(self, data: list[StockDaily]) -> int:
        if not data:
            return 0
        sql = """
        INSERT OR REPLACE INTO daily_prices
            (code, date, open, high, low, close, volume, amount, turnover)
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        rows = [
            (
                d.code,
                d.date.isoformat(),
                d.open,
                d.high,
                d.low,
                d.close,
                d.volume,
                d.amount,
                d.turnover,
            )
            for d in data
        ]
        try:
            with self._conn:
                self._conn.executemany(sql, rows)
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save daily data: {e}") from e
        logger.debug(f"Saved {len(rows)} daily bars")
        return len(rows)

    def get_daily_data(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[StockDaily]:
        sql = "SELECT code, date, open, high, low, close, volume, amount, turnover FROM daily_prices WHERE code = ?"
        params: list = [code]
        if start:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY date ASC"
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to query daily data: {e}") from e
        return [self._row_to_daily(r) for r in rows]

    def get_latest_date(self, code: str) -> Optional[date]:
        sql = "SELECT MAX(date) FROM daily_prices WHERE code = ?"
        try:
            row = self._conn.execute(sql, (code,)).fetchone()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to query latest date: {e}") from e
        if row and row[0]:
            return date.fromisoformat(row[0])
        return None

    # ------------------------------------------------------------------
    # Technical indicators
    # ------------------------------------------------------------------

    def save_indicators(self, data: list[TechnicalIndicators]) -> int:
        if not data:
            return 0
        sql = """
        INSERT OR REPLACE INTO technical_indicators
            (code, date, ma_5, ma_10, ma_20, ma_60,
             rsi_14, macd_dif, macd_dea, macd_bar,
             bb_upper, bb_middle, bb_lower)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        rows = [
            (
                d.code,
                d.date.isoformat(),
                d.ma_5,
                d.ma_10,
                d.ma_20,
                d.ma_60,
                d.rsi_14,
                d.macd_dif,
                d.macd_dea,
                d.macd_bar,
                d.bb_upper,
                d.bb_middle,
                d.bb_lower,
            )
            for d in data
        ]
        try:
            with self._conn:
                self._conn.executemany(sql, rows)
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save indicators: {e}") from e
        logger.debug(f"Saved {len(rows)} indicator rows")
        return len(rows)

    def get_indicators(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> list[TechnicalIndicators]:
        sql = (
            "SELECT code, date, ma_5, ma_10, ma_20, ma_60, "
            "rsi_14, macd_dif, macd_dea, macd_bar, "
            "bb_upper, bb_middle, bb_lower "
            "FROM technical_indicators WHERE code = ?"
        )
        params: list = [code]
        if start:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY date ASC"
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to query indicators: {e}") from e
        return [self._row_to_indicators(r) for r in rows]

    # ------------------------------------------------------------------
    # Combined query
    # ------------------------------------------------------------------

    def get_merged_dataframe(
        self, code: str, start: Optional[date] = None, end: Optional[date] = None
    ) -> pd.DataFrame:
        sql = """
        SELECT
            d.code, d.date,
            d.open, d.high, d.low, d.close, d.volume, d.amount, d.turnover,
            t.ma_5, t.ma_10, t.ma_20, t.ma_60,
            t.rsi_14, t.macd_dif, t.macd_dea, t.macd_bar,
            t.bb_upper, t.bb_middle, t.bb_lower
        FROM daily_prices d
        LEFT JOIN technical_indicators t ON d.code = t.code AND d.date = t.date
        WHERE d.code = ?
        """
        params: list = [code]
        if start:
            sql += " AND d.date >= ?"
            params.append(start.isoformat())
        if end:
            sql += " AND d.date <= ?"
            params.append(end.isoformat())
        sql += " ORDER BY d.date ASC"
        try:
            return pd.read_sql_query(sql, self._conn, params=params)
        except (sqlite3.Error, pd.errors.DatabaseError) as e:
            raise StorageError(f"Failed merged query: {e}") from e

    # ------------------------------------------------------------------
    # Analysis result cache
    # ------------------------------------------------------------------

    def get_cached_result(self, code: str, cache_date: date) -> Optional[dict]:
        """Return cached analysis result for (code, date), or None."""
        try:
            row = self._conn.execute(
                "SELECT result_json FROM analysis_cache WHERE code=? AND date=?",
                (code, cache_date.isoformat()),
            ).fetchone()
            if row:
                import json
                return json.loads(row[0])
        except (sqlite3.Error, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read cache for {code}: {e}")
        return None

    def set_cached_result(self, code: str, cache_date: date, result: dict) -> None:
        """Persist analysis result for (code, date)."""
        import json
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO analysis_cache(code, date, result_json) VALUES(?,?,?)",
                (code, cache_date.isoformat(), json.dumps(result, ensure_ascii=False)),
            )
            self._conn.commit()
            logger.debug(f"Cached result for {code} on {cache_date}")
        except sqlite3.Error as e:
            logger.warning(f"Failed to cache result for {code}: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_daily(row: tuple) -> StockDaily:
        return StockDaily(
            code=row[0],
            date=date.fromisoformat(row[1]),
            open=row[2],
            high=row[3],
            low=row[4],
            close=row[5],
            volume=row[6],
            amount=row[7],
            turnover=row[8],
        )

    @staticmethod
    def _row_to_indicators(row: tuple) -> TechnicalIndicators:
        return TechnicalIndicators(
            code=row[0],
            date=date.fromisoformat(row[1]),
            ma_5=row[2],
            ma_10=row[3],
            ma_20=row[4],
            ma_60=row[5],
            rsi_14=row[6],
            macd_dif=row[7],
            macd_dea=row[8],
            macd_bar=row[9],
            bb_upper=row[10],
            bb_middle=row[11],
            bb_lower=row[12],
        )
