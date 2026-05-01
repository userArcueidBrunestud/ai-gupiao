from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from src.core.models.stock import StockBasic, StockDaily, StockRealtime


class TestStockBasic:
    def test_valid_code(self):
        s = StockBasic(code="000001", name="平安银行", market="sz")
        assert s.code == "000001"

    def test_invalid_code_non_digit(self):
        with pytest.raises(ValidationError):
            StockBasic(code="abc001", name="Test", market="sh")

    def test_invalid_code_too_short(self):
        with pytest.raises(ValidationError):
            StockBasic(code="0001", name="Test", market="sh")

    def test_market_literal(self):
        with pytest.raises(ValidationError):
            StockBasic(code="000001", name="Test", market="nyse")  # type: ignore[arg-type]


class TestStockDaily:
    def test_valid_bar(self):
        bar = StockDaily(
            code="000001",
            date=date(2026, 1, 5),
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.2,
            volume=1000000,
            amount=10200000.0,
        )
        assert bar.code == "000001"

    def test_high_lt_low(self):
        with pytest.raises(ValidationError):
            StockDaily(
                code="000001",
                date=date(2026, 1, 5),
                open=10.0,
                high=9.5,
                low=10.0,
                close=9.8,
                volume=1000000,
                amount=10200000.0,
            )

    def test_close_out_of_range(self):
        with pytest.raises(ValidationError):
            StockDaily(
                code="000001",
                date=date(2026, 1, 5),
                open=10.0,
                high=10.5,
                low=9.8,
                close=11.0,  # > high
                volume=1000000,
                amount=10200000.0,
            )

    def test_negative_price(self):
        with pytest.raises(ValidationError):
            StockDaily(
                code="000001",
                date=date(2026, 1, 5),
                open=-10.0,
                high=10.5,
                low=9.8,
                close=10.2,
                volume=1000000,
                amount=10200000.0,
            )

    def test_optional_turnover(self):
        bar = StockDaily(
            code="000001",
            date=date(2026, 1, 5),
            open=10.0,
            high=10.5,
            low=9.8,
            close=10.2,
            volume=1000000,
            amount=10200000.0,
            turnover=None,
        )
        assert bar.turnover is None


class TestStockRealtime:
    def test_minimal(self):
        rt = StockRealtime(code="000001", name="平安银行", price=10.5)
        assert rt.price == 10.5
        assert rt.updated_at is not None
