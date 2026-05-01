# -*- coding: utf-8 -*-
"""L1 hard filter — apply strategy hard_filters to snapshot DataFrame."""

import logging
from dataclasses import replace

import pandas as pd

from alphasift.models import HardFilterConfig

logger = logging.getLogger(__name__)
_DAILY_FILTER_DEFAULTS = {
    "change_60d_min": None,
    "change_60d_max": None,
    "require_ma_bullish": False,
    "require_price_above_ma20": False,
    "signal_score_min": None,
    "macd_status_whitelist": None,
    "rsi_status_whitelist": None,
    "breakout_20d_pct_min": None,
    "breakout_20d_pct_max": None,
    "range_20d_pct_max": None,
    "volume_ratio_20d_min": None,
    "volume_ratio_20d_max": None,
    "body_pct_min": None,
    "body_pct_max": None,
    "pullback_to_ma20_pct_min": None,
    "pullback_to_ma20_pct_max": None,
    "consolidation_days_20d_min": None,
    "consolidation_days_20d_max": None,
}


class SnapshotFieldMissingError(ValueError):
    """Raised when a configured hard filter cannot be evaluated safely."""


def apply_hard_filters(df: pd.DataFrame, filters: HardFilterConfig) -> pd.DataFrame:
    """Filter snapshot DataFrame by hard conditions. Returns filtered copy."""
    result = df.copy()
    if result.empty:
        return result

    if filters.exclude_st:
        name_col = _find_col(result, ["name", "股票名称", "名称"])
        if not name_col:
            raise SnapshotFieldMissingError(
                "Missing required snapshot column for exclude_st filter: name"
            )
        result = result[~result[name_col].str.contains(r"ST|退", na=False)]

    # Numeric filters — each is optional
    _filter_min(result, ["amount", "成交额"], filters.amount_min)
    _filter_min(result, ["price", "最新价", "现价"], filters.price_min)
    _filter_max(result, ["price", "最新价", "现价"], filters.price_max)
    _filter_min(result, ["total_mv", "总市值"], filters.market_cap_min)
    _filter_max(result, ["total_mv", "总市值"], filters.market_cap_max)
    _filter_min(result, ["pe_ratio", "市盈率"], filters.pe_ttm_min)
    _filter_max(result, ["pe_ratio", "市盈率"], filters.pe_ttm_max)
    _filter_min(result, ["pb_ratio", "市净率"], filters.pb_min)
    _filter_max(result, ["pb_ratio", "市净率"], filters.pb_max)
    _filter_min(result, ["volume_ratio", "量比"], filters.volume_ratio_min)
    _filter_min(result, ["turnover_rate", "换手率"], filters.turnover_rate_min)
    _filter_min(result, ["change_pct", "涨跌幅"], filters.change_pct_min)
    _filter_max(result, ["change_pct", "涨跌幅"], filters.change_pct_max)

    _filter_min(result, ["change_60d"], filters.change_60d_min)
    _filter_max(result, ["change_60d"], filters.change_60d_max)
    _filter_bool_true(result, "ma_bullish", filters.require_ma_bullish)
    _filter_bool_true(result, "price_above_ma20", filters.require_price_above_ma20)
    _filter_min(result, ["signal_score"], filters.signal_score_min)
    _filter_in(result, "macd_status", filters.macd_status_whitelist)
    _filter_in(result, "rsi_status", filters.rsi_status_whitelist)
    _filter_min(result, ["breakout_20d_pct"], filters.breakout_20d_pct_min)
    _filter_max(result, ["breakout_20d_pct"], filters.breakout_20d_pct_max)
    _filter_max(result, ["range_20d_pct"], filters.range_20d_pct_max)
    _filter_min(result, ["volume_ratio_20d"], filters.volume_ratio_20d_min)
    _filter_max(result, ["volume_ratio_20d"], filters.volume_ratio_20d_max)
    _filter_min(result, ["body_pct"], filters.body_pct_min)
    _filter_max(result, ["body_pct"], filters.body_pct_max)
    _filter_min(result, ["pullback_to_ma20_pct"], filters.pullback_to_ma20_pct_min)
    _filter_max(result, ["pullback_to_ma20_pct"], filters.pullback_to_ma20_pct_max)
    _filter_min(result, ["consolidation_days_20d"], filters.consolidation_days_20d_min)
    _filter_max(result, ["consolidation_days_20d"], filters.consolidation_days_20d_max)

    return result


def requires_daily_features(filters: HardFilterConfig) -> bool:
    """Return whether a hard-filter config needs daily K-line features."""
    return any([
        filters.change_60d_min is not None,
        filters.change_60d_max is not None,
        filters.require_ma_bullish,
        filters.require_price_above_ma20,
        filters.signal_score_min is not None,
        bool(filters.macd_status_whitelist),
        bool(filters.rsi_status_whitelist),
        filters.breakout_20d_pct_min is not None,
        filters.breakout_20d_pct_max is not None,
        filters.range_20d_pct_max is not None,
        filters.volume_ratio_20d_min is not None,
        filters.volume_ratio_20d_max is not None,
        filters.body_pct_min is not None,
        filters.body_pct_max is not None,
        filters.pullback_to_ma20_pct_min is not None,
        filters.pullback_to_ma20_pct_max is not None,
        filters.consolidation_days_20d_min is not None,
        filters.consolidation_days_20d_max is not None,
    ])


def without_daily_filters(filters: HardFilterConfig) -> HardFilterConfig:
    """Return a copy with daily K-line filters disabled."""
    return replace(filters, **_DAILY_FILTER_DEFAULTS)


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _filter_min(df: pd.DataFrame, col_names: list[str], value: float | None) -> None:
    if value is None:
        return
    if df.empty:
        return
    col = _find_col(df, col_names)
    if not col:
        raise SnapshotFieldMissingError(
            f"Missing required snapshot column for min filter {col_names}: "
            f"configured value={value}"
        )
    series = pd.to_numeric(df[col], errors="coerce")
    df.drop(df[(series < value) | series.isna()].index, inplace=True)


def _filter_max(df: pd.DataFrame, col_names: list[str], value: float | None) -> None:
    if value is None:
        return
    if df.empty:
        return
    col = _find_col(df, col_names)
    if not col:
        raise SnapshotFieldMissingError(
            f"Missing required snapshot column for max filter {col_names}: "
            f"configured value={value}"
        )
    series = pd.to_numeric(df[col], errors="coerce")
    df.drop(df[(series > value) | series.isna()].index, inplace=True)


def _filter_bool_true(df: pd.DataFrame, col_name: str, enabled: bool) -> None:
    if not enabled:
        return
    if df.empty:
        return
    if col_name not in df.columns:
        raise SnapshotFieldMissingError(
            f"Missing required daily feature column for bool filter: {col_name}"
        )
    df.drop(df[df[col_name] != True].index, inplace=True)  # noqa: E712


def _filter_in(df: pd.DataFrame, col_name: str, allowed: list[str] | None) -> None:
    if not allowed:
        return
    if df.empty:
        return
    if col_name not in df.columns:
        raise SnapshotFieldMissingError(
            f"Missing required daily feature column for whitelist filter: {col_name}"
        )
    allowed_set = {str(item) for item in allowed}
    df.drop(df[~df[col_name].astype(str).isin(allowed_set)].index, inplace=True)
