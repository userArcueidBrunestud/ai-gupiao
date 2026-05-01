from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class StockBasic(BaseModel):
    code: str = Field(..., description="6-digit stock code, e.g. 000001")
    name: str = Field(..., description="Stock name")
    market: Literal["sh", "sz", "bj"] = Field(..., description="Exchange")

    @field_validator("code")
    @classmethod
    def code_must_be_6_digits(cls, v: str) -> str:
        if not re.match(r"^\d{6}$", v):
            raise ValueError(f"code must be 6 digits, got: {v}")
        return v


class StockDaily(BaseModel):
    code: str
    date: date
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    volume: int = Field(ge=0)
    amount: float = Field(ge=0)
    turnover: Optional[float] = Field(default=None, ge=0)

    @field_validator("high")
    @classmethod
    def high_ge_low(cls, v: float, info) -> float:
        low = info.data.get("low")
        if low is not None and v < low:
            raise ValueError(f"high ({v}) must be >= low ({low})")
        return v

    @field_validator("close")
    @classmethod
    def close_between_hl(cls, v: float, info) -> float:
        high = info.data.get("high")
        low = info.data.get("low")
        if high is not None and low is not None and not (low <= v <= high):
            raise ValueError(f"close ({v}) must be between low ({low}) and high ({high})")
        return v


class StockRealtime(BaseModel):
    code: str
    name: str
    price: float = Field(ge=0)
    change_pct: Optional[float] = None
    change_amount: Optional[float] = None
    volume: Optional[int] = Field(default=None, ge=0)
    amount: Optional[float] = Field(default=None, ge=0)
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    pre_close: Optional[float] = None
    updated_at: datetime = Field(default_factory=datetime.now)
