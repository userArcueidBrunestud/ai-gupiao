from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class TechnicalIndicators(BaseModel):
    code: str
    date: date
    ma_5: Optional[float] = None
    ma_10: Optional[float] = None
    ma_20: Optional[float] = None
    ma_60: Optional[float] = None
    rsi_14: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    macd_bar: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
