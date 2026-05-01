from __future__ import annotations

import time
from datetime import date, datetime
from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger

from config.settings import settings
from src.core.exceptions import DataFetchError
from src.core.models.stock import StockBasic, StockDaily
from src.data.base_fetcher import BaseFetcher
from src.utils.helpers import determine_market, normalize_code


def _apply_eastmoney_patch() -> None:
    """Apply NID authorization patch for eastmoney endpoints if enabled."""
    if not settings.enable_eastmoney_patch:
        return
    try:
        from patch.eastmoney_patch import eastmoney_patch as _patch
        _patch()
        logger.info("Eastmoney patch applied")
    except ImportError:
        logger.warning("patch.eastmoney_patch not available")
    except Exception as e:
        logger.warning(f"Failed to apply eastmoney patch: {e}")


_apply_eastmoney_patch()


class AkshareFetcher(BaseFetcher):
    """A-share data fetcher powered by akshare."""

    @property
    def source_name(self) -> str:
        return "akshare"

    def fetch_stock_list(self) -> list[StockDaily]:
        """Fetch the full list of A-share stocks from东方财富."""
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as e:
            raise DataFetchError(self.source_name, str(e)) from e

        results: list[StockBasic] = []
        for _, row in df.iterrows():
            code = str(row["代码"]).strip()
            name = str(row["名称"]).strip()
            if not code or len(code) != 6:
                continue
            try:
                market = determine_market(code)
            except (KeyError, ValueError):
                continue
            results.append(StockBasic(code=code, name=name, market=market))

        logger.info(f"Fetched {len(results)} stocks from akshare")
        return results

    def fetch_daily_data(
        self, code: str, start_date: str, end_date: str
    ) -> list[StockDaily]:
        """Fetch daily K-line (前复权) for a single stock."""
        code = normalize_code(code)
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="qfq",
            )
        except Exception as e:
            raise DataFetchError(
                self.source_name, f"code={code}: {e}"
            ) from e

        if df is None or df.empty:
            logger.warning(f"No data returned for {code} [{start_date}..{end_date}]")
            return []

        results: list[StockDaily] = []
        for _, row in df.iterrows():
            try:
                results.append(self._row_to_daily(code, row))
            except (ValueError, KeyError) as e:
                logger.debug(f"Skipping row for {code}: {e}")
                continue

        logger.info(f"Fetched {len(results)} daily bars for {code}")
        time.sleep(settings.fetch_batch_delay)
        return results

    def fetch_realtime(self, code: str) -> StockDaily:
        """Fetch real-time quote for a single stock (via spot batch + filter)."""
        code = normalize_code(code)
        try:
            df = ak.stock_zh_a_spot_em()
        except Exception as e:
            raise DataFetchError(self.source_name, f"realtime: {e}") from e

        row = df[df["代码"] == code]
        if row.empty:
            raise DataFetchError(
                self.source_name, f"code {code} not found in realtime data"
            )
        return self._row_to_daily(code, row.iloc[0])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(val) -> date:
        if isinstance(val, date):
            return val
        if isinstance(val, datetime):
            return val.date()
        raw = str(val).strip()
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: {raw}")

    @staticmethod
    def _to_optional_float(val) -> Optional[float]:
        if pd.isna(val):
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(val) -> int:
        if pd.isna(val):
            return 0
        return int(val)

    def _row_to_daily(self, code: str, row) -> StockDaily:
        return StockDaily(
            code=code,
            date=self._parse_date(row["日期"]),
            open=float(row["开盘"]),
            high=float(row["最高"]),
            low=float(row["最低"]),
            close=float(row["收盘"]),
            volume=self._to_int(row.get("成交量")),
            amount=float(row.get("成交额", 0)),
            turnover=self._to_optional_float(row.get("换手率")),
        )
