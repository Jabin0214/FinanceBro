# FinanceBro V2 — Iteration 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the three highest-ROI items from the GitHub `financial-services` research: (1) historical risk metrics from snapshot data, (2) persistent trigger/cooldown abstraction for proactive jobs, (3) news-to-portfolio impact scoring.

**Architecture:** Three phases, each independently shippable.
- Phase 1 adds a new pure-Python module `agent/risk_metrics.py` that consumes `portfolio_snapshots` history and exposes a new orchestrator tool `get_risk_metrics`.
- Phase 2 introduces `bot/triggers.py` with a `Trigger` dataclass plus SQLite-backed dedup, replacing the in-memory `_sent_*_keys` sets in `bot/proactive.py`.
- Phase 3 adds `agent/news_impact.py` that takes news output + current positions and surfaces an impact ranking, wired into `news_monitor_job`.

**Tech Stack:** Python 3.11, SQLite (existing `storage/db.py`), pytest, python-telegram-bot (existing), Anthropic SDK (existing orchestrator).

**Inspirations referenced:**
- Phase 1: `JoelLewis/finance_skills` (core math + wealth-management/risk)
- Phase 2: `pavelsukhachev/hybrid-orchestrator` (Trigger/cooldown patterns)
- Phase 3: `IBM-Cloud/investment-insights-for-asset-managers` (news → portfolio shock)

---

## Pre-flight

- [ ] **Step 0.1: Confirm tests baseline is green**

Run: `pytest -q`
Expected: all existing tests pass before adding new code.

- [ ] **Step 0.2: Confirm we are on the worktree branch**

Run: `git status && git branch --show-current`
Expected: clean working tree on `claude/youthful-liskov-c525ed`.

---

## Phase 1 — Historical Risk Metrics

**Why:** Current `agent/risk_calculator.py` only computes a single-point snapshot (concentration, HHI, currency split). `portfolio_snapshots` already holds daily history, so we can derive volatility, max drawdown, VaR, CVaR, Sharpe, Sortino — the metrics every "wealth-management/risk" skill in the inspiration repos exposes.

**Deliverable:** New module + new orchestrator tool + tests.

### Task 1.1: Add snapshot history fetcher

**Files:**
- Modify: `storage/portfolio_store.py` (add one function)
- Test: `tests/storage/test_portfolio_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/storage/test_portfolio_store.py`:

```python
def test_get_net_liquidation_series_returns_ordered_pairs(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))

    from storage.portfolio_store import (
        save_portfolio_report,
        get_net_liquidation_series,
    )

    user_id = 999
    base_report = {
        "report_date": "2026-05-01",
        "accounts": [{
            "account_id": "U1",
            "alias": "main",
            "base_currency": "USD",
            "summary": {"net_liquidation": 10000.0, "stock_value_base": 8000.0,
                        "cash_base": 2000.0, "total_unrealized_pnl_base": 0,
                        "total_cost_base": 8000.0, "total_unrealized_pnl_pct": 0},
            "positions": [],
            "cash": [],
        }],
    }
    save_portfolio_report(user_id, base_report)
    save_portfolio_report(user_id, {**base_report, "report_date": "2026-05-02",
        "accounts": [{**base_report["accounts"][0],
            "summary": {**base_report["accounts"][0]["summary"], "net_liquidation": 10500.0}}]})
    save_portfolio_report(user_id, {**base_report, "report_date": "2026-05-03",
        "accounts": [{**base_report["accounts"][0],
            "summary": {**base_report["accounts"][0]["summary"], "net_liquidation": 10200.0}}]})

    series = get_net_liquidation_series(user_id, days=30)
    assert series == [
        ("2026-05-01", 10000.0),
        ("2026-05-02", 10500.0),
        ("2026-05-03", 10200.0),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_portfolio_store.py::test_get_net_liquidation_series_returns_ordered_pairs -v`
Expected: FAIL with `ImportError: cannot import name 'get_net_liquidation_series'`.

- [ ] **Step 3: Implement the function**

Append to `storage/portfolio_store.py`:

```python
def get_net_liquidation_series(
    user_id: int,
    days: int = 90,
) -> list[tuple[str, float]]:
    """Return [(report_date, summed_net_liquidation)] ascending, last `days` only.

    Sums across multiple accounts on the same date so the series represents the
    user's combined book.
    """
    with transaction() as conn:
        rows = conn.execute(
            """
            select report_date, sum(net_liquidation) as nlv
            from portfolio_snapshots
            where user_id = ?
            group by report_date
            order by report_date asc
            """,
            (user_id,),
        ).fetchall()
    pairs = [(r["report_date"], float(r["nlv"])) for r in rows]
    return pairs[-days:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_portfolio_store.py::test_get_net_liquidation_series_returns_ordered_pairs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add storage/portfolio_store.py tests/storage/test_portfolio_store.py
git commit -m "feat(storage): add get_net_liquidation_series for risk metrics"
```

---

### Task 1.2: Returns + volatility primitives

**Files:**
- Create: `agent/risk_metrics.py`
- Test: `tests/agent/test_risk_metrics.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agent/test_risk_metrics.py`:

```python
import math
import pytest

from agent.risk_metrics import daily_returns, annualized_volatility


def test_daily_returns_simple():
    series = [("d1", 100.0), ("d2", 110.0), ("d3", 99.0)]
    out = daily_returns(series)
    assert out == pytest.approx([0.10, -0.10], rel=1e-6)


def test_daily_returns_skips_zero_or_negative_priors():
    series = [("d1", 0.0), ("d2", 100.0), ("d3", 110.0)]
    out = daily_returns(series)
    assert out == pytest.approx([0.10], rel=1e-6)


def test_annualized_volatility_252_trading_days():
    # constant 1% daily move → annualized = 0.01 * sqrt(252)
    returns = [0.01, -0.01, 0.01, -0.01, 0.01, -0.01]
    vol = annualized_volatility(returns)
    expected = math.sqrt(sum(r * r for r in returns) / (len(returns) - 1)) * math.sqrt(252)
    assert vol == pytest.approx(expected, rel=1e-6)


def test_annualized_volatility_requires_two_points():
    assert annualized_volatility([]) == 0.0
    assert annualized_volatility([0.01]) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.risk_metrics'`.

- [ ] **Step 3: Implement the module**

Create `agent/risk_metrics.py`:

```python
"""Historical risk metrics computed from portfolio_snapshots time series.

Pure Python. No external dependencies. Uses 252 trading days for annualization.
"""

from __future__ import annotations

import math
from statistics import fmean, pstdev

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add agent/risk_metrics.py tests/agent/test_risk_metrics.py
git commit -m "feat(risk): add daily_returns and annualized_volatility primitives"
```

---

### Task 1.3: Max drawdown

**Files:**
- Modify: `agent/risk_metrics.py`
- Test: `tests/agent/test_risk_metrics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/agent/test_risk_metrics.py`:

```python
from agent.risk_metrics import max_drawdown


def test_max_drawdown_classic_peak_trough():
    series = [("d1", 100.0), ("d2", 120.0), ("d3", 90.0), ("d4", 110.0)]
    result = max_drawdown(series)
    assert result["max_drawdown_pct"] == pytest.approx(-25.0, rel=1e-6)
    assert result["peak_date"] == "d2"
    assert result["trough_date"] == "d3"


def test_max_drawdown_monotonic_up_is_zero():
    series = [("d1", 100.0), ("d2", 110.0), ("d3", 120.0)]
    result = max_drawdown(series)
    assert result["max_drawdown_pct"] == 0.0


def test_max_drawdown_empty_returns_zero():
    result = max_drawdown([])
    assert result["max_drawdown_pct"] == 0.0
    assert result["peak_date"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: FAIL with `ImportError: cannot import name 'max_drawdown'`.

- [ ] **Step 3: Implement**

Append to `agent/risk_metrics.py`:

```python
def max_drawdown(series: list[tuple[str, float]]) -> dict:
    """Largest peak-to-trough percentage decline in the NLV series.

    Returns a negative percentage (e.g. -25.0 = 25% drawdown).
    """
    if not series:
        return {"max_drawdown_pct": 0.0, "peak_date": None, "trough_date": None}

    peak_value = series[0][1]
    peak_date = series[0][0]
    running_peak_value = peak_value
    running_peak_date = peak_date
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: PASS (7 tests total).

- [ ] **Step 5: Commit**

```bash
git add agent/risk_metrics.py tests/agent/test_risk_metrics.py
git commit -m "feat(risk): add max_drawdown"
```

---

### Task 1.4: Historical VaR + CVaR

**Files:**
- Modify: `agent/risk_metrics.py`
- Test: `tests/agent/test_risk_metrics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/agent/test_risk_metrics.py`:

```python
from agent.risk_metrics import historical_var, historical_cvar


def test_historical_var_95_picks_5th_percentile_loss():
    # 20 returns, sorted ascending; 5th percentile index = 1 (0-indexed)
    returns = [-0.10, -0.08, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0,
               0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.04, 0.05,
               0.05, 0.06, 0.07, 0.08]
    var95 = historical_var(returns, confidence=0.95)
    # Expected: the loss at the 5% worst tail = -0.08
    assert var95 == pytest.approx(-0.08, rel=1e-6)


def test_historical_var_returns_zero_when_insufficient_data():
    assert historical_var([], confidence=0.95) == 0.0
    assert historical_var([0.01], confidence=0.95) == 0.0


def test_historical_cvar_is_mean_of_tail():
    returns = [-0.10, -0.08, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0,
               0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.04, 0.05,
               0.05, 0.06, 0.07, 0.08]
    cvar95 = historical_cvar(returns, confidence=0.95)
    # Tail = the worst 5% = [-0.10]; with n=20 the floor is 1, so tail mean = -0.10
    assert cvar95 == pytest.approx(-0.10, rel=1e-6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: FAIL with `ImportError: cannot import name 'historical_var'`.

- [ ] **Step 3: Implement**

Append to `agent/risk_metrics.py`:

```python
def historical_var(returns: list[float], confidence: float = 0.95) -> float:
    """Historical Value-at-Risk: the (1-confidence) quantile of returns.

    Returned as a negative number (loss). Example: -0.04 = 4% one-day loss
    at the chosen confidence level.
    """
    if len(returns) < 2:
        return 0.0
    sorted_returns = sorted(returns)
    tail_size = max(1, int(len(sorted_returns) * (1.0 - confidence)))
    return round(sorted_returns[tail_size - 1], 6)


def historical_cvar(returns: list[float], confidence: float = 0.95) -> float:
    """Conditional VaR (a.k.a. Expected Shortfall): average loss in the worst tail."""
    if len(returns) < 2:
        return 0.0
    sorted_returns = sorted(returns)
    tail_size = max(1, int(len(sorted_returns) * (1.0 - confidence)))
    tail = sorted_returns[:tail_size]
    return round(sum(tail) / len(tail), 6)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: PASS (10 tests total).

- [ ] **Step 5: Commit**

```bash
git add agent/risk_metrics.py tests/agent/test_risk_metrics.py
git commit -m "feat(risk): add historical VaR and CVaR"
```

---

### Task 1.5: Sharpe + Sortino

**Files:**
- Modify: `agent/risk_metrics.py`
- Test: `tests/agent/test_risk_metrics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/agent/test_risk_metrics.py`:

```python
from agent.risk_metrics import sharpe_ratio, sortino_ratio


def test_sharpe_ratio_constant_positive_returns():
    # Constant 0.001 daily return, zero variance → division-safe degenerate case
    returns = [0.001] * 30
    assert sharpe_ratio(returns) == 0.0  # zero variance returns zero


def test_sharpe_ratio_basic_shape():
    returns = [0.01, -0.005, 0.015, -0.002, 0.008]
    sr = sharpe_ratio(returns, risk_free_annual=0.0)
    # Should be positive and finite
    assert sr > 0
    assert math.isfinite(sr)


def test_sortino_ratio_only_uses_downside():
    returns = [0.02, 0.02, 0.02, -0.01, -0.01]
    so = sortino_ratio(returns)
    assert so > 0
    assert math.isfinite(so)


def test_sortino_ratio_no_downside_returns_zero():
    returns = [0.01, 0.02, 0.03]
    assert sortino_ratio(returns) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: FAIL with `ImportError: cannot import name 'sharpe_ratio'`.

- [ ] **Step 3: Implement**

Append to `agent/risk_metrics.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: PASS (14 tests total).

- [ ] **Step 5: Commit**

```bash
git add agent/risk_metrics.py tests/agent/test_risk_metrics.py
git commit -m "feat(risk): add sharpe and sortino ratios"
```

---

### Task 1.6: Top-level `compute_history_metrics` aggregator

**Files:**
- Modify: `agent/risk_metrics.py`
- Test: `tests/agent/test_risk_metrics.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/agent/test_risk_metrics.py`:

```python
from agent.risk_metrics import compute_history_metrics


def test_compute_history_metrics_returns_full_payload():
    series = [
        ("2026-04-01", 10000.0),
        ("2026-04-02", 10100.0),
        ("2026-04-03",  9900.0),
        ("2026-04-04", 10050.0),
        ("2026-04-05",  9800.0),
        ("2026-04-06",  9950.0),
    ]
    out = compute_history_metrics(series)
    assert out["sample_size"] == 6
    assert out["window_days"] == 5  # 5 daily returns from 6 points
    assert "annualized_volatility" in out
    assert "max_drawdown" in out
    assert "var_95" in out
    assert "cvar_95" in out
    assert "sharpe" in out
    assert "sortino" in out
    assert out["start_date"] == "2026-04-01"
    assert out["end_date"] == "2026-04-06"


def test_compute_history_metrics_too_short_returns_error():
    out = compute_history_metrics([("2026-04-01", 10000.0)])
    assert "error" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: FAIL with `ImportError: cannot import name 'compute_history_metrics'`.

- [ ] **Step 3: Implement**

Append to `agent/risk_metrics.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_risk_metrics.py -v`
Expected: PASS (16 tests total).

- [ ] **Step 5: Commit**

```bash
git add agent/risk_metrics.py tests/agent/test_risk_metrics.py
git commit -m "feat(risk): add compute_history_metrics aggregator"
```

---

### Task 1.7: Orchestrator tool `get_risk_metrics`

**Files:**
- Create: `agent/tools/risk_metrics.py`
- Modify: `agent/tools/__init__.py`
- Test: `tests/agent/test_tools_risk_metrics.py`

Reference existing tool shape: `agent/tools/history.py` (39 lines) is the closest analog — read it before writing the new tool.

- [ ] **Step 1: Write the failing test**

Create `tests/agent/test_tools_risk_metrics.py`:

```python
from unittest.mock import patch

from agent.tools.risk_metrics import DEFINITION, execute


def test_definition_shape():
    assert DEFINITION["name"] == "get_risk_metrics"
    assert "description" in DEFINITION
    assert "input_schema" in DEFINITION


def test_execute_returns_formatted_text_on_success():
    series = [
        ("2026-04-01", 10000.0),
        ("2026-04-02", 10100.0),
        ("2026-04-03",  9900.0),
        ("2026-04-04", 10050.0),
    ]
    with patch("agent.tools.risk_metrics.current_user_id", return_value=42), \
         patch("agent.tools.risk_metrics.get_net_liquidation_series", return_value=series):
        out = execute({"days": 30})
    assert "波动" in out or "volatility" in out.lower()
    assert "最大回撤" in out or "drawdown" in out.lower()


def test_execute_handles_insufficient_data():
    with patch("agent.tools.risk_metrics.current_user_id", return_value=42), \
         patch("agent.tools.risk_metrics.get_net_liquidation_series", return_value=[]):
        out = execute({"days": 30})
    assert "不足" in out or "error" in out.lower()


def test_execute_missing_user_id():
    with patch("agent.tools.risk_metrics.current_user_id", return_value=None):
        out = execute({"days": 30})
    assert "用户" in out or "user" in out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_tools_risk_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.risk_metrics'`.

- [ ] **Step 3: Implement the tool**

Create `agent/tools/risk_metrics.py`:

```python
"""Orchestrator tool: historical risk metrics from snapshot series."""

from __future__ import annotations

from agent.risk_metrics import compute_history_metrics
from agent.tools._state import current_user_id
from storage.portfolio_store import get_net_liquidation_series

DEFINITION = {
    "name": "get_risk_metrics",
    "description": (
        "Compute historical risk metrics (annualized volatility, max drawdown, "
        "VaR 95%, CVaR 95%, Sharpe, Sortino) from the user's portfolio_snapshots "
        "history. Use when the user asks about portfolio risk over a window."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Lookback window in calendar days (max 365). Default 90.",
                "minimum": 7,
                "maximum": 365,
            },
        },
    },
}


def execute(tool_input: dict) -> str:
    user_id = current_user_id()
    if user_id is None:
        return "❌ 无法识别当前 Telegram 用户，无法读取历史快照。"

    days = int(tool_input.get("days") or 90)
    days = max(7, min(days, 365))

    series = get_net_liquidation_series(user_id, days=days)
    metrics = compute_history_metrics(series)

    if "error" in metrics:
        return f"⚠️ 历史风险指标无法计算：{metrics['error']}（窗口 {days} 天）"

    dd = metrics["max_drawdown"]
    return (
        f"📊 历史风险指标（{metrics['start_date']} → {metrics['end_date']}，"
        f"{metrics['window_days']} 个交易日样本）\n\n"
        f"• 累计收益：{metrics['total_return_pct']:.2f}%\n"
        f"• 年化波动率：{metrics['annualized_volatility'] * 100:.2f}%\n"
        f"• 最大回撤：{dd['max_drawdown_pct']:.2f}% "
        f"（{dd['peak_date']} → {dd['trough_date']}）\n"
        f"• 历史 VaR 95%：{metrics['var_95'] * 100:.2f}%\n"
        f"• 历史 CVaR 95%：{metrics['cvar_95'] * 100:.2f}%\n"
        f"• Sharpe：{metrics['sharpe']:.2f}\n"
        f"• Sortino：{metrics['sortino']:.2f}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_tools_risk_metrics.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Register the tool**

Edit `agent/tools/__init__.py`. Three changes:

Change the import line:

```python
from agent.tools import history, news, portfolio, report, risk, risk_metrics
```

Change the `_TOOLS` dict to:

```python
_TOOLS = {
    portfolio.DEFINITION["name"]:     portfolio.execute,
    history.DEFINITION["name"]:       history.execute,
    report.DEFINITION["name"]:        report.execute,
    news.DEFINITION["name"]:          news.execute,
    risk.DEFINITION["name"]:          risk.execute,
    risk_metrics.DEFINITION["name"]:  risk_metrics.execute,
}
```

Change the `TOOL_DEFINITIONS` list to:

```python
TOOL_DEFINITIONS = [
    portfolio.DEFINITION,
    history.DEFINITION,
    report.DEFINITION,
    news.DEFINITION,
    risk.DEFINITION,
    risk_metrics.DEFINITION,
]
```

- [ ] **Step 6: Run full test suite**

Run: `pytest -q`
Expected: all tests pass, including new risk_metrics tests.

- [ ] **Step 7: Commit**

```bash
git add agent/tools/risk_metrics.py agent/tools/__init__.py tests/agent/test_tools_risk_metrics.py
git commit -m "feat(tools): expose get_risk_metrics orchestrator tool"
```

---

### Task 1.8: Phase 1 verification

- [ ] **Step 1: Manual orchestrator smoke**

Start the bot locally (if env permits) and message it: `过去 30 天我的组合风险怎么样？`

Confirm orchestrator chooses `get_risk_metrics`, the response includes volatility / drawdown / VaR / Sharpe, and rendering survives Telegram HTML.

If no local env: skip this step and rely on the pytest matrix.

- [ ] **Step 2: Update README command table**

Modify `README.md` "如何新增 Orchestrator 工具" stays unchanged. In the "工具" line under "Architecture" section (lines 145-150), add:

```text
  +--> agent/tools/risk_metrics.py -> 历史风险指标
```

- [ ] **Step 3: Commit docs**

```bash
git add README.md
git commit -m "docs: mention get_risk_metrics tool"
```

---

## Phase 2 — Persistent Trigger Abstraction

**Why:** `bot/proactive.py` currently uses two in-memory sets (`_sent_alert_keys`, `_sent_news_keys`) for dedup. Both get wiped on every restart, so a Docker redeploy at 08:30 will re-send the same alert. The hybrid-orchestrator pattern (cooldown + max-fires-per-day, persisted) eliminates the bug and gives a single place to add future triggers (Risk Sentinel, Earnings Calendar) without copy-pasting.

**Deliverable:** New module `bot/triggers.py`, new SQLite table `trigger_fires`, `proactive.py` refactored to use it.

### Task 2.1: SQLite table for trigger fires

**Files:**
- Modify: `storage/db.py`
- Test: `tests/storage/test_db.py` (create if missing — confirm with `ls tests/storage/`)

- [ ] **Step 1: Write the failing test**

Create or append to `tests/storage/test_db.py`:

```python
import sqlite3


def test_trigger_fires_table_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))

    from storage.db import connect

    conn = connect()
    cur = conn.execute(
        "select name from sqlite_master where type='table' and name='trigger_fires'"
    )
    assert cur.fetchone() is not None

    cols = {r[1] for r in conn.execute("pragma table_info(trigger_fires)").fetchall()}
    assert {"id", "trigger_name", "user_id", "fingerprint", "fired_at"}.issubset(cols)
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/storage/test_db.py::test_trigger_fires_table_exists -v`
Expected: FAIL (table missing).

- [ ] **Step 3: Add schema**

In `storage/db.py`, inside `_init_schema`, append to the existing `executescript` block this DDL:

```sql
create table if not exists trigger_fires (
    id integer primary key autoincrement,
    trigger_name text not null,
    user_id integer not null,
    fingerprint text not null,
    fired_at text not null default current_timestamp
);

create index if not exists idx_trigger_fires_lookup
    on trigger_fires (trigger_name, user_id, fired_at desc);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/storage/test_db.py::test_trigger_fires_table_exists -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add storage/db.py tests/storage/test_db.py
git commit -m "feat(storage): add trigger_fires table for proactive dedup"
```

---

### Task 2.2: `Trigger` evaluator with cooldown + daily cap

**Files:**
- Create: `bot/triggers.py`
- Test: `tests/bot/test_triggers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_triggers.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))


def test_trigger_fires_once_then_cooldown_blocks():
    from bot.triggers import Trigger, should_fire, record_fire

    t = Trigger(name="alert.threshold", cooldown_seconds=3600, max_fires_per_day=5)
    fp = "abc"

    assert should_fire(t, user_id=1, fingerprint=fp) is True
    record_fire(t, user_id=1, fingerprint=fp)
    assert should_fire(t, user_id=1, fingerprint=fp) is False


def test_trigger_distinguishes_fingerprints():
    from bot.triggers import Trigger, should_fire, record_fire

    t = Trigger(name="alert.threshold", cooldown_seconds=3600, max_fires_per_day=5)
    record_fire(t, user_id=1, fingerprint="abc")
    assert should_fire(t, user_id=1, fingerprint="def") is True


def test_trigger_daily_cap_blocks_unique_fingerprints():
    from bot.triggers import Trigger, should_fire, record_fire

    t = Trigger(name="alert.threshold", cooldown_seconds=0, max_fires_per_day=2)
    record_fire(t, user_id=1, fingerprint="a")
    record_fire(t, user_id=1, fingerprint="b")
    assert should_fire(t, user_id=1, fingerprint="c") is False


def test_trigger_cooldown_expires(monkeypatch):
    from bot.triggers import Trigger, should_fire, record_fire
    import bot.triggers as triggers_mod

    t = Trigger(name="alert.threshold", cooldown_seconds=10, max_fires_per_day=99)
    record_fire(t, user_id=1, fingerprint="same")

    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    monkeypatch.setattr(triggers_mod, "_utcnow", lambda: future)
    assert should_fire(t, user_id=1, fingerprint="same") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bot/test_triggers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.triggers'`.

- [ ] **Step 3: Implement**

Create `bot/triggers.py`:

```python
"""Persistent trigger evaluator with cooldown and daily cap.

Pattern adapted from pavelsukhachev/hybrid-orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from storage.db import transaction


@dataclass(frozen=True)
class Trigger:
    name: str
    cooldown_seconds: int = 3600
    max_fires_per_day: int = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def should_fire(trigger: Trigger, user_id: int, fingerprint: str) -> bool:
    """Return True if this (trigger, user, fingerprint) is allowed to fire now."""
    now = _utcnow()
    with transaction() as conn:
        # Same fingerprint within cooldown blocks.
        row = conn.execute(
            """
            select fired_at from trigger_fires
            where trigger_name = ? and user_id = ? and fingerprint = ?
            order by id desc limit 1
            """,
            (trigger.name, user_id, fingerprint),
        ).fetchone()
        if row is not None:
            fired_at = datetime.fromisoformat(row["fired_at"]).replace(
                tzinfo=timezone.utc
            )
            age = (now - fired_at).total_seconds()
            if age < trigger.cooldown_seconds:
                return False

        # Daily cap across all fingerprints.
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = conn.execute(
            """
            select count(*) as n from trigger_fires
            where trigger_name = ? and user_id = ? and fired_at >= ?
            """,
            (trigger.name, user_id, today_start.isoformat(sep=" ", timespec="seconds")),
        ).fetchone()["n"]
        if count >= trigger.max_fires_per_day:
            return False

    return True


def record_fire(trigger: Trigger, user_id: int, fingerprint: str) -> None:
    """Persist a trigger fire. Call only after the side effect (Telegram send) succeeds."""
    now = _utcnow().isoformat(sep=" ", timespec="seconds")
    with transaction() as conn:
        conn.execute(
            """
            insert into trigger_fires (trigger_name, user_id, fingerprint, fired_at)
            values (?, ?, ?, ?)
            """,
            (trigger.name, user_id, fingerprint, now),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bot/test_triggers.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add bot/triggers.py tests/bot/test_triggers.py
git commit -m "feat(triggers): persistent cooldown + daily-cap evaluator"
```

---

### Task 2.3: Refactor `threshold_alert_job` to use triggers

**Files:**
- Modify: `bot/proactive.py`
- Test: `tests/bot/test_proactive.py` (create if missing — check with `ls tests/bot/`)

- [ ] **Step 1: Write the failing test**

Add to `tests/bot/test_proactive.py` (create if missing):

```python
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))


@pytest.mark.asyncio
async def test_threshold_alert_persists_dedup_across_calls(monkeypatch):
    """Second call within cooldown must not re-send the same alert."""
    monkeypatch.setattr("bot.proactive.PROACTIVE_ALERT_USER_ID", 42)

    report = {
        "report_date": "2026-05-10",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 10000, "stock_value_base": 9000,
                        "cash_base": 1000, "total_unrealized_pnl_base": -1000,
                        "total_cost_base": 10000, "total_unrealized_pnl_pct": -10.0},
            "positions": [{
                "symbol": "AAA", "description": "", "asset_category": "STK",
                "currency": "USD", "market_value_base": 9000,
                "unrealized_pnl_base": -1000, "unrealized_pnl_pct": -10.0,
                "cost_basis_base": 10000,
            }],
            "cash": [],
        }],
    }

    bot_mock = AsyncMock()
    context = type("Ctx", (), {"bot": bot_mock})()

    from bot import proactive

    with patch.object(proactive, "_fetch_and_save", return_value=report):
        await proactive.threshold_alert_job(context)
        await proactive.threshold_alert_job(context)

    assert bot_mock.send_message.await_count == 1
```

Ensure `pytest.ini` enables asyncio (check with `cat pytest.ini`). If `asyncio_mode = auto` is not set, the test uses `@pytest.mark.asyncio` — confirm `pytest-asyncio` is in `requirements.txt`; if not, install steps must be added.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bot/test_proactive.py -v`
Expected: FAIL — the current implementation has a `_sent_alert_keys: set[str]` module global that survives across calls within the same process, so the dedup happens to work in-process; but the assertion will still hold today. The real proof of breakage comes from cross-restart, which we cover after we strip the in-memory set in Step 3. For now, this single assertion is the regression guard once we delete the in-memory set.

If the test currently passes (it will), that's fine — the value of this test is that it MUST keep passing after we remove `_sent_alert_keys` in Step 3. The test is asserting persistent dedup; today's in-memory dedup happens to satisfy it, but the persistent version is what we want to lock in.

- [ ] **Step 3: Refactor `threshold_alert_job`**

In `bot/proactive.py`, replace the `_sent_alert_keys` usage in `threshold_alert_job` with:

```python
from bot.triggers import Trigger, record_fire, should_fire

_THRESHOLD_ALERT_TRIGGER = Trigger(
    name="alert.threshold",
    cooldown_seconds=12 * 3600,
    max_fires_per_day=3,
)
```

Then change the dedup block inside `threshold_alert_job`:

```python
        key = _fingerprint(user_id, report.get("report_date", ""), "\n".join(alerts))
        if not should_fire(_THRESHOLD_ALERT_TRIGGER, user_id=user_id, fingerprint=key):
            logger.info("threshold alert skipped: trigger dedup")
            return

        await _send(
            context,
            user_id,
            "<b>持仓阈值预警</b>\n\n" + "\n".join(f"🔴 {alert}" for alert in alerts),
        )
        record_fire(_THRESHOLD_ALERT_TRIGGER, user_id=user_id, fingerprint=key)
```

Remove the module-level `_sent_alert_keys: set[str] = set()` declaration and the `_sent_alert_keys.add(key)` line.

- [ ] **Step 4: Run tests**

Run: `pytest tests/bot/test_proactive.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/proactive.py tests/bot/test_proactive.py
git commit -m "refactor(proactive): use persistent Trigger for threshold alerts"
```

---

### Task 2.4: Refactor `news_monitor_job` to use triggers

**Files:**
- Modify: `bot/proactive.py`
- Test: `tests/bot/test_proactive.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/bot/test_proactive.py`:

```python
@pytest.mark.asyncio
async def test_news_monitor_dedup_persists(monkeypatch):
    monkeypatch.setattr("bot.proactive.PROACTIVE_NEWS_USER_ID", 42)

    report = {
        "report_date": "2026-05-10",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 10000, "stock_value_base": 9000,
                        "cash_base": 1000, "total_unrealized_pnl_base": 0,
                        "total_cost_base": 9000, "total_unrealized_pnl_pct": 0},
            "positions": [{
                "symbol": "AAA", "description": "", "asset_category": "STK",
                "currency": "USD", "market_value_base": 9000,
                "unrealized_pnl_base": 0, "unrealized_pnl_pct": 0,
                "cost_basis_base": 9000,
            }],
            "cash": [],
        }],
    }

    bot_mock = AsyncMock()
    context = type("Ctx", (), {"bot": bot_mock})()

    from bot import proactive

    with patch.object(proactive, "_fetch_and_save", return_value=report), \
         patch.object(proactive, "_get_news", return_value="AAA reports strong Q1"):
        await proactive.news_monitor_job(context)
        await proactive.news_monitor_job(context)

    # Dedup is persisted in SQLite; the fresh_db fixture proves nothing leaks
    # across tests, and the second call hitting the same DB must short-circuit.
    assert bot_mock.send_message.await_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bot/test_proactive.py::test_news_monitor_dedup_persists -v`
Expected: FAIL.

- [ ] **Step 3: Refactor `news_monitor_job`**

In `bot/proactive.py`, add:

```python
_NEWS_MONITOR_TRIGGER = Trigger(
    name="news.monitor",
    cooldown_seconds=4 * 3600,
    max_fires_per_day=4,
)
```

Replace the `_sent_news_keys` usage inside `news_monitor_job`:

```python
        key = _fingerprint(user_id, report.get("report_date", ""), digest[:500])
        if not should_fire(_NEWS_MONITOR_TRIGGER, user_id=user_id, fingerprint=key):
            logger.info("news monitor skipped: trigger dedup")
            return

        await _send(
            context,
            user_id,
            "<b>重大新闻 / 财报提醒</b>\n\n" + digest,
        )
        record_fire(_NEWS_MONITOR_TRIGGER, user_id=user_id, fingerprint=key)
```

Remove the module-level `_sent_news_keys: set[str] = set()` declaration and the `_sent_news_keys.add(key)` line.

- [ ] **Step 4: Run all tests**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add bot/proactive.py tests/bot/test_proactive.py
git commit -m "refactor(proactive): use persistent Trigger for news monitor"
```

---

### Task 2.5: Phase 2 verification

- [ ] **Step 1: Confirm in-memory sets are gone**

Run: `git grep -n '_sent_alert_keys\|_sent_news_keys' bot/`
Expected: no results.

- [ ] **Step 2: Run full suite**

Run: `pytest -q`
Expected: green.

- [ ] **Step 3: README update**

In `README.md`, in the "如何新增 scheduler job" section, add a note after step 4:

```text
   - 优先使用 `bot/triggers.Trigger` 做冷却 / 去重，状态进 SQLite，重启不丢
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: note bot.triggers as the dedup primitive for scheduler jobs"
```

---

## Phase 3 — News Impact Scoring

**Why:** News Agent currently returns a narrative digest. Inspired by IBM `investment-insights-for-asset-managers`, we score every news item by (a) which tickers it mentions, (b) those tickers' weights in the current portfolio, (c) a lightweight sentiment polarity proxy. Output ranks news by *portfolio impact*, not chronology. This converts News Agent from "information stream" to "decision input" — and is the exact upgrade the README's V2 roadmap implies for the Risk Sentinel.

**Deliverable:** New module `agent/news_impact.py`, integration in `news_monitor_job`.

### Task 3.1: Pure-function impact scorer

**Files:**
- Create: `agent/news_impact.py`
- Test: `tests/agent/test_news_impact.py`

**Design constraint:** Sentiment is intentionally a coarse keyword polarity, not an LLM call. The Grok narrative already supplies a richer summary; we just need a routable score for ranking. Future iterations can swap in an LLM scorer.

- [ ] **Step 1: Write the failing test**

Create `tests/agent/test_news_impact.py`:

```python
from agent.news_impact import (
    extract_mentioned_symbols,
    polarity_score,
    score_headline,
    rank_news_by_impact,
)


def test_extract_mentioned_symbols_uppercase_word_boundary():
    text = "AAPL beats earnings; TSLA misses; aapl rumor (lowercase ignored)"
    symbols = {"AAPL", "TSLA", "MSFT"}
    assert extract_mentioned_symbols(text, symbols) == {"AAPL", "TSLA"}


def test_extract_mentioned_symbols_handles_punctuation():
    text = "$NVDA up 5%, GOOG/L flat."
    symbols = {"NVDA", "GOOG", "GOOGL"}
    found = extract_mentioned_symbols(text, symbols)
    assert "NVDA" in found
    assert "GOOG" in found


def test_polarity_positive_keywords():
    assert polarity_score("beats earnings, raises guidance") > 0


def test_polarity_negative_keywords():
    assert polarity_score("misses earnings, downgrade, lawsuit") < 0


def test_polarity_neutral():
    assert polarity_score("reports quarterly results") == 0


def test_score_headline_combines_weight_and_polarity():
    weights = {"AAPL": 20.0, "TSLA": 5.0}
    score = score_headline(
        "AAPL beats earnings and raises guidance",
        symbols=set(weights),
        weights=weights,
    )
    # weight * polarity → positive, magnitude proportional to AAPL weight
    assert score["impact"] > 0
    assert score["symbols"] == ["AAPL"]
    assert score["polarity"] > 0


def test_score_headline_ignores_unweighted_mentions():
    weights = {"AAPL": 20.0}
    score = score_headline(
        "TSLA recall announced",
        symbols={"AAPL", "TSLA"},
        weights=weights,
    )
    # TSLA is mentioned but has zero weight → impact must be zero
    assert score["impact"] == 0
    assert score["symbols"] == ["TSLA"]


def test_rank_news_by_impact_sorts_descending_abs():
    weights = {"AAPL": 20.0, "TSLA": 5.0}
    items = [
        "TSLA recall announced",         # negative, small weight
        "AAPL beats earnings",           # positive, big weight
        "MSFT launches new product",     # not in book
    ]
    ranked = rank_news_by_impact(items, weights=weights)
    assert ranked[0]["headline"] == "AAPL beats earnings"
    assert ranked[1]["headline"] == "TSLA recall announced"
    assert ranked[2]["headline"] == "MSFT launches new product"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_news_impact.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `agent/news_impact.py`:

```python
"""Score news items by portfolio impact (mentioned tickers × position weight × polarity).

Lightweight, deterministic, no LLM calls. The Grok narrative still drives the
prose summary; this module is purely for ranking and routing.
"""

from __future__ import annotations

import re

_POSITIVE = {
    "beats", "beat", "raises", "raise", "upgrade", "upgraded", "record",
    "strong", "outperform", "surge", "surges", "rally", "rallies",
    "breakthrough", "approval", "approved", "win", "wins", "partnership",
}
_NEGATIVE = {
    "misses", "miss", "downgrade", "downgraded", "lawsuit", "investigation",
    "recall", "warns", "warning", "cut", "cuts", "slump", "plunge", "plunges",
    "halt", "halted", "fraud", "delisting", "bankruptcy", "decline", "declines",
}

_TOKEN_RE = re.compile(r"[A-Z]{1,6}")


def extract_mentioned_symbols(text: str, symbols: set[str]) -> set[str]:
    """Return the subset of `symbols` that appear as uppercase word tokens in text."""
    found = set(_TOKEN_RE.findall(text))
    return found & symbols


def polarity_score(text: str) -> int:
    """Naive polarity: +1 per positive keyword, -1 per negative keyword."""
    words = {w.strip(".,;:!?()[]\"'$/%").lower() for w in text.split()}
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    return pos - neg


def score_headline(
    headline: str,
    symbols: set[str],
    weights: dict[str, float],
) -> dict:
    """Score one headline.

    Returns {headline, symbols, polarity, impact} where impact = sum(weight_of_symbol)
    * polarity. Mentioned-but-unheld symbols are listed but contribute zero weight.
    """
    mentioned = extract_mentioned_symbols(headline, symbols)
    pol = polarity_score(headline)
    weight = sum(weights.get(s, 0.0) for s in mentioned)
    return {
        "headline": headline,
        "symbols": sorted(mentioned),
        "polarity": pol,
        "impact": round(weight * pol, 2),
    }


def rank_news_by_impact(
    headlines: list[str],
    weights: dict[str, float],
) -> list[dict]:
    """Return scored headlines sorted by |impact| descending."""
    symbols = set(weights)
    scored = [score_headline(h, symbols, weights) for h in headlines]
    scored.sort(key=lambda x: abs(x["impact"]), reverse=True)
    return scored
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_news_impact.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add agent/news_impact.py tests/agent/test_news_impact.py
git commit -m "feat(news): add portfolio impact scoring primitives"
```

---

### Task 3.2: Wire impact ranking into `news_monitor_job`

**Files:**
- Modify: `bot/proactive.py`
- Test: `tests/bot/test_proactive.py`

**Design note:** Grok returns one prose digest, not individual headlines. We split by newline as a pragmatic best-effort and score each line. If the digest is a single paragraph (no newlines), we fall back to current behavior.

- [ ] **Step 1: Write the failing test**

Append to `tests/bot/test_proactive.py`:

```python
@pytest.mark.asyncio
async def test_news_monitor_prepends_high_impact_summary(monkeypatch):
    monkeypatch.setattr("bot.proactive.PROACTIVE_NEWS_USER_ID", 42)

    report = {
        "report_date": "2026-05-10",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 10000, "stock_value_base": 10000,
                        "cash_base": 0, "total_unrealized_pnl_base": 0,
                        "total_cost_base": 10000, "total_unrealized_pnl_pct": 0},
            "positions": [
                {"symbol": "AAPL", "description": "", "asset_category": "STK",
                 "currency": "USD", "market_value_base": 8000,
                 "unrealized_pnl_base": 0, "unrealized_pnl_pct": 0,
                 "cost_basis_base": 8000},
                {"symbol": "TSLA", "description": "", "asset_category": "STK",
                 "currency": "USD", "market_value_base": 2000,
                 "unrealized_pnl_base": 0, "unrealized_pnl_pct": 0,
                 "cost_basis_base": 2000},
            ],
            "cash": [],
        }],
    }

    grok_digest = (
        "AAPL beats earnings and raises guidance for next quarter.\n"
        "TSLA recall announced over battery defect.\n"
        "Generic market chatter with no ticker."
    )

    bot_mock = AsyncMock()
    context = type("Ctx", (), {"bot": bot_mock})()

    from bot import proactive

    with patch.object(proactive, "_fetch_and_save", return_value=report), \
         patch.object(proactive, "_get_news", return_value=grok_digest):
        await proactive.news_monitor_job(context)

    sent_text = bot_mock.send_message.await_args.kwargs["text"]
    # High-impact summary must appear before the raw digest
    assert "影响排序" in sent_text or "Impact" in sent_text
    # AAPL (larger weight) ranks above TSLA in the summary
    aapl_idx = sent_text.find("AAPL")
    tsla_idx = sent_text.find("TSLA")
    assert 0 <= aapl_idx < tsla_idx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bot/test_proactive.py::test_news_monitor_prepends_high_impact_summary -v`
Expected: FAIL (no impact section in output).

- [ ] **Step 3: Build the position-weights helper inside proactive.py**

In `bot/proactive.py`, add an import and a small helper:

```python
from agent.news_impact import rank_news_by_impact
from agent.risk_calculator import compute_metrics


def _position_weights(report: dict) -> dict[str, float]:
    metrics = compute_metrics(report)
    if "error" in metrics:
        return {}
    return {item["symbol"]: item["weight_pct"] for item in metrics.get("concentration", [])}
```

- [ ] **Step 4: Modify `news_monitor_job` to prepend the impact ranking**

Inside `news_monitor_job`, after `digest = await asyncio.to_thread(_get_news, query)` and before the dedup `key = ...` line, insert:

```python
        weights = _position_weights(report)
        impact_summary = ""
        if weights:
            lines = [line.strip() for line in digest.splitlines() if line.strip()]
            ranked = rank_news_by_impact(lines, weights=weights)
            top = [r for r in ranked if r["impact"] != 0][:3]
            if top:
                impact_summary = "<b>影响排序（前 3 条）</b>\n" + "\n".join(
                    f"{'🟢' if r['impact'] > 0 else '🔴'} {', '.join(r['symbols']) or '—'}"
                    f"（影响分 {r['impact']:.1f}）：{r['headline']}"
                    for r in top
                ) + "\n\n"
```

Then change the `await _send(...)` call to prepend `impact_summary`:

```python
        await _send(
            context,
            user_id,
            "<b>重大新闻 / 财报提醒</b>\n\n" + impact_summary + digest,
        )
```

- [ ] **Step 5: Run the new test**

Run: `pytest tests/bot/test_proactive.py::test_news_monitor_prepends_high_impact_summary -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add bot/proactive.py tests/bot/test_proactive.py
git commit -m "feat(news): rank monitored news by portfolio impact"
```

---

### Task 3.3: Phase 3 verification

- [ ] **Step 1: README update**

In `README.md`, under "模型分工" table, add a row:

```text
| 新闻影响排序 | Python | 关键词极性 × 持仓权重，确定性可复现 |
```

And in the architecture diagram add:

```text
  +--> agent/news_impact.py    -> 持仓加权影响打分
```

(Reference the existing tool listings around lines 145-150 for style.)

- [ ] **Step 2: Commit docs**

```bash
git add README.md
git commit -m "docs: mention news impact scorer"
```

---

## Done

After all three phases:
- New tools: `get_risk_metrics`
- New abstractions: `bot.triggers.Trigger` (persistent), `agent.news_impact.rank_news_by_impact`
- Test deltas: +~30 unit tests across `tests/agent/` and `tests/bot/`
- No new external API dependencies; no new env vars
- Behavior change for users: `/news` and the opening brief surface ranked impact; threshold alerts no longer re-fire on restart

**Next iteration candidates (not in scope here):**
- Earnings calendar agent (V2 roadmap §2)
- Trade journal agent (V2 roadmap §3)
- Rebalancing suggestion agent (V2 roadmap §6)
- Swap `agent/news_impact.py` polarity for an LLM scorer once the keyword version proves the UX is worth it
