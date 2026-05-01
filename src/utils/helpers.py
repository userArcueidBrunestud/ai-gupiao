from __future__ import annotations

import re
from datetime import date, timedelta


def normalize_code(code: str) -> str:
    """Ensure stock code is a plain 6-digit string, stripping exchange prefixes."""
    code = code.strip().upper()
    code = re.sub(r"^(SH|SZ|BJ|sh|sz|bj)\.?", "", code)
    code = re.sub(r"\.(SH|SZ|BJ)$", "", code, flags=re.IGNORECASE)
    if not re.match(r"^\d{6}$", code):
        raise ValueError(f"Invalid stock code: {code}")
    return code


def determine_market(code: str) -> str:
    """Infer exchange market from stock code prefix."""
    code = normalize_code(code)
    if code.startswith(("60", "68")):
        return "sh"
    elif code.startswith(("00", "30")):
        return "sz"
    elif code.startswith(("8", "4")):
        return "bj"
    raise ValueError(f"Cannot determine market for code: {code}")


def format_code_akshare(code: str) -> str:
    """Convert stock code to akshare symbol format (e.g. 000001 -> sz000001)."""
    code = normalize_code(code)
    market = determine_market(code)
    return f"{market}{code}"


def date_range(start: str | date, end: str | date) -> list[date]:
    """Generate a list of dates from start to end (inclusive)."""
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def trading_days_since(target: date, n: int = 5) -> date:
    """Estimate a date N trading days before target (crude: skip weekends)."""
    result = target
    count = 0
    while count < n:
        result = result - timedelta(days=1)
        if result.weekday() < 5:
            count += 1
    return result
