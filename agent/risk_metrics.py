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


def sharpe_ratio(returns: list[float], risk_free_annual: float = 0.0) -> float:
    """Annualized Sharpe = (mean_daily - rf_daily) / std_daily * sqrt(252)."""
    if len(returns) < 2:
        return 0.0
    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = [r - rf_daily for r in returns]
    mean = fmean(excess)
    n = len(excess)
    var = sum((r - mean) ** 2 for r in excess) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return round(mean / std * math.sqrt(TRADING_DAYS_PER_YEAR), 4)


def sortino_ratio(returns: list[float], risk_free_annual: float = 0.0) -> float:
    """Annualized Sortino = (mean - rf) / downside_std * sqrt(252).

    downside_std uses only negative excess returns.
    """
    if len(returns) < 2:
        return 0.0
    rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
    excess = [r - rf_daily for r in returns]
    downside = [r for r in excess if r < 0]
    if not downside:
        return 0.0
    mean = fmean(excess)
    dd_var = sum(r * r for r in downside) / len(downside)
    dd_std = math.sqrt(dd_var)
    if dd_std == 0:
        return 0.0
    return round(mean / dd_std * math.sqrt(TRADING_DAYS_PER_YEAR), 4)


def compute_history_metrics(
    series: list[tuple[str, float]],
    risk_free_annual: float = 0.0,
    confidence: float = 0.95,
) -> dict:
    """One-shot aggregator returning every historical risk metric.

    Input: ascending [(date, nlv)] pairs (the shape returned by
    storage.portfolio_store.get_net_liquidation_series).
    """
    if len(series) < 2:
        return {"error": "需要至少 2 个快照才能计算历史风险指标"}

    returns = daily_returns(series)
    if len(returns) < 2:
        return {"error": "有效收益样本不足"}

    return {
        "sample_size": len(series),
        "window_days": len(returns),
        "start_date": series[0][0],
        "end_date": series[-1][0],
        "start_nlv": round(series[0][1], 2),
        "end_nlv": round(series[-1][1], 2),
        "total_return_pct": round((series[-1][1] / series[0][1] - 1.0) * 100, 2),
        "annualized_volatility": round(annualized_volatility(returns), 4),
        "max_drawdown": max_drawdown(series),
        "var_95": historical_var(returns, confidence=confidence),
        "cvar_95": historical_cvar(returns, confidence=confidence),
        "sharpe": sharpe_ratio(returns, risk_free_annual=risk_free_annual),
        "sortino": sortino_ratio(returns, risk_free_annual=risk_free_annual),
    }
