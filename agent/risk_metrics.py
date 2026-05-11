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
