"""Historical risk metrics computed from portfolio_snapshots time series.

Pure Python. No external dependencies. Uses 252 trading days for annualization.
"""

from __future__ import annotations

import math
from statistics import fmean

TRADING_DAYS_PER_YEAR = 252


def daily_returns(series: list[tuple[str, float]]) -> list[float]:
    """Simple daily returns r_t = nlv_t / nlv_{t-1} - 1.

    Skips any step where the prior nlv is <= 0 (no valid base).
    """
    returns: list[float] = []
    for i in range(1, len(series)):
        prev = series[i - 1][1]
        curr = series[i][1]
        if prev <= 0:
            continue
        returns.append(curr / prev - 1.0)
    return returns


def annualized_volatility(returns: list[float]) -> float:
    """Sample standard deviation scaled by sqrt(252)."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = fmean(returns)
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    return math.sqrt(var) * math.sqrt(TRADING_DAYS_PER_YEAR)


def max_drawdown(series: list[tuple[str, float]]) -> dict:
    """Largest peak-to-trough percentage decline in the NLV series.

    Returns a negative percentage (e.g. -25.0 = 25% drawdown).
    """
    if not series:
        return {"max_drawdown_pct": 0.0, "peak_date": None, "trough_date": None}

    running_peak_value = series[0][1]
    running_peak_date = series[0][0]
    worst_dd = 0.0
    worst_peak_date: str | None = None
    worst_trough_date: str | None = None

    for date, value in series:
        if value > running_peak_value:
            running_peak_value = value
            running_peak_date = date
            continue
        if running_peak_value <= 0:
            continue
        dd = value / running_peak_value - 1.0
        if dd < worst_dd:
            worst_dd = dd
            worst_peak_date = running_peak_date
            worst_trough_date = date

    return {
        "max_drawdown_pct": round(worst_dd * 100, 4),
        "peak_date": worst_peak_date,
        "trough_date": worst_trough_date,
    }


def historical_var(returns: list[float], confidence: float = 0.95) -> float:
    """Historical Value-at-Risk: the (1-confidence) quantile of returns.

    Returned as a negative number (loss). Example: -0.04 = 4% one-day loss
    at the chosen confidence level.
    """
    if len(returns) < 2:
        return 0.0
    sorted_returns = sorted(returns)
    tail_idx = int(len(sorted_returns) * (1.0 - confidence))
    tail_idx = min(tail_idx, len(sorted_returns) - 1)
    return round(sorted_returns[tail_idx], 6)


def historical_cvar(returns: list[float], confidence: float = 0.95) -> float:
    """Conditional VaR (a.k.a. Expected Shortfall): average loss in the worst tail."""
    if len(returns) < 2:
        return 0.0
    sorted_returns = sorted(returns)
    tail_size = max(1, int(len(sorted_returns) * (1.0 - confidence)))
    tail = sorted_returns[:tail_size]
    return round(sum(tail) / len(tail), 6)
