from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class BacktestResult:
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    n_trades: int


def evaluate_model(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray,
    label_names: dict[int, str] | None = None,
) -> dict:
    """Compute accuracy, precision/recall/f1 per class."""
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
    )

    accuracy = float(accuracy_score(y_true, y_pred))
    report = classification_report(
        y_true,
        y_pred,
        target_names=[label_names.get(i, str(i)) for i in sorted(set(y_true))],
        output_dict=True,
        zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred).tolist()

    logger.info(f"Model accuracy: {accuracy:.4f}")
    return {
        "accuracy": accuracy,
        "classification_report": report,
        "confusion_matrix": cm,
    }


def run_backtest(
    prices: pd.Series,
    predictions: np.ndarray,
    horizon: int = 5,
) -> BacktestResult:
    """
    Simple event-driven backtest.

    For each 'up' prediction, simulate buying and holding for `horizon` days.
    """
    holdings = np.zeros(len(prices))
    position = False
    entry_idx = 0

    for i in range(len(prices) - horizon):
        if predictions[i] == 2 and not position:  # 'up'
            entry_idx = i
            position = True
            holdings[i : i + horizon] = 1
        elif position and i >= entry_idx + horizon:
            position = False

    returns = prices.pct_change().fillna(0.0)
    strategy_returns = returns * holdings[:-1]  # shift to avoid look-ahead
    cumulative = (1.0 + strategy_returns).cumprod()

    total_return = float(cumulative.iloc[-1] - 1.0) if len(cumulative) > 0 else 0.0
    n_days = len(prices)
    annual_return = float((1.0 + total_return) ** (252.0 / n_days) - 1.0) if n_days > 0 else 0.0
    sharpe = (
        float(strategy_returns.mean() / strategy_returns.std() * np.sqrt(252))
        if strategy_returns.std() > 0
        else 0.0
    )
    drawdown = (cumulative / cumulative.cummax() - 1.0).min()
    max_dd = float(drawdown) if not pd.isna(drawdown) else 0.0
    win_rate = float((strategy_returns > 0).mean()) if len(strategy_returns) > 0 else 0.0
    n_trades = int(np.sum(np.diff(holdings) == 1))

    result = BacktestResult(
        total_return=total_return,
        annual_return=annual_return,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        win_rate=win_rate,
        n_trades=n_trades,
    )
    logger.info(
        f"Backtest — return={total_return:.2%} "
        f"annual={annual_return:.2%} sharpe={sharpe:.2f} "
        f"maxDD={max_dd:.2%} win_rate={win_rate:.2%}"
    )
    return result
