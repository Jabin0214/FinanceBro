# FinanceBro V2 Iteration 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a target-allocation rebalancing workflow (store targets → compute drift → alert when drift exceeds threshold), enrich the opening brief with a NLV trend line, and wire a scheduled drift-alert job.

**Architecture:** Three independent layers — (1) a pure-Python rebalancing engine + SQLite allocation store + orchestrator tool lets the AI answer "do I need to rebalance?"; (2) the existing `build_opening_brief` gains an optional `nlv_series` parameter so the daily push shows yesterday-vs-today NLV movement; (3) a new `drift_alert_job` reads the last saved report + stored targets and fires a Telegram push when the largest position drift exceeds a configurable threshold, reusing the existing `Trigger` cooldown infra.

**Tech Stack:** Python 3.12, SQLite (WAL), python-telegram-bot 20.x, existing `storage/db.py` patterns (`connect()` for reads, `transaction()` for writes).

---

## Files Modified / Created

| File | Action | Responsibility |
|------|--------|---------------|
| `storage/db.py` | modify | add `target_allocations` table to schema |
| `storage/allocation_store.py` | **create** | `set_targets` / `get_targets` CRUD |
| `storage/portfolio_store.py` | modify | add `get_latest_portfolio_report` helper |
| `agent/rebalancing.py` | **create** | pure-Python drift + trade-suggestion engine |
| `agent/tools/rebalancing.py` | **create** | `get_rebalancing_suggestion` orchestrator tool |
| `agent/tools/__init__.py` | modify | register new tool |
| `bot/handlers.py` | modify | add `cmd_settarget`, `cmd_target` commands |
| `bot/telegram_bot.py` | modify | register `/settarget`, `/target` handlers |
| `bot/proactive.py` | modify | `build_opening_brief` NLV trend, new `drift_alert_job` |
| `bot/scheduler.py` | modify | register drift alert job |
| `config.py` | modify | add `DRIFT_ALERT_*` config vars |
| `tests/storage/test_allocation_store.py` | **create** | 4 tests |
| `tests/storage/test_portfolio_store.py` | modify | 1 new test for `get_latest_portfolio_report` |
| `tests/agent/test_rebalancing.py` | **create** | 5 tests |
| `tests/agent/tools/test_tools_rebalancing.py` | **create** | 3 tests |
| `tests/bot/test_commands.py` | modify | 3 new command handler tests |
| `tests/bot/test_proactive.py` | modify | 5 new tests (NLV trend + drift alert) |

---

## Phase 1: Target Allocation Profile & Rebalancing Suggestion

### Task 1.1: DB Schema + Allocation Store

**Files:**
- Modify: `storage/db.py` (add table to `_init_schema`)
- Create: `storage/allocation_store.py`
- Create: `tests/storage/test_allocation_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/storage/test_allocation_store.py`:

```python
import pytest
from storage.allocation_store import get_targets, set_targets


def test_set_and_get_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    set_targets(42, {"AAPL": 30.0, "MSFT": 20.0})
    result = get_targets(42)
    assert result == {"AAPL": 30.0, "MSFT": 20.0}


def test_set_targets_replaces_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    set_targets(42, {"AAPL": 30.0})
    set_targets(42, {"MSFT": 40.0, "GOOGL": 25.0})
    result = get_targets(42)
    assert result == {"MSFT": 40.0, "GOOGL": 25.0}
    assert "AAPL" not in result


def test_get_targets_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    result = get_targets(999)
    assert result == {}


def test_set_targets_upcases_symbols(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    set_targets(42, {"aapl": 30.0, "msft": 20.0})
    result = get_targets(42)
    assert "AAPL" in result
    assert "MSFT" in result
    assert "aapl" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_allocation_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'storage.allocation_store'`

- [ ] **Step 3: Add `target_allocations` table to `storage/db.py`**

In `storage/db.py`, inside `_init_schema`, add the following block **before** the final `conn.commit()` line (after the existing `idx_trigger_fires_lookup` index statement):

```sql
        create table if not exists target_allocations (
            id integer primary key autoincrement,
            user_id integer not null,
            symbol text not null,
            target_pct real not null,
            updated_at text not null default current_timestamp,
            unique (user_id, symbol)
        );
```

- [ ] **Step 4: Create `storage/allocation_store.py`**

```python
"""CRUD for user target allocation profiles."""

from __future__ import annotations

from storage import db


def set_targets(user_id: int, targets: dict[str, float]) -> None:
    """Replace all target allocations for user. targets = {SYMBOL: target_pct}."""
    with db.transaction() as conn:
        conn.execute("delete from target_allocations where user_id = ?", (user_id,))
        conn.executemany(
            "insert into target_allocations (user_id, symbol, target_pct) values (?, ?, ?)",
            [(user_id, sym.upper(), round(float(pct), 2)) for sym, pct in targets.items()],
        )


def get_targets(user_id: int) -> dict[str, float]:
    """Return {SYMBOL: target_pct} for user, empty dict if none set."""
    with db.connect() as conn:
        rows = conn.execute(
            "select symbol, target_pct from target_allocations where user_id = ? order by symbol",
            (user_id,),
        ).fetchall()
    return {row["symbol"]: row["target_pct"] for row in rows}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/storage/test_allocation_store.py -v`
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add storage/db.py storage/allocation_store.py tests/storage/test_allocation_store.py
git commit -m "feat(storage): target_allocations table + allocation_store CRUD"
```

---

### Task 1.2: Rebalancing Engine

**Files:**
- Create: `agent/rebalancing.py`
- Create: `tests/agent/test_rebalancing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/agent/test_rebalancing.py`:

```python
from agent.rebalancing import compute_rebalancing


def _weights(*items):
    """Build concentration list from (symbol, weight_pct, market_value_base) tuples."""
    return [
        {"symbol": s, "weight_pct": w, "market_value_base": mv}
        for s, w, mv in items
    ]


def test_compute_rebalancing_basic_drift():
    current = _weights(
        ("AAPL", 40.0, 40000.0),
        ("MSFT", 30.0, 30000.0),
        ("CASH", 30.0, 30000.0),
    )
    targets = {"AAPL": 30.0, "MSFT": 40.0}
    result = compute_rebalancing(current, targets, 100000.0)

    assert result["total_target_pct"] == 70.0
    assert result["unallocated_pct"] == 30.0

    drift_map = {r["symbol"]: r for r in result["drift"]}
    assert drift_map["AAPL"]["drift_pct"] == 10.0    # overweight by 10 pp
    assert drift_map["MSFT"]["drift_pct"] == -10.0   # underweight by 10 pp
    assert drift_map["AAPL"]["suggested_trade_base"] == -10000.0  # sell $10k
    assert drift_map["MSFT"]["suggested_trade_base"] == 10000.0   # buy $10k


def test_compute_rebalancing_sorts_by_abs_drift():
    current = _weights(("AAPL", 50.0, 50000.0), ("MSFT", 50.0, 50000.0))
    targets = {"AAPL": 40.0, "MSFT": 45.0}
    result = compute_rebalancing(current, targets, 100000.0)

    # AAPL drift = 10 pp, MSFT drift = 5 pp → AAPL first
    assert result["drift"][0]["symbol"] == "AAPL"
    assert result["max_drift_symbol"] == "AAPL"
    assert result["max_drift_abs_pct"] == 10.0


def test_compute_rebalancing_symbol_not_in_portfolio():
    current = _weights(("AAPL", 100.0, 100000.0))
    targets = {"AAPL": 60.0, "MSFT": 20.0}  # MSFT not held yet
    result = compute_rebalancing(current, targets, 100000.0)

    drift_map = {r["symbol"]: r for r in result["drift"]}
    assert drift_map["MSFT"]["current_pct"] == 0.0
    assert drift_map["MSFT"]["drift_pct"] == -20.0       # underweight
    assert drift_map["MSFT"]["suggested_trade_base"] == 20000.0  # buy $20k


def test_compute_rebalancing_empty_targets_returns_error():
    current = _weights(("AAPL", 100.0, 100000.0))
    result = compute_rebalancing(current, {}, 100000.0)
    assert "error" in result


def test_compute_rebalancing_zero_portfolio_value_returns_error():
    result = compute_rebalancing([], {"AAPL": 30.0}, 0.0)
    assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/test_rebalancing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.rebalancing'`

- [ ] **Step 3: Create `agent/rebalancing.py`**

```python
"""Rebalancing engine — pure Python, no external deps.

Compares current portfolio weights against user-defined target allocations
and computes position drift + suggested trade direction/size.
"""

from __future__ import annotations


def compute_rebalancing(
    current_weights: list[dict],
    targets: dict[str, float],
    total_portfolio_value: float,
) -> dict:
    """
    Args:
        current_weights: list of {"symbol": str, "weight_pct": float, "market_value_base": float}
                         (the "concentration" list from risk_calculator.compute_metrics)
        targets: {SYMBOL: target_pct} — sum should be <= 100
        total_portfolio_value: total net liquidation in base currency

    Returns:
        {
            "drift": [
                {
                    "symbol": str,
                    "target_pct": float,
                    "current_pct": float,
                    "drift_pct": float,          # current - target; positive = overweight
                    "suggested_trade_base": float,  # negative = sell, positive = buy
                },
                ...                              # sorted by abs(drift_pct) desc
            ],
            "total_target_pct": float,
            "unallocated_pct": float,            # 100 - total_target_pct
            "max_drift_symbol": str | None,
            "max_drift_abs_pct": float,
        }
        or {"error": str} on invalid input.
    """
    if not targets:
        return {"error": "no targets defined"}
    if total_portfolio_value <= 0:
        return {"error": "invalid portfolio value"}

    # Build lookup: SYMBOL → current weight_pct
    current_by_symbol: dict[str, float] = {
        pos["symbol"].upper(): float(pos["weight_pct"])
        for pos in current_weights
    }

    total_target = sum(targets.values())
    drift_rows: list[dict] = []

    for symbol, target_pct in sorted(targets.items()):
        sym_upper = symbol.upper()
        current_pct = current_by_symbol.get(sym_upper, 0.0)
        drift = round(current_pct - target_pct, 2)
        # A positive drift means overweight → suggested trade is negative (sell)
        trade_value = round(-drift / 100.0 * total_portfolio_value, 2)
        drift_rows.append({
            "symbol": sym_upper,
            "target_pct": round(float(target_pct), 2),
            "current_pct": round(current_pct, 2),
            "drift_pct": drift,
            "suggested_trade_base": trade_value,
        })

    drift_rows.sort(key=lambda r: abs(r["drift_pct"]), reverse=True)

    max_row = drift_rows[0] if drift_rows else None
    return {
        "drift": drift_rows,
        "total_target_pct": round(float(total_target), 2),
        "unallocated_pct": round(100.0 - float(total_target), 2),
        "max_drift_symbol": max_row["symbol"] if max_row else None,
        "max_drift_abs_pct": abs(max_row["drift_pct"]) if max_row else 0.0,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agent/test_rebalancing.py -v`
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/rebalancing.py tests/agent/test_rebalancing.py
git commit -m "feat(agent): rebalancing engine — drift + suggested trade computation"
```

---

### Task 1.3: Rebalancing Orchestrator Tool

**Files:**
- Create: `agent/tools/rebalancing.py`
- Modify: `agent/tools/__init__.py`
- Create: `tests/agent/tools/test_tools_rebalancing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/agent/tools/test_tools_rebalancing.py`:

```python
import json
from unittest.mock import patch

from agent.tools import rebalancing as rebalancing_tool


def test_execute_returns_error_when_no_targets(monkeypatch):
    monkeypatch.setattr("agent.tools.rebalancing.current_user_id", lambda: 42)
    with patch("agent.tools.rebalancing.get_targets", return_value={}):
        result = json.loads(rebalancing_tool.execute({}))
    assert "error" in result


def test_execute_returns_error_when_no_portfolio_metrics(monkeypatch):
    monkeypatch.setattr("agent.tools.rebalancing.current_user_id", lambda: 42)
    with (
        patch("agent.tools.rebalancing.get_targets", return_value={"AAPL": 30.0}),
        patch("agent.tools.rebalancing.get_cached_portfolio", return_value={}),
        patch("agent.tools.rebalancing.compute_metrics", return_value={"error": "no positions"}),
    ):
        result = json.loads(rebalancing_tool.execute({}))
    assert "error" in result


def test_execute_returns_drift_when_targets_and_portfolio_present(monkeypatch):
    monkeypatch.setattr("agent.tools.rebalancing.current_user_id", lambda: 42)
    mock_metrics = {
        "total_net_liquidation": 100000.0,
        "concentration": [
            {"symbol": "AAPL", "weight_pct": 40.0, "market_value_base": 40000.0, "unrealized_pnl_pct": 5.0},
            {"symbol": "MSFT", "weight_pct": 30.0, "market_value_base": 30000.0, "unrealized_pnl_pct": 2.0},
        ],
    }
    with (
        patch("agent.tools.rebalancing.get_targets", return_value={"AAPL": 30.0, "MSFT": 40.0}),
        patch("agent.tools.rebalancing.get_cached_portfolio", return_value={"accounts": []}),
        patch("agent.tools.rebalancing.compute_metrics", return_value=mock_metrics),
    ):
        result = json.loads(rebalancing_tool.execute({}))
    assert "drift" in result
    assert len(result["drift"]) == 2
    drift_map = {r["symbol"]: r for r in result["drift"]}
    assert drift_map["AAPL"]["drift_pct"] == 10.0
    assert drift_map["MSFT"]["drift_pct"] == -10.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agent/tools/test_tools_rebalancing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.tools.rebalancing'`

- [ ] **Step 3: Create `agent/tools/rebalancing.py`**

```python
"""get_rebalancing_suggestion tool — compares portfolio to stored target allocations."""

from __future__ import annotations

import json
import logging

from agent.rebalancing import compute_rebalancing
from agent.risk_calculator import compute_metrics
from agent.tools._state import current_user_id
from agent.tools.portfolio import get_cached_portfolio
from storage.allocation_store import get_targets

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "get_rebalancing_suggestion",
    "description": (
        "根据用户通过 /settarget 设定的目标仓位比例，分析当前组合与目标的偏差并给出调仓建议。"
        "返回每个目标标的的超配/低配程度及建议买卖金额。"
        "当用户询问调仓、再平衡、仓位偏离、需要买入或卖出哪些标的时调用。"
        "若用户未设置目标仓位则返回提示。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def execute(_tool_input: dict) -> str:
    user_id = current_user_id()
    if user_id is None:
        return json.dumps({"error": "未知用户"}, ensure_ascii=False)

    targets = get_targets(user_id)
    if not targets:
        return json.dumps(
            {"error": "未设置目标仓位，请先发送 /settarget AAPL 30 MSFT 20 ..."},
            ensure_ascii=False,
        )

    portfolio = get_cached_portfolio()
    metrics = compute_metrics(portfolio)
    if "error" in metrics:
        return json.dumps(metrics, ensure_ascii=False)

    result = compute_rebalancing(
        current_weights=metrics["concentration"],
        targets=targets,
        total_portfolio_value=metrics["total_net_liquidation"],
    )
    logger.info(
        "rebalancing suggestion — user=%s max_drift=%s%%",
        user_id,
        result.get("max_drift_abs_pct"),
    )
    return json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 4: Register the tool in `agent/tools/__init__.py`**

In `agent/tools/__init__.py`, add `rebalancing` to the imports and registrations:

```python
from agent.tools import history, news, portfolio, rebalancing, report, risk, risk_metrics
from agent.tools._state import (
    pop_pending_files,
    reset_active_user,
    set_active_user,
)

__all__ = [
    "TOOL_DEFINITIONS",
    "execute_tool",
    "set_active_user",
    "reset_active_user",
    "pop_pending_files",
]

_TOOLS = {
    portfolio.DEFINITION["name"]:    portfolio.execute,
    history.DEFINITION["name"]:      history.execute,
    report.DEFINITION["name"]:       report.execute,
    news.DEFINITION["name"]:         news.execute,
    risk.DEFINITION["name"]:         risk.execute,
    risk_metrics.DEFINITION["name"]: risk_metrics.execute,
    rebalancing.DEFINITION["name"]:  rebalancing.execute,
}

TOOL_DEFINITIONS = [
    portfolio.DEFINITION,
    history.DEFINITION,
    report.DEFINITION,
    news.DEFINITION,
    risk.DEFINITION,
    risk_metrics.DEFINITION,
    rebalancing.DEFINITION,
]


def execute_tool(name: str, tool_input: dict) -> str:
    if name not in _TOOLS:
        raise ValueError(f"未知工具: {name}")
    return _TOOLS[name](tool_input)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/agent/tools/test_tools_rebalancing.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all green (was 90 before this task; now +7 = 97 passing)

- [ ] **Step 7: Commit**

```bash
git add agent/tools/rebalancing.py agent/tools/__init__.py tests/agent/tools/test_tools_rebalancing.py
git commit -m "feat(tools): get_rebalancing_suggestion orchestrator tool"
```

---

### Task 1.4: Bot Commands `/settarget` and `/target`

**Files:**
- Modify: `bot/handlers.py`
- Modify: `bot/telegram_bot.py`
- Modify: `tests/bot/test_commands.py`

- [ ] **Step 1: Write the failing tests**

Add three new tests to the end of `tests/bot/test_commands.py`:

```python
@pytest.mark.anyio
async def test_cmd_settarget_stores_targets(monkeypatch):
    stored = {}
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "set_targets", lambda user_id, targets: stored.update(targets))
    update = _update(user_id=42)
    context = _context(args=["AAPL", "30", "MSFT", "20"])

    await handlers.cmd_settarget(update, context)

    assert stored == {"AAPL": 30.0, "MSFT": 20.0}
    update.message.reply_text.assert_awaited_once()
    assert "✅" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_cmd_settarget_rejects_odd_args(monkeypatch):
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    update = _update()
    context = _context(args=["AAPL"])

    await handlers.cmd_settarget(update, context)

    assert "/settarget" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_cmd_target_shows_stored_targets(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "get_targets", lambda _user_id: {"AAPL": 30.0, "MSFT": 20.0})
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_target(_update(user_id=42), _context())

    assert sent
    assert "AAPL" in sent[0]
    assert "30.0%" in sent[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/bot/test_commands.py::test_cmd_settarget_stores_targets tests/bot/test_commands.py::test_cmd_settarget_rejects_odd_args tests/bot/test_commands.py::test_cmd_target_shows_stored_targets -v`
Expected: FAIL with `AttributeError: module 'bot.handlers' has no attribute 'cmd_settarget'`

- [ ] **Step 3: Add imports and commands to `bot/handlers.py`**

At the top of `bot/handlers.py`, add to the existing import block:

```python
from storage.allocation_store import get_targets, set_targets
```

Then add the two command functions (insert after `cmd_history` and before `handle_message`):

```python
async def cmd_settarget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    args = context.args or []
    if len(args) < 2 or len(args) % 2 != 0:
        await update.message.reply_text(
            "用法：/settarget AAPL 30 MSFT 20 TSLA 15\n"
            "每个标的需对应一个目标权重（%），成对输入。"
        )
        return

    targets: dict[str, float] = {}
    for i in range(0, len(args), 2):
        symbol = args[i].upper()
        try:
            pct = float(args[i + 1])
        except ValueError:
            await update.message.reply_text(f"无效权重：{args[i + 1]}，请输入数字。")
            return
        if pct <= 0:
            await update.message.reply_text(f"权重必须大于 0，{symbol} 的权重为 {pct}。")
            return
        targets[symbol] = pct

    total = sum(targets.values())
    warning = f"\n\n⚠️ 目标权重合计 {total:.1f}%，超过 100%，请确认。" if total > 100 else ""

    user_id = update.effective_user.id
    set_targets(user_id, targets)

    lines = "\n".join(f"  {sym}：{pct:.1f}%" for sym, pct in sorted(targets.items()))
    await update.message.reply_text(
        f"✅ 目标仓位已保存\n\n{lines}\n\n合计：{total:.1f}%{warning}",
        parse_mode=ParseMode.HTML,
    )


async def cmd_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    targets = get_targets(user_id)

    if not targets:
        await update.message.reply_text(
            "还未设置目标仓位，请使用：\n/settarget AAPL 30 MSFT 20 TSLA 15"
        )
        return

    total = sum(targets.values())
    lines = "\n".join(
        f"<code>{sym:<8}</code>{pct:.1f}%" for sym, pct in sorted(targets.items())
    )
    await send_html_with_fallback(
        update,
        "<b>目标仓位</b>\n\n"
        + lines
        + f"\n{'—' * 14}\n"
        + f"已分配：{total:.1f}%  剩余：{100.0 - total:.1f}%\n\n"
        + "💬 发消息询问 AI 可获取调仓建议（偏离分析、建议买卖金额）。",
    )
```

- [ ] **Step 4: Register commands in `bot/telegram_bot.py`**

In `bot/telegram_bot.py`, update the imports:

```python
from bot.handlers import (
    cmd_alerts,
    cmd_brief,
    cmd_clear,
    cmd_history,
    cmd_news,
    cmd_report,
    cmd_risk,
    cmd_settarget,
    cmd_start,
    cmd_target,
    handle_message,
)
```

And add two handler registrations after `app.add_handler(CommandHandler("history", cmd_history))`:

```python
    app.add_handler(CommandHandler("settarget", cmd_settarget))
    app.add_handler(CommandHandler("target", cmd_target))
```

Also update the docstring at the top of `telegram_bot.py` to include the new commands:

```python
"""Telegram application wiring.

Commands:
  /start      — show help
  /report     — fetch IBKR portfolio HTML report (no AI, saves tokens)
  /risk       — run risk analysis
  /news       — search market news
  /brief      — generate opening brief now
  /alerts     — check threshold alerts now
  /history    — summarize recent portfolio changes
  /settarget  — set target allocation (e.g. /settarget AAPL 30 MSFT 20)
  /target     — view stored target allocation
  /clear      — clear current conversation history

Plain text → routed to the Orchestrator agent (Claude Sonnet); the agent
auto-invokes tools (portfolio, news, risk, report, rebalancing) as needed.
"""
```

Also update `/start` help text in `cmd_start` in `bot/handlers.py` to mention the new commands. Replace the existing help text block:

```python
    await update.message.reply_text(
        "👋 <b>FinanceBro</b> 已就绪\n\n"
        "💬 <b>直接发消息</b>即可与 AI 对话，可询问持仓、盈亏分析、调仓建议等\n\n"
        "📋 <b>命令</b>\n"
        "/report      — 直接获取持仓 HTML 报告\n"
        "/risk        — 立即运行风险分析 Agent\n"
        "/news AAPL   — 搜索新闻 / 财报 / 市场动态\n"
        "/brief       — 立即生成开盘前简报\n"
        "/alerts      — 立即检查持仓阈值预警\n"
        "/history     — 查看最近 30 天组合复盘\n"
        "/settarget   — 设置目标仓位（例：/settarget AAPL 30 MSFT 20）\n"
        "/target      — 查看目标仓位与调仓建议\n"
        "/clear       — 清除对话历史",
        parse_mode=ParseMode.HTML,
    )
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/bot/test_commands.py::test_cmd_settarget_stores_targets tests/bot/test_commands.py::test_cmd_settarget_rejects_odd_args tests/bot/test_commands.py::test_cmd_target_shows_stored_targets -v`
Expected: 3 PASSED

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all green (now ~100 passing)

- [ ] **Step 7: Commit**

```bash
git add bot/handlers.py bot/telegram_bot.py tests/bot/test_commands.py
git commit -m "feat(bot): /settarget and /target commands for allocation profiles"
```

---

## Phase 2: Enhanced Opening Brief with NLV Trend

### Task 2.1: NLV Trend Line in Opening Brief

**Files:**
- Modify: `bot/proactive.py`
- Modify: `tests/bot/test_proactive.py`

- [ ] **Step 1: Write the failing tests**

Add two new tests to `tests/bot/test_proactive.py`:

```python
def test_build_opening_brief_includes_nlv_trend_when_series_has_two_entries():
    from bot.proactive import build_opening_brief

    report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1",
            "alias": "main",
            "base_currency": "USD",
            "summary": {
                "net_liquidation": 105000.0,
                "stock_value_base": 100000.0,
                "cash_base": 5000.0,
                "total_unrealized_pnl_base": 5000.0,
                "total_cost_base": 95000.0,
                "total_unrealized_pnl_pct": 5.26,
            },
            "positions": [{
                "symbol": "AAPL",
                "description": "Apple Inc",
                "currency": "USD",
                "asset_category": "STK",
                "quantity": 10.0,
                "cost_price": 150.0,
                "mark_price": 175.0,
                "market_value": 1750.0,
                "market_value_base": 1750.0,
                "cost_basis": 1500.0,
                "cost_basis_base": 1500.0,
                "unrealized_pnl": 250.0,
                "unrealized_pnl_base": 250.0,
                "unrealized_pnl_pct": 16.67,
                "fx_rate": 1.0,
            }],
            "cash_balances": [],
        }],
    }
    nlv_series = [("2026-05-11", 100000.0), ("2026-05-12", 105000.0)]

    text = build_opening_brief(report, nlv_series=nlv_series)

    assert "净值变动" in text
    assert "+5,000" in text or "+5000" in text
    assert "+5.0%" in text


def test_build_opening_brief_omits_trend_when_series_has_one_entry():
    from bot.proactive import build_opening_brief

    report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1",
            "alias": "main",
            "base_currency": "USD",
            "summary": {
                "net_liquidation": 100000.0,
                "stock_value_base": 95000.0,
                "cash_base": 5000.0,
                "total_unrealized_pnl_base": 0.0,
                "total_cost_base": 95000.0,
                "total_unrealized_pnl_pct": 0.0,
            },
            "positions": [{
                "symbol": "AAPL",
                "description": "Apple Inc",
                "currency": "USD",
                "asset_category": "STK",
                "quantity": 10.0,
                "cost_price": 150.0,
                "mark_price": 150.0,
                "market_value": 1500.0,
                "market_value_base": 1500.0,
                "cost_basis": 1500.0,
                "cost_basis_base": 1500.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_base": 0.0,
                "unrealized_pnl_pct": 0.0,
                "fx_rate": 1.0,
            }],
            "cash_balances": [],
        }],
    }
    nlv_series = [("2026-05-12", 100000.0)]  # only one entry

    text = build_opening_brief(report, nlv_series=nlv_series)

    assert "净值变动" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/bot/test_proactive.py::test_build_opening_brief_includes_nlv_trend_when_series_has_two_entries tests/bot/test_proactive.py::test_build_opening_brief_omits_trend_when_series_has_one_entry -v`
Expected: FAIL — `build_opening_brief` doesn't accept `nlv_series` kwarg

- [ ] **Step 3: Modify `build_opening_brief` in `bot/proactive.py`**

Change the function signature and body. Replace the existing `build_opening_brief` function (starting at `def build_opening_brief(report: dict) -> str:`) with:

```python
def build_opening_brief(
    report: dict,
    nlv_series: list[tuple[str, float]] | None = None,
) -> str:
    metrics = compute_metrics(report)
    if "error" in metrics:
        return f"<b>开盘前简报</b>\n\n⚪ 暂无有效持仓数据：{metrics['error']}"

    pnl = metrics["pnl_summary"]
    pnl_emoji = "🟢" if pnl["total_pnl_pct"] >= 0 else "🔴"

    # NLV trend vs yesterday
    nlv_trend = ""
    if nlv_series and len(nlv_series) >= 2:
        prev_nlv = nlv_series[-2][1]
        curr_nlv = nlv_series[-1][1]
        if prev_nlv:
            delta = curr_nlv - prev_nlv
            delta_pct = delta / prev_nlv * 100
            trend_emoji = "📈" if delta >= 0 else "📉"
            sign = "+" if delta >= 0 else ""
            nlv_trend = (
                f"{trend_emoji} 净值变动：{sign}{delta:,.2f}"
                f"（{delta_pct:+.1f}%）vs 昨日\n"
            )

    top = metrics["concentration"][:5]
    top_lines = [
        f"{item['symbol']} {item['weight_pct']:.1f}%（浮动 {item['unrealized_pnl_pct']:.1f}%）"
        for item in top
    ]
    alerts = build_threshold_alerts(
        report,
        pnl_threshold_pct=PROACTIVE_ALERT_PNL_PCT,
        position_weight_threshold_pct=PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
    )
    alert_text = "\n".join(f"🔴 {alert}" for alert in alerts) if alerts else "🟢 未触发风险阈值"

    return (
        "<b>开盘前简报</b>\n\n"
        f"日期：{report.get('report_date', 'unknown')}\n"
        f"净值：${metrics['total_net_liquidation']:,.2f}\n"
        f"{nlv_trend}"
        f"{pnl_emoji} 整体浮动：{pnl['total_pnl_pct']:.1f}%"
        f"（${pnl['total_unrealized_pnl']:,.2f}）\n"
        f"前五大持仓：{metrics['top5_concentration_pct']:.1f}% · HHI：{metrics['hhi']:,.0f}\n\n"
        "<b>主要持仓</b>\n"
        + "\n".join(top_lines)
        + "\n\n<b>风险提醒</b>\n"
        + alert_text
    )
```

- [ ] **Step 4: Update `opening_brief_job` to pass the NLV series**

In `bot/proactive.py`, add `get_net_liquidation_series` to the import from `storage.portfolio_store`:

```python
from storage.portfolio_store import get_net_liquidation_series, save_portfolio_report
```

Then modify the `opening_brief_job` function. Replace its try block body:

```python
    try:
        report = await asyncio.to_thread(_fetch_and_save, user_id)
        nlv_series = await asyncio.to_thread(get_net_liquidation_series, user_id, 2)
        await _send(context, user_id, build_opening_brief(report, nlv_series=nlv_series))
    except Exception:
        logger.exception("opening brief failed")
        await _send(context, user_id, "❌ 开盘前简报生成失败，请稍后手动发送 /report 检查。")
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/bot/test_proactive.py::test_build_opening_brief_includes_nlv_trend_when_series_has_two_entries tests/bot/test_proactive.py::test_build_opening_brief_omits_trend_when_series_has_one_entry -v`
Expected: 2 PASSED

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add bot/proactive.py tests/bot/test_proactive.py
git commit -m "feat(brief): add NLV trend vs yesterday to opening brief"
```

---

## Phase 3: Drift Alert Job

### Task 3.1: Config Vars + Portfolio Store Helper

**Files:**
- Modify: `config.py`
- Modify: `storage/portfolio_store.py`
- Modify: `tests/storage/test_portfolio_store.py`

- [ ] **Step 1: Write the failing test**

Add one new test to `tests/storage/test_portfolio_store.py`:

```python
def test_get_latest_portfolio_report_returns_saved_report(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    from storage.portfolio_store import get_latest_portfolio_report, save_portfolio_report

    report = _sample_report()
    save_portfolio_report(42, report)

    result = get_latest_portfolio_report(42)
    assert result is not None
    assert result["report_date"] == report["report_date"]
    assert len(result["accounts"]) == 1


def test_get_latest_portfolio_report_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    from storage.portfolio_store import get_latest_portfolio_report

    assert get_latest_portfolio_report(999) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/storage/test_portfolio_store.py::test_get_latest_portfolio_report_returns_saved_report tests/storage/test_portfolio_store.py::test_get_latest_portfolio_report_returns_none_when_empty -v`
Expected: FAIL with `ImportError: cannot import name 'get_latest_portfolio_report'`

- [ ] **Step 3: Add `get_latest_portfolio_report` to `storage/portfolio_store.py`**

Add the following function after `get_position_history` (before `_normalize_history_days`):

```python
def get_latest_portfolio_report(user_id: int) -> dict | None:
    """Return the most recently saved raw portfolio report dict for user, or None."""
    with db.connect() as conn:
        row = conn.execute(
            """
            select payload_json from raw_reports
            where user_id = ?
            order by report_date desc, id desc
            limit 1
            """,
            (user_id,),
        ).fetchone()
    return json.loads(row["payload_json"]) if row else None
```

- [ ] **Step 4: Add drift alert config vars to `config.py`**

Add after the existing `PROACTIVE_NEWS_INTERVAL_MINUTES` line:

```python
DRIFT_ALERT_ENABLED = _parse_bool("DRIFT_ALERT_ENABLED", "false")
DRIFT_ALERT_USER_ID = DEFAULT_USER_ID
DRIFT_ALERT_THRESHOLD_PCT = float(os.getenv("DRIFT_ALERT_THRESHOLD_PCT", "10.0"))
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/storage/test_portfolio_store.py::test_get_latest_portfolio_report_returns_saved_report tests/storage/test_portfolio_store.py::test_get_latest_portfolio_report_returns_none_when_empty -v`
Expected: 2 PASSED

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add config.py storage/portfolio_store.py tests/storage/test_portfolio_store.py
git commit -m "feat(config): DRIFT_ALERT env vars; feat(storage): get_latest_portfolio_report helper"
```

---

### Task 3.2: Drift Alert Job

**Files:**
- Modify: `bot/proactive.py`
- Modify: `tests/bot/test_proactive.py`

- [ ] **Step 1: Write the failing tests**

Add three new tests to `tests/bot/test_proactive.py`:

```python
@pytest.mark.anyio
async def test_drift_alert_job_fires_when_drift_exceeds_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "drift_test.db"))
    from bot import proactive

    sent = []

    _report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 100000.0, "stock_value_base": 100000.0,
                        "cash_base": 0.0, "total_unrealized_pnl_base": 0.0,
                        "total_cost_base": 100000.0, "total_unrealized_pnl_pct": 0.0},
            "positions": [{"symbol": "AAPL", "description": "", "currency": "USD",
                           "asset_category": "STK", "quantity": 100.0, "cost_price": 150.0,
                           "mark_price": 170.0, "market_value": 17000.0, "market_value_base": 17000.0,
                           "cost_basis": 15000.0, "cost_basis_base": 15000.0, "unrealized_pnl": 2000.0,
                           "unrealized_pnl_base": 2000.0, "unrealized_pnl_pct": 13.33, "fx_rate": 1.0}],
            "cash_balances": [],
        }],
    }

    monkeypatch.setattr(proactive, "DRIFT_ALERT_USER_ID", 42)
    monkeypatch.setattr(proactive, "DRIFT_ALERT_THRESHOLD_PCT", 5.0)
    monkeypatch.setattr(proactive, "get_latest_portfolio_report", lambda user_id: _report)
    monkeypatch.setattr(proactive, "get_targets", lambda user_id: {"AAPL": 80.0})  # current ~17%, target 80%
    monkeypatch.setattr(proactive, "should_fire", lambda trigger, user_id, fingerprint: True)
    monkeypatch.setattr(proactive, "record_fire", lambda trigger, user_id, fingerprint: None)
    monkeypatch.setattr(proactive, "_send", AsyncMock(side_effect=lambda ctx, uid, text: sent.append(text)))

    context = SimpleNamespace(bot=AsyncMock())
    await proactive.drift_alert_job(context)

    assert sent
    assert "仓位偏离预警" in sent[0]
    assert "AAPL" in sent[0]


@pytest.mark.anyio
async def test_drift_alert_job_skips_when_drift_below_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "drift_test2.db"))
    from bot import proactive

    sent = []

    _report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 100000.0, "stock_value_base": 100000.0,
                        "cash_base": 0.0, "total_unrealized_pnl_base": 0.0,
                        "total_cost_base": 100000.0, "total_unrealized_pnl_pct": 0.0},
            "positions": [{"symbol": "AAPL", "description": "", "currency": "USD",
                           "asset_category": "STK", "quantity": 100.0, "cost_price": 150.0,
                           "mark_price": 150.0, "market_value": 15000.0, "market_value_base": 15000.0,
                           "cost_basis": 15000.0, "cost_basis_base": 15000.0, "unrealized_pnl": 0.0,
                           "unrealized_pnl_base": 0.0, "unrealized_pnl_pct": 0.0, "fx_rate": 1.0}],
            "cash_balances": [],
        }],
    }

    monkeypatch.setattr(proactive, "DRIFT_ALERT_USER_ID", 42)
    monkeypatch.setattr(proactive, "DRIFT_ALERT_THRESHOLD_PCT", 20.0)   # high threshold
    monkeypatch.setattr(proactive, "get_latest_portfolio_report", lambda user_id: _report)
    monkeypatch.setattr(proactive, "get_targets", lambda user_id: {"AAPL": 14.0})  # ~1% drift
    monkeypatch.setattr(proactive, "_send", AsyncMock(side_effect=lambda ctx, uid, text: sent.append(text)))

    context = SimpleNamespace(bot=AsyncMock())
    await proactive.drift_alert_job(context)

    assert not sent


@pytest.mark.anyio
async def test_drift_alert_job_skips_when_no_targets(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "drift_test3.db"))
    from bot import proactive

    sent = []
    monkeypatch.setattr(proactive, "DRIFT_ALERT_USER_ID", 42)
    monkeypatch.setattr(proactive, "get_latest_portfolio_report", lambda user_id: {"report_date": "2026-05-12", "accounts": []})
    monkeypatch.setattr(proactive, "get_targets", lambda user_id: {})
    monkeypatch.setattr(proactive, "_send", AsyncMock(side_effect=lambda ctx, uid, text: sent.append(text)))

    context = SimpleNamespace(bot=AsyncMock())
    await proactive.drift_alert_job(context)

    assert not sent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/bot/test_proactive.py::test_drift_alert_job_fires_when_drift_exceeds_threshold tests/bot/test_proactive.py::test_drift_alert_job_skips_when_drift_below_threshold tests/bot/test_proactive.py::test_drift_alert_job_skips_when_no_targets -v`
Expected: FAIL with `AttributeError: module 'bot.proactive' has no attribute 'drift_alert_job'`

- [ ] **Step 3: Add imports and `_DRIFT_ALERT_TRIGGER` to `bot/proactive.py`**

Add to the existing imports at the top of `bot/proactive.py`:

```python
from agent.rebalancing import compute_rebalancing
from config import (
    DRIFT_ALERT_THRESHOLD_PCT,
    DRIFT_ALERT_USER_ID,
    PROACTIVE_ALERT_PNL_PCT,
    PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
    PROACTIVE_ALERT_USER_ID,
    PROACTIVE_BRIEF_USER_ID,
    PROACTIVE_NEWS_USER_ID,
)
from storage.allocation_store import get_targets
from storage.portfolio_store import get_latest_portfolio_report, get_net_liquidation_series, save_portfolio_report
```

(Replace the existing `from config import ...` and `from storage.portfolio_store import ...` lines with the above.)

Then, after the `_NEWS_MONITOR_TRIGGER` constant, add:

```python
_DRIFT_ALERT_TRIGGER = Trigger(
    name="drift.alert",
    cooldown_seconds=12 * 3600,
    max_fires_per_day=2,
)
```

- [ ] **Step 4: Add `drift_alert_job` to `bot/proactive.py`**

Add the following function after `news_monitor_job` (before `build_opening_brief`):

```python
async def drift_alert_job(context) -> None:
    user_id = DRIFT_ALERT_USER_ID
    if user_id is None:
        logger.error("drift alert skipped: missing DRIFT_ALERT_USER_ID")
        return

    try:
        report = await asyncio.to_thread(get_latest_portfolio_report, user_id)
        if not report:
            logger.info("drift alert skipped: no saved portfolio")
            return

        targets = get_targets(user_id)
        if not targets:
            logger.info("drift alert skipped: no targets set")
            return

        metrics = compute_metrics(report)
        if "error" in metrics:
            logger.info("drift alert skipped: %s", metrics["error"])
            return

        drift_result = compute_rebalancing(
            current_weights=metrics["concentration"],
            targets=targets,
            total_portfolio_value=metrics["total_net_liquidation"],
        )
        if "error" in drift_result:
            logger.info("drift alert skipped: %s", drift_result["error"])
            return

        if drift_result["max_drift_abs_pct"] < DRIFT_ALERT_THRESHOLD_PCT:
            logger.info(
                "drift alert skipped: max drift %.1f%% below threshold %.1f%%",
                drift_result["max_drift_abs_pct"],
                DRIFT_ALERT_THRESHOLD_PCT,
            )
            return

        top_drifts = sorted(
            drift_result["drift"], key=lambda r: abs(r["drift_pct"]), reverse=True
        )[:3]
        key = _fingerprint(user_id, report.get("report_date", ""), str(top_drifts))

        if not should_fire(_DRIFT_ALERT_TRIGGER, user_id=user_id, fingerprint=key):
            logger.info("drift alert skipped: trigger dedup")
            return

        lines = []
        for row in drift_result["drift"]:
            if row["drift_pct"] > 0:
                emoji, direction, trade_dir = "🔴", "超配", "卖出"
            else:
                emoji, direction, trade_dir = "🟡", "低配", "买入"
            trade_abs = abs(row["suggested_trade_base"])
            lines.append(
                f"{emoji} {row['symbol']}：{direction} {abs(row['drift_pct']):.1f}%"
                f"（建议{trade_dir} ${trade_abs:,.0f}）"
            )

        await _send(
            context,
            user_id,
            "<b>仓位偏离预警</b>\n\n"
            + "\n".join(lines)
            + f"\n\n最大偏离：{drift_result['max_drift_symbol']} "
            + f"{drift_result['max_drift_abs_pct']:.1f}%（阈值 {DRIFT_ALERT_THRESHOLD_PCT:.0f}%）",
        )
        record_fire(_DRIFT_ALERT_TRIGGER, user_id=user_id, fingerprint=key)
    except Exception:
        logger.exception("drift alert job failed")
```

- [ ] **Step 5: Run the new tests**

Run: `pytest tests/bot/test_proactive.py::test_drift_alert_job_fires_when_drift_exceeds_threshold tests/bot/test_proactive.py::test_drift_alert_job_skips_when_drift_below_threshold tests/bot/test_proactive.py::test_drift_alert_job_skips_when_no_targets -v`
Expected: 3 PASSED

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add bot/proactive.py tests/bot/test_proactive.py
git commit -m "feat(proactive): drift_alert_job — push when portfolio drifts from target"
```

---

### Task 3.3: Scheduler Registration + Phase Verification

**Files:**
- Modify: `bot/scheduler.py`

- [ ] **Step 1: Add DRIFT_ALERT config import and job registration to `bot/scheduler.py`**

In `bot/scheduler.py`, update the config imports to include the new vars:

```python
from config import (
    DAILY_SNAPSHOT_ENABLED,
    DAILY_SNAPSHOT_NOTIFY,
    DAILY_SNAPSHOT_TIME,
    DAILY_SNAPSHOT_USER_ID,
    DRIFT_ALERT_ENABLED,
    DRIFT_ALERT_USER_ID,
    PROACTIVE_ALERT_ENABLED,
    PROACTIVE_ALERT_TIME,
    PROACTIVE_ALERT_USER_ID,
    PROACTIVE_BRIEF_ENABLED,
    PROACTIVE_BRIEF_TIME,
    PROACTIVE_BRIEF_USER_ID,
    PROACTIVE_NEWS_ENABLED,
    PROACTIVE_NEWS_INTERVAL_MINUTES,
    PROACTIVE_NEWS_USER_ID,
)
from bot.proactive import drift_alert_job, news_monitor_job, opening_brief_job, threshold_alert_job
```

Then, in `setup_jobs`, add the drift alert registration after the `PROACTIVE_NEWS_ENABLED` block:

```python
    if DRIFT_ALERT_ENABLED:
        if DRIFT_ALERT_USER_ID is None:
            raise RuntimeError("DRIFT_ALERT_USER_ID is required when drift alerts are enabled")
        app.job_queue.run_daily(
            drift_alert_job,
            time=time(9, 0, tzinfo=APP_TIMEZONE),
            name="drift_alert",
        )
        logger.info("drift alert job scheduled daily at 09:00")
```

Also add `from config import ... APP_TIMEZONE` if not already imported. Check that `APP_TIMEZONE` is accessible — it is imported via the existing `from config import` block. Add it to the imports:

```python
from config import (
    APP_TIMEZONE,
    DAILY_SNAPSHOT_ENABLED,
    ...
)
```

And add the `time` import at the top of `bot/scheduler.py` if not present:

```python
from datetime import time
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -q`
Expected: all green

- [ ] **Step 3: Update README.md**

In `README.md`:

1. Under `## 当前状态`, update V2 Iteration 1 section title and add an **V2 Iteration 2（已落地）** section:
   ```
   ### V2 Iteration 2（已落地）
   - **目标仓位管理**：`/settarget` 存储目标配置，`get_rebalancing_suggestion` 工具分析偏差
   - **调仓建议**：AI 可回答"当前哪些标的需要买入/卖出"
   - **开盘简报增强**：加入昨日净值变动趋势行
   - **仓位偏离预警**：持仓偏离目标超阈值时自动推送（`DRIFT_ALERT_ENABLED=true`）
   ```

2. Under `## V2 Roadmap`, update Risk Sentinel row:
   ```
   | 4 | Risk Sentinel Agent | 🔜 待开发（Trigger + Drift 基础设施已就绪）|
   ```

3. Under `## 目录结构`, add the new files with ★ markers:
   ```
   storage/allocation_store.py    ★ 目标仓位 CRUD
   agent/rebalancing.py           ★ 调仓偏差引擎（纯 Python）
   agent/tools/rebalancing.py     ★ get_rebalancing_suggestion 工具
   ```

4. Under `## 环境变量`, add:
   ```
   DRIFT_ALERT_ENABLED        仓位偏离预警开关（默认 false）
   DRIFT_ALERT_THRESHOLD_PCT  触发预警的最大偏离阈值，单位百分点（默认 10.0）
   ```

- [ ] **Step 4: Commit docs**

```bash
git add bot/scheduler.py README.md
git commit -m "feat(scheduler): register drift_alert_job; docs: V2 Iteration 2 summary"
```

- [ ] **Step 5: Run the final suite**

Run: `pytest -q`
Expected: all green (~107+ passing, starting from 90)

---

## Done

After all three phases:
- **New tools:** `get_rebalancing_suggestion`
- **New bot commands:** `/settarget`, `/target`
- **New scheduled job:** `drift_alert_job` (daily, threshold-gated, Trigger-cooldown-protected)
- **New abstractions:** `storage/allocation_store.py`, `agent/rebalancing.py`, `storage.portfolio_store.get_latest_portfolio_report`
- **Enhanced:** `build_opening_brief` now shows NLV trend vs yesterday
- **Test delta:** +17 tests (from 90 → ~107)
- **No new external API dependencies; 2 new env vars** (`DRIFT_ALERT_ENABLED`, `DRIFT_ALERT_THRESHOLD_PCT`)

**Next iteration candidates (not in scope here):**
- Earnings Calendar Agent — pull calendar data (e.g. from yfinance / Alpha Vantage) and alert before earnings for held tickers
- Trade Journal Agent — parse IBKR `Trades` section from Flex XML, store realized P&L in new `realized_trades` table
- Swap `agent/news_impact.py` keyword polarity scorer for an LLM call once UX is validated
- Macro Regime Agent — classify market regime (risk-on / risk-off) and adjust thresholds dynamically
