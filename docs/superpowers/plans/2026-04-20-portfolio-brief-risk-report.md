# Portfolio Brief, Risk, and Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic daily portfolio overview that powers Telegram `/brief`, richer `/risk`, chat tool use, and consistent HTML report summary calculations without requiring IBKR TWS.

**Architecture:** Create a pure summary module that consumes the existing parsed Flex dict and returns stable metrics, risk flags, and display-ready rows. Telegram, Claude tools, `/risk`, and the HTML report all read from that shared summary instead of each recalculating portfolio structure. Tests use static sample dicts and never call IBKR, Telegram, Anthropic, or Grok.

**Tech Stack:** Python 3, python-telegram-bot, Anthropic tool schemas, requests for Grok, pytest for unit tests, existing IBKR Flex parser data shape.

---

## File Structure

- Create `agent/portfolio_summary.py`: pure portfolio summary calculation and local fallback text helpers.
- Create `report/brief_formatter.py`: Telegram HTML formatter for `/brief` and local `/risk` fallback.
- Create `tests/test_portfolio_summary.py`: deterministic summary tests with static portfolio dicts.
- Create `tests/test_brief_formatter.py`: Telegram formatting and splitting tests.
- Modify `agent/tools.py`: add cached portfolio fetch helper, `get_portfolio_brief` tool, and summary-aware risk analysis.
- Modify `agent/analyzer.py`: accept optional deterministic summary context in Grok risk prompt.
- Modify `agent/orchestrator.py`: guide Claude to use `get_portfolio_brief` for overview questions.
- Modify `bot/telegram_bot.py`: add `/brief` command and update `/start`.
- Modify `report/html_report.py`: replace private `_portfolio_metrics()` calculations with shared summary data while keeping HTML shape.
- Modify `requirements.txt`: add `pytest>=8.0.0` if tests are introduced and pytest is not already installed.

---

### Task 1: Shared Portfolio Summary Module

**Files:**
- Create: `agent/portfolio_summary.py`
- Create: `tests/test_portfolio_summary.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest dependency**

Add this line to `requirements.txt`:

```txt
pytest>=8.0.0
```

- [ ] **Step 2: Write failing summary tests**

Create `tests/test_portfolio_summary.py`:

```python
from agent.portfolio_summary import build_portfolio_summary


def _account(account_id, base_currency, net, stock, cash, pnl, cost, positions):
    return {
        "account_id": account_id,
        "alias": account_id,
        "base_currency": base_currency,
        "summary": {
            "net_liquidation": net,
            "stock_value_base": stock,
            "cash_base": cash,
            "total_unrealized_pnl_base": pnl,
            "total_cost_base": cost,
            "total_unrealized_pnl_pct": (pnl / cost * 100) if cost else 0,
        },
        "positions": positions,
        "cash_balances": [
            {"currency": base_currency, "ending_cash": cash, "ending_cash_base": cash}
        ],
    }


def _position(symbol, mv, pnl, cost, pct=None):
    return {
        "symbol": symbol,
        "description": f"{symbol} Inc",
        "asset_category": "STK",
        "currency": "USD",
        "quantity": 10,
        "cost_price": cost / 10 if cost else 0,
        "mark_price": mv / 10 if mv else 0,
        "market_value": mv,
        "market_value_base": mv,
        "cost_basis": cost,
        "cost_basis_base": cost,
        "unrealized_pnl": pnl,
        "unrealized_pnl_base": pnl,
        "unrealized_pnl_pct": pct if pct is not None else ((pnl / cost * 100) if cost else 0),
        "fx_rate": 1.0,
    }


def test_single_account_summary_computes_totals_and_risk_flags():
    data = {
        "generated_at": "2026-04-20 09:00:00",
        "report_date": "2026-04-20",
        "accounts": [
            _account(
                "U1",
                "USD",
                100_000,
                82_000,
                18_000,
                2_000,
                80_000,
                [
                    _position("AAPL", 30_000, 3_000, 27_000, 11.11),
                    _position("MSFT", 20_000, -1_000, 21_000, -4.76),
                    _position("SPY", 12_000, 500, 11_500, 4.35),
                    _position("QQQ", 10_000, -250, 10_250, -2.44),
                    _position("NVDA", 10_000, 1_500, 8_500, 17.65),
                ],
            )
        ],
    }

    summary = build_portfolio_summary(data)

    assert summary["can_consolidate"] is True
    assert summary["base_currency"] == "USD"
    assert summary["totals"]["net_liquidation"] == 100_000
    assert summary["ratios"]["cash_pct"] == 18.0
    assert summary["ratios"]["equity_pct"] == 82.0
    assert summary["risk_flags"]["cash"]["level"] == "good"
    assert summary["risk_flags"]["largest_position"]["level"] == "danger"
    assert summary["risk_flags"]["top5_concentration"]["level"] == "danger"
    assert summary["top_holdings"][0]["symbol"] == "AAPL"
    assert summary["top_winners"][0]["symbol"] == "NVDA"
    assert summary["top_losers"][0]["symbol"] == "MSFT"


def test_same_base_currency_accounts_are_consolidated():
    data = {
        "generated_at": "2026-04-20 09:00:00",
        "report_date": "2026-04-20",
        "accounts": [
            _account("U1", "USD", 50_000, 40_000, 10_000, 1_000, 39_000, [_position("SPY", 40_000, 1_000, 39_000)]),
            _account("U2", "USD", 50_000, 35_000, 15_000, -500, 35_500, [_position("QQQ", 35_000, -500, 35_500)]),
        ],
    }

    summary = build_portfolio_summary(data)

    assert summary["can_consolidate"] is True
    assert summary["totals"]["net_liquidation"] == 100_000
    assert summary["totals"]["cash"] == 25_000
    assert summary["ratios"]["cash_pct"] == 25.0
    assert [p["symbol"] for p in summary["top_holdings"]] == ["SPY", "QQQ"]


def test_different_base_currency_accounts_do_not_consolidate():
    data = {
        "generated_at": "2026-04-20 09:00:00",
        "report_date": "2026-04-20",
        "accounts": [
            _account("U1", "USD", 50_000, 40_000, 10_000, 1_000, 39_000, [_position("SPY", 40_000, 1_000, 39_000)]),
            _account("U2", "HKD", 400_000, 350_000, 50_000, -2_000, 352_000, [_position("700", 350_000, -2_000, 352_000)]),
        ],
    }

    summary = build_portfolio_summary(data)

    assert summary["can_consolidate"] is False
    assert summary["totals"]["net_liquidation"] is None
    assert summary["base_currencies"] == ["HKD", "USD"]
    assert "不同基准货币" in summary["summary_text"]


def test_risk_threshold_boundaries():
    data = {
        "generated_at": "2026-04-20 09:00:00",
        "report_date": "2026-04-20",
        "accounts": [
            _account(
                "U1",
                "USD",
                100_000,
                92_000,
                8_000,
                0,
                92_000,
                [
                    _position("A", 20_000, 0, 20_000),
                    _position("B", 15_000, 0, 15_000),
                    _position("C", 10_000, 0, 10_000),
                    _position("D", 5_000, 0, 5_000),
                    _position("E", 5_000, 0, 5_000),
                ],
            )
        ],
    }

    summary = build_portfolio_summary(data)

    assert summary["risk_flags"]["cash"]["level"] == "warn"
    assert summary["risk_flags"]["largest_position"]["level"] == "danger"
    assert summary["risk_flags"]["top5_concentration"]["level"] == "danger"


def test_empty_portfolio_returns_error_summary():
    summary = build_portfolio_summary({"generated_at": "", "report_date": "", "accounts": []})

    assert summary["error"] == "无有效账户数据"
    assert summary["can_consolidate"] is False
    assert summary["accounts"] == []
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
pytest tests/test_portfolio_summary.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'agent.portfolio_summary'`.

- [ ] **Step 4: Implement shared summary module**

Create `agent/portfolio_summary.py`:

```python
"""
Deterministic portfolio summary helpers.

This module consumes parsed IBKR Flex data only. It does not call IBKR,
Telegram, Anthropic, Grok, or the filesystem.
"""

from __future__ import annotations

from typing import Any


def build_portfolio_summary(data: dict[str, Any], top_n: int = 5) -> dict[str, Any]:
    accounts = data.get("accounts", []) or []
    if not accounts:
        return {
            "error": "无有效账户数据",
            "generated_at": data.get("generated_at", ""),
            "report_date": data.get("report_date", ""),
            "can_consolidate": False,
            "base_currency": None,
            "base_currencies": [],
            "accounts": [],
            "positions": [],
            "top_holdings": [],
            "top_winners": [],
            "top_losers": [],
            "risk_flags": {},
            "totals": {"net_liquidation": None, "stock_value": None, "cash": None, "unrealized_pnl": None, "total_cost": None},
            "ratios": {"equity_pct": None, "cash_pct": None, "other_pct": None, "unrealized_pnl_pct": None, "largest_position_pct": None, "top5_concentration_pct": None},
            "summary_text": "没有找到有效账户数据。",
        }

    base_currencies = sorted({acct.get("base_currency", "") or "USD" for acct in accounts})
    can_consolidate = len(base_currencies) == 1
    base_currency = base_currencies[0] if base_currencies else "USD"

    account_rows = [_account_row(acct) for acct in accounts]
    positions = _position_rows(accounts, can_consolidate)
    cash_balances = _cash_rows(accounts)

    if not can_consolidate:
        _sort_positions(positions, by_total=False)
        return {
            "error": None,
            "generated_at": data.get("generated_at", ""),
            "report_date": data.get("report_date", ""),
            "can_consolidate": False,
            "base_currency": base_currency,
            "base_currencies": base_currencies,
            "accounts": account_rows,
            "positions": positions,
            "cash_balances": cash_balances,
            "top_holdings": positions[:top_n],
            "top_winners": _top_winners(positions, top_n),
            "top_losers": _top_losers(positions, top_n),
            "risk_flags": {
                "consolidation": {
                    "level": "warn",
                    "label": "分账户查看",
                    "title": "检测到不同基准货币",
                    "detail": "组合总额和跨账户比例已停用，避免把不同基准货币直接相加。",
                }
            },
            "totals": {"net_liquidation": None, "stock_value": None, "cash": None, "unrealized_pnl": None, "total_cost": None},
            "ratios": {"equity_pct": None, "cash_pct": None, "other_pct": None, "unrealized_pnl_pct": None, "largest_position_pct": None, "top5_concentration_pct": None},
            "summary_text": f"检测到不同基准货币账户（{' / '.join(base_currencies)}），已关闭跨账户合并。",
        }

    totals = _totals(accounts)
    _add_position_weights(positions, totals["net_liquidation"])
    _sort_positions(positions, by_total=True)

    ratios = _ratios(totals, positions)
    risk_flags = {
        "cash": _flag("现金缓冲", ratios["cash_pct"], _cash_level(ratios["cash_pct"]), f"现金占比 {_pct(ratios['cash_pct'])}"),
        "largest_position": _flag("最大单一持仓", ratios["largest_position_pct"], _risk_level(ratios["largest_position_pct"], 10, 20), f"最大持仓占比 {_pct(ratios['largest_position_pct'])}"),
        "top5_concentration": _flag("前五持仓集中度", ratios["top5_concentration_pct"], _risk_level(ratios["top5_concentration_pct"], 35, 55), f"前五大持仓占比 {_pct(ratios['top5_concentration_pct'])}"),
    }

    return {
        "error": None,
        "generated_at": data.get("generated_at", ""),
        "report_date": data.get("report_date", ""),
        "can_consolidate": True,
        "base_currency": base_currency,
        "base_currencies": base_currencies,
        "accounts": account_rows,
        "positions": positions,
        "cash_balances": cash_balances,
        "top_holdings": positions[:top_n],
        "top_winners": _top_winners(positions, top_n),
        "top_losers": _top_losers(positions, top_n),
        "risk_flags": risk_flags,
        "totals": totals,
        "ratios": ratios,
        "summary_text": _summary_text(totals, ratios, risk_flags, base_currency),
    }


def _account_row(acct: dict[str, Any]) -> dict[str, Any]:
    summary = acct.get("summary", {})
    net = _num(summary.get("net_liquidation"))
    cash = _num(summary.get("cash_base"))
    return {
        "account_id": acct.get("account_id", ""),
        "alias": acct.get("alias") or acct.get("account_id", ""),
        "base_currency": acct.get("base_currency", "USD"),
        "net_liquidation": net,
        "stock_value": _num(summary.get("stock_value_base")),
        "cash": cash,
        "cash_pct": round(cash / net * 100, 2) if net else 0.0,
        "unrealized_pnl": _num(summary.get("total_unrealized_pnl_base")),
        "unrealized_pnl_pct": _num(summary.get("total_unrealized_pnl_pct")),
        "position_count": len(acct.get("positions", []) or []),
    }


def _position_rows(accounts: list[dict[str, Any]], can_consolidate: bool) -> list[dict[str, Any]]:
    rows = []
    for acct in accounts:
        alias = acct.get("alias") or acct.get("account_id", "")
        account_net = _num(acct.get("summary", {}).get("net_liquidation"))
        for pos in acct.get("positions", []) or []:
            market_value_base = _num(pos.get("market_value_base"))
            account_weight = round(market_value_base / account_net * 100, 2) if account_net else 0.0
            row = dict(pos)
            row.update({
                "account_label": alias,
                "account_id": acct.get("account_id", ""),
                "base_currency": acct.get("base_currency", "USD"),
                "market_value_base": market_value_base,
                "unrealized_pnl_base": _num(pos.get("unrealized_pnl_base")),
                "unrealized_pnl_pct": _num(pos.get("unrealized_pnl_pct")),
                "account_weight_pct": account_weight,
                "weight_pct": account_weight if not can_consolidate else 0.0,
            })
            rows.append(row)
    return rows


def _cash_rows(accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for acct in accounts:
        alias = acct.get("alias") or acct.get("account_id", "")
        for cash in acct.get("cash_balances", []) or []:
            row = dict(cash)
            row["account_label"] = alias
            row["account_id"] = acct.get("account_id", "")
            rows.append(row)
    return rows


def _totals(accounts: list[dict[str, Any]]) -> dict[str, float]:
    total_net = sum(_num(a.get("summary", {}).get("net_liquidation")) for a in accounts)
    total_stock = sum(_num(a.get("summary", {}).get("stock_value_base")) for a in accounts)
    total_cash = sum(_num(a.get("summary", {}).get("cash_base")) for a in accounts)
    total_pnl = sum(_num(a.get("summary", {}).get("total_unrealized_pnl_base")) for a in accounts)
    total_cost = sum(_num(a.get("summary", {}).get("total_cost_base")) for a in accounts)
    return {
        "net_liquidation": round(total_net, 2),
        "stock_value": round(total_stock, 2),
        "cash": round(total_cash, 2),
        "unrealized_pnl": round(total_pnl, 2),
        "total_cost": round(total_cost, 2),
    }


def _add_position_weights(positions: list[dict[str, Any]], total_net: float) -> None:
    for pos in positions:
        pos["weight_pct"] = round(pos["market_value_base"] / total_net * 100, 2) if total_net else 0.0


def _sort_positions(positions: list[dict[str, Any]], by_total: bool) -> None:
    key = "market_value_base" if by_total else "account_weight_pct"
    positions.sort(key=lambda item: item.get(key, 0.0), reverse=True)


def _ratios(totals: dict[str, float], positions: list[dict[str, Any]]) -> dict[str, float]:
    net = totals["net_liquidation"]
    stock = totals["stock_value"]
    cash = totals["cash"]
    cost = totals["total_cost"]
    other = max(net - stock - cash, 0.0) if net else 0.0
    top5_value = sum(_num(p.get("market_value_base")) for p in positions[:5])
    return {
        "equity_pct": round(stock / net * 100, 2) if net else 0.0,
        "cash_pct": round(cash / net * 100, 2) if net else 0.0,
        "other_pct": round(other / net * 100, 2) if net else 0.0,
        "unrealized_pnl_pct": round(totals["unrealized_pnl"] / cost * 100, 2) if cost else 0.0,
        "largest_position_pct": round(positions[0]["weight_pct"], 2) if positions else 0.0,
        "top5_concentration_pct": round(top5_value / net * 100, 2) if net else 0.0,
    }


def _top_winners(positions: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    return sorted(positions, key=lambda p: p.get("unrealized_pnl_pct", 0.0), reverse=True)[:top_n]


def _top_losers(positions: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    return sorted(positions, key=lambda p: p.get("unrealized_pnl_pct", 0.0))[:top_n]


def _flag(title: str, value: float, level: str, detail: str) -> dict[str, Any]:
    return {"level": level, "label": _level_label(level), "title": title, "value": round(value, 2), "detail": detail}


def _risk_level(value: float, low: float, high: float) -> str:
    if value >= high:
        return "danger"
    if value >= low:
        return "warn"
    return "good"


def _cash_level(value: float) -> str:
    if value < 8:
        return "danger"
    if value < 18:
        return "warn"
    return "good"


def _level_label(level: str) -> str:
    return {"good": "相对稳健", "warn": "需要留意", "danger": "重点关注"}[level]


def _summary_text(totals: dict[str, float], ratios: dict[str, float], flags: dict[str, Any], base_currency: str) -> str:
    pnl_phrase = "账面盈利" if totals["unrealized_pnl"] >= 0 else "账面亏损"
    return (
        f"总资产约 {_money(totals['net_liquidation'])} {base_currency}，"
        f"当前{pnl_phrase} {_money(totals['unrealized_pnl'])} {base_currency}。"
        f"现金占比 {_pct(ratios['cash_pct'])}，"
        f"前五持仓集中度 {_pct(ratios['top5_concentration_pct'])}（{flags['top5_concentration']['label']}）。"
    )


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _pct(value: float) -> str:
    return f"{value:.1f}%"
```

- [ ] **Step 5: Run summary tests**

Run:

```bash
pytest tests/test_portfolio_summary.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add requirements.txt agent/portfolio_summary.py tests/test_portfolio_summary.py
git commit -m "feat: add portfolio summary metrics"
```

---

### Task 2: Telegram Brief Formatter and `/brief` Command

**Files:**
- Create: `report/brief_formatter.py`
- Create: `tests/test_brief_formatter.py`
- Modify: `bot/telegram_bot.py`
- Modify: `agent/tools.py`

- [ ] **Step 1: Write failing formatter tests**

Create `tests/test_brief_formatter.py`:

```python
from report.brief_formatter import build_brief_messages, build_local_risk_fallback


def _summary():
    return {
        "error": None,
        "report_date": "2026-04-20",
        "generated_at": "2026-04-20 09:00:00",
        "can_consolidate": True,
        "base_currency": "USD",
        "base_currencies": ["USD"],
        "summary_text": "总资产约 100,000.00 USD，当前账面盈利 2,000.00 USD。",
        "totals": {"net_liquidation": 100000, "stock_value": 82000, "cash": 18000, "unrealized_pnl": 2000, "total_cost": 80000},
        "ratios": {"equity_pct": 82.0, "cash_pct": 18.0, "other_pct": 0.0, "unrealized_pnl_pct": 2.5, "largest_position_pct": 30.0, "top5_concentration_pct": 82.0},
        "risk_flags": {
            "cash": {"level": "good", "label": "相对稳健", "title": "现金缓冲", "detail": "现金占比 18.0%"},
            "largest_position": {"level": "danger", "label": "重点关注", "title": "最大单一持仓", "detail": "最大持仓占比 30.0%"},
            "top5_concentration": {"level": "danger", "label": "重点关注", "title": "前五持仓集中度", "detail": "前五大持仓占比 82.0%"},
        },
        "top_holdings": [
            {"symbol": "AAPL", "description": "Apple", "weight_pct": 30.0, "market_value_base": 30000, "unrealized_pnl_pct": 10.0, "unrealized_pnl_base": 3000},
            {"symbol": "MSFT", "description": "Microsoft", "weight_pct": 20.0, "market_value_base": 20000, "unrealized_pnl_pct": -5.0, "unrealized_pnl_base": -1000},
        ],
        "top_winners": [
            {"symbol": "AAPL", "unrealized_pnl_pct": 10.0, "unrealized_pnl_base": 3000},
        ],
        "top_losers": [
            {"symbol": "MSFT", "unrealized_pnl_pct": -5.0, "unrealized_pnl_base": -1000},
        ],
    }


def test_build_brief_messages_contains_key_sections():
    messages = build_brief_messages(_summary())
    text = "\n".join(messages)

    assert "<b>FinanceBro Brief</b>" in text
    assert "总资产" in text
    assert "风险灯" in text
    assert "AAPL" in text
    assert "MSFT" in text
    assert all(len(message) <= 4000 for message in messages)


def test_local_risk_fallback_mentions_grok_unavailable():
    text = build_local_risk_fallback(_summary(), "Grok API Key 未配置")

    assert "市场上下文分析暂不可用" in text
    assert "Grok API Key 未配置" in text
    assert "前五持仓集中度" in text
```

- [ ] **Step 2: Run formatter tests and verify they fail**

Run:

```bash
pytest tests/test_brief_formatter.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'report.brief_formatter'`.

- [ ] **Step 3: Implement brief formatter**

Create `report/brief_formatter.py`:

```python
from __future__ import annotations

from html import escape
from typing import Any

MAX_MSG_LEN = 4000


def build_brief_messages(summary: dict[str, Any]) -> list[str]:
    if summary.get("error"):
        return [f"❌ <b>组合概览失败</b>\n<code>{escape(summary['error'])}</code>"]

    if not summary.get("can_consolidate"):
        text = _mixed_currency_brief(summary)
    else:
        text = _consolidated_brief(summary)
    return _split(text)


def build_local_risk_fallback(summary: dict[str, Any], reason: str) -> str:
    if summary.get("error"):
        return f"❌ <b>风险分析失败</b>\n<code>{escape(summary['error'])}</code>"

    lines = [
        "<b>本地风险概览</b>",
        "",
        "市场上下文分析暂不可用，先返回基于 IBKR Flex 的本地风险灯。",
        f"<i>原因：{escape(reason)}</i>",
        "",
    ]
    lines.extend(_risk_lines(summary))
    lines.append("")
    lines.append("<i>仅供账户结构观察，不构成投资建议。</i>")
    return "\n".join(lines)


def _consolidated_brief(summary: dict[str, Any]) -> str:
    totals = summary["totals"]
    ratios = summary["ratios"]
    ccy = summary["base_currency"]
    lines = [
        f"<b>FinanceBro Brief</b>  <code>{escape(summary.get('report_date') or '-')}</code>",
        "",
        escape(summary["summary_text"]),
        "",
        "<b>账户</b>",
        f"总资产　{_money(totals['net_liquidation'])} {escape(ccy)}",
        f"股票　　{_money(totals['stock_value'])} {escape(ccy)}　{_pct(ratios['equity_pct'])}",
        f"现金　　{_money(totals['cash'])} {escape(ccy)}　{_pct(ratios['cash_pct'])}",
        f"账面盈亏　{_pnl(totals['unrealized_pnl'])} {escape(ccy)}　{_signed_pct(ratios['unrealized_pnl_pct'])}",
        "",
        "<b>风险灯</b>",
    ]
    lines.extend(_risk_lines(summary))
    lines.extend(["", "<b>Top 持仓</b>"])
    lines.extend(_holding_lines(summary.get("top_holdings", [])))
    lines.extend(["", "<b>赢家 / 输家</b>"])
    lines.extend(_winner_loser_lines(summary))
    lines.extend(["", f"<i>数据来自 IBKR Flex 快照：{escape(summary.get('generated_at') or '-')}</i>"])
    return "\n".join(lines)


def _mixed_currency_brief(summary: dict[str, Any]) -> str:
    lines = [
        f"<b>FinanceBro Brief</b>  <code>{escape(summary.get('report_date') or '-')}</code>",
        "",
        escape(summary["summary_text"]),
        "",
        "<b>分账户</b>",
    ]
    for acct in summary.get("accounts", []):
        ccy = acct["base_currency"]
        lines.append(
            f"• <b>{escape(acct['alias'])}</b>：净值 {_money(acct['net_liquidation'])} {escape(ccy)}，"
            f"现金 {_pct(acct['cash_pct'])}，盈亏 {_pnl(acct['unrealized_pnl'])} {escape(ccy)}"
        )
    lines.append("")
    lines.append("<i>不同基准货币账户未合并计算总风险灯。</i>")
    return "\n".join(lines)


def _risk_lines(summary: dict[str, Any]) -> list[str]:
    order = ["cash", "largest_position", "top5_concentration", "consolidation"]
    lines = []
    for key in order:
        item = summary.get("risk_flags", {}).get(key)
        if item:
            lines.append(f"{_level_icon(item['level'])} <b>{escape(item['title'])}</b>：{escape(item['detail'])}（{escape(item['label'])}）")
    return lines


def _holding_lines(holdings: list[dict[str, Any]]) -> list[str]:
    if not holdings:
        return ["<i>暂无持仓</i>"]
    return [
        f"• <b>{escape(item['symbol'])}</b>　{_pct(item.get('weight_pct', 0))}　"
        f"盈亏 {_signed_pct(item.get('unrealized_pnl_pct', 0))}"
        for item in holdings[:5]
    ]


def _winner_loser_lines(summary: dict[str, Any]) -> list[str]:
    winner = (summary.get("top_winners") or [None])[0]
    loser = (summary.get("top_losers") or [None])[0]
    lines = []
    if winner:
        lines.append(f"🟢 最强：<b>{escape(winner['symbol'])}</b> {_signed_pct(winner.get('unrealized_pnl_pct', 0))}")
    if loser:
        lines.append(f"🔴 最弱：<b>{escape(loser['symbol'])}</b> {_signed_pct(loser.get('unrealized_pnl_pct', 0))}")
    return lines or ["<i>暂无盈亏数据</i>"]


def _level_icon(level: str) -> str:
    return {"good": "🟢", "warn": "🟡", "danger": "🔴"}.get(level, "⚪")


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def _pnl(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.2f}"


def _split(text: str) -> list[str]:
    if len(text) <= MAX_MSG_LEN:
        return [text]
    parts = []
    current = ""
    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= MAX_MSG_LEN:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = para
    if current:
        parts.append(current)
    return parts
```

- [ ] **Step 4: Add cached portfolio fetch helper in tools**

Modify `agent/tools.py` by adding this helper near `_get_portfolio()`:

```python
def get_cached_portfolio_data() -> dict:
    """Fetch portfolio data using the shared in-memory cache."""
    global _portfolio_cache, _portfolio_cache_ts
    from ibkr.flex_query import fetch_flex_report

    now = time.time()
    if _portfolio_cache and now - _portfolio_cache_ts < _PORTFOLIO_CACHE_TTL:
        logger.info("使用缓存持仓数据（剩余 %.0fs）", _PORTFOLIO_CACHE_TTL - (now - _portfolio_cache_ts))
        return _portfolio_cache

    data = fetch_flex_report()
    _portfolio_cache = data
    _portfolio_cache_ts = time.time()
    return data
```

Then replace the duplicated fetch/cache blocks in `_get_portfolio()`, `_generate_report()`, and `_get_risk_analysis()` with:

```python
data = get_cached_portfolio_data()
```

- [ ] **Step 5: Add `/brief` command**

Modify `bot/telegram_bot.py` imports:

```python
from agent.tools import pop_pending_files, set_active_user, reset_active_user, run_risk_analysis, get_cached_portfolio_data
from agent.portfolio_summary import build_portfolio_summary
from report.brief_formatter import build_brief_messages
```

Add command handler:

```python
async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ 未授权")
        return

    status_msg = await update.message.reply_text("⏳ 正在生成组合概览...")

    try:
        raw_data = await asyncio.to_thread(get_cached_portfolio_data)
        summary = build_portfolio_summary(raw_data)
        await status_msg.delete()
        for chunk in build_brief_messages(summary):
            try:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            except BadRequest:
                await update.message.reply_text(chunk)
    except Exception as e:
        logger.exception("组合概览失败：%s", e)
        await status_msg.edit_text(
            f"❌ <b>组合概览失败</b>\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML,
        )
```

Update `/start` text to include:

```python
"/brief  — 一键组合概览（资产、现金、Top 持仓、风险灯）\n"
```

Register command in `build_app()`:

```python
app.add_handler(CommandHandler("brief", cmd_brief))
```

- [ ] **Step 6: Run formatter tests and import check**

Run:

```bash
pytest tests/test_brief_formatter.py tests/test_portfolio_summary.py -v
python -m compileall agent report bot
```

Expected: tests pass and compileall reports no syntax errors.

- [ ] **Step 7: Commit**

Run:

```bash
git add agent/tools.py bot/telegram_bot.py report/brief_formatter.py tests/test_brief_formatter.py
git commit -m "feat: add telegram portfolio brief"
```

---

### Task 3: Claude Brief Tool and Prompt Guidance

**Files:**
- Modify: `agent/tools.py`
- Modify: `agent/orchestrator.py`

- [ ] **Step 1: Add `get_portfolio_brief` tool schema**

In `agent/tools.py`, add this item to `TOOL_DEFINITIONS` after `get_portfolio`:

```python
{
    "name": "get_portfolio_brief",
    "description": (
        "获取 IBKR 账户的一屏组合概览，包括总资产、现金占比、股票仓位、"
        "Top 持仓、Top winners/losers、集中度和风险灯。"
        "用于回答用户关于今天账户怎么样、组合概览、风险灯、哪些仓位拖累表现等摘要型问题。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
},
```

- [ ] **Step 2: Add tool execution branch**

In `execute_tool()` add:

```python
if name == "get_portfolio_brief":
    return _get_portfolio_brief()
```

Add function:

```python
def _get_portfolio_brief() -> str:
    from agent.portfolio_summary import build_portfolio_summary

    logger.info("工具调用: get_portfolio_brief")
    data = get_cached_portfolio_data()
    summary = build_portfolio_summary(data)
    return json.dumps(summary, ensure_ascii=False)
```

- [ ] **Step 3: Update orchestrator prompt**

Modify `SYSTEM_PROMPT` in `agent/orchestrator.py` by adding this guidance after the portfolio data rule:

```text
如果用户的问题是摘要型组合概览，例如“今天账户怎么样”“组合概览”“风险灯”“哪些仓位表现最好/最差”，优先调用 get_portfolio_brief。
如果用户要求完整明细或原始持仓数据，再调用 get_portfolio。
如果用户要求深度风险分析、组合健康度、市场背景下的风险解读，调用 get_risk_analysis。
```

- [ ] **Step 4: Run compile check**

Run:

```bash
python -m compileall agent
```

Expected: no syntax errors.

- [ ] **Step 5: Commit**

Run:

```bash
git add agent/tools.py agent/orchestrator.py
git commit -m "feat: expose portfolio brief tool"
```

---

### Task 4: Summary-Aware `/risk` and Local Fallback

**Files:**
- Modify: `agent/tools.py`
- Modify: `agent/analyzer.py`
- Modify: `report/brief_formatter.py`

- [ ] **Step 1: Inspect current analyzer signature**

Run:

```bash
sed -n '1,260p' agent/analyzer.py
```

Expected: find `analyze_risk(metrics)` and the Grok request payload.

- [ ] **Step 2: Modify analyzer signature**

Change:

```python
def analyze_risk(metrics: dict) -> str:
```

to:

```python
def analyze_risk(metrics: dict, portfolio_summary: dict | None = None) -> str:
```

In the request prompt, include summary context:

```python
summary_context = ""
if portfolio_summary:
    summary_context = (
        "\n\n组合摘要与风险灯：\n"
        f"{json.dumps(portfolio_summary, ensure_ascii=False)[:6000]}"
    )
```

Append `summary_context` to the user content sent to Grok.

- [ ] **Step 3: Add local fallback in tools**

Modify `_get_risk_analysis()` in `agent/tools.py`:

```python
def _get_risk_analysis() -> str:
    from agent.risk_calculator import compute_metrics
    from agent.analyzer import analyze_risk
    from agent.portfolio_summary import build_portfolio_summary
    from report.brief_formatter import build_local_risk_fallback

    logger.info("工具调用: get_risk_analysis — 正在获取持仓数据...")
    data = get_cached_portfolio_data()

    summary = build_portfolio_summary(data)
    metrics = compute_metrics(data)
    if "error" in metrics:
        if summary.get("error"):
            return f"风险分析失败：{metrics['error']}"
        return build_local_risk_fallback(summary, metrics["error"])

    logger.info("工具调用: get_risk_analysis — 正在调用 Grok 进行风险评估...")
    try:
        return analyze_risk(metrics, portfolio_summary=summary)
    except Exception as e:
        logger.exception("Grok 风险分析失败，降级为本地风险概览")
        return build_local_risk_fallback(summary, str(e))
```

- [ ] **Step 4: Ensure analyzer raises on missing Grok key or preserve error fallback**

If `analyze_risk()` currently returns a string for missing `GROK_API_KEY`, keep that behavior only if the string is useful. Prefer raising:

```python
if not GROK_API_KEY:
    raise RuntimeError("未配置 GROK_API_KEY")
```

This allows `_get_risk_analysis()` to produce the local fallback.

- [ ] **Step 5: Run compile and targeted tests**

Run:

```bash
pytest tests/test_portfolio_summary.py tests/test_brief_formatter.py -v
python -m compileall agent report
```

Expected: tests pass and compileall reports no syntax errors.

- [ ] **Step 6: Commit**

Run:

```bash
git add agent/tools.py agent/analyzer.py report/brief_formatter.py
git commit -m "feat: add local risk fallback"
```

---

### Task 5: HTML Report Uses Shared Summary

**Files:**
- Modify: `report/html_report.py`
- Test: `tests/test_portfolio_summary.py`

- [ ] **Step 1: Import shared summary**

Add near the top of `report/html_report.py`:

```python
from agent.portfolio_summary import build_portfolio_summary
```

- [ ] **Step 2: Use shared summary in `_render_html`**

Change:

```python
metrics = _portfolio_metrics(accounts)
```

to:

```python
summary = build_portfolio_summary(data)
metrics = _portfolio_metrics_from_summary(summary)
```

- [ ] **Step 3: Add adapter function**

Replace the body of `_portfolio_metrics(accounts: list[dict])` with an adapter or add a new function:

```python
def _portfolio_metrics_from_summary(summary: dict) -> dict:
    totals = summary["totals"]
    ratios = summary["ratios"]
    return {
        "account_count": len(summary["accounts"]),
        "can_consolidate": summary["can_consolidate"],
        "base_currency": summary["base_currency"] or "-",
        "base_currencies": summary["base_currencies"],
        "positions": summary["positions"],
        "cash_balances": summary.get("cash_balances", []),
        "total_net": totals["net_liquidation"] or 0.0,
        "total_stock": totals["stock_value"] or 0.0,
        "total_cash": totals["cash"] or 0.0,
        "other_assets": max((totals["net_liquidation"] or 0.0) - (totals["stock_value"] or 0.0) - (totals["cash"] or 0.0), 0.0),
        "total_pnl": totals["unrealized_pnl"] or 0.0,
        "total_cost": totals["total_cost"] or 0.0,
        "total_pnl_pct": ratios["unrealized_pnl_pct"] or 0.0,
        "position_count": len(summary["positions"]),
        "equity_ratio": ratios["equity_pct"] or 0.0,
        "cash_ratio": ratios["cash_pct"] or 0.0,
        "other_ratio": ratios["other_pct"] or 0.0,
        "largest_position_weight": ratios["largest_position_pct"] or 0.0,
        "top5_concentration": ratios["top5_concentration_pct"] or 0.0,
        "largest_position_level": summary["risk_flags"].get("largest_position", {}).get("level", "warn"),
        "top5_level": summary["risk_flags"].get("top5_concentration", {}).get("level", "warn"),
        "cash_ratio_level": summary["risk_flags"].get("cash", {}).get("level", "warn"),
        "summary_text": summary["summary_text"],
    }
```

Update `_build_summary_sentence(metrics)` to return `metrics["summary_text"]` when present:

```python
if metrics.get("summary_text"):
    return metrics["summary_text"]
```

- [ ] **Step 4: Normalize position key names used by HTML**

In `agent/portfolio_summary.py`, ensure each position row contains both key styles:

```python
row["weight"] = row["weight_pct"]
row["account_weight"] = row["account_weight_pct"]
```

Add these assignments after weights are calculated for consolidated and multi-currency paths.

- [ ] **Step 5: Run render smoke test**

Run:

```bash
python - <<'PY'
from report.html_report import _render_html

data = {
    "generated_at": "2026-04-20 09:00:00",
    "report_date": "2026-04-20",
    "accounts": [{
        "account_id": "U1",
        "alias": "U1",
        "base_currency": "USD",
        "summary": {"net_liquidation": 100000, "stock_value_base": 82000, "cash_base": 18000, "total_unrealized_pnl_base": 2000, "total_cost_base": 80000, "total_unrealized_pnl_pct": 2.5},
        "positions": [{
            "symbol": "AAPL", "description": "Apple", "asset_category": "STK", "currency": "USD",
            "quantity": 10, "cost_price": 2700, "mark_price": 3000, "market_value": 30000,
            "market_value_base": 30000, "cost_basis": 27000, "cost_basis_base": 27000,
            "unrealized_pnl": 3000, "unrealized_pnl_base": 3000, "unrealized_pnl_pct": 11.11,
            "fx_rate": 1.0,
        }],
        "cash_balances": [{"currency": "USD", "ending_cash": 18000, "ending_cash_base": 18000}],
    }],
}
html = _render_html(data)
assert "IBKR 账户总览" in html
assert "AAPL" in html
assert "风险" in html
print("html smoke ok")
PY
```

Expected: prints `html smoke ok`.

- [ ] **Step 6: Run tests and compile**

Run:

```bash
pytest tests/test_portfolio_summary.py tests/test_brief_formatter.py -v
python -m compileall report agent
```

Expected: tests pass and compileall reports no syntax errors.

- [ ] **Step 7: Commit**

Run:

```bash
git add agent/portfolio_summary.py report/html_report.py tests/test_portfolio_summary.py
git commit -m "refactor: share portfolio summary with html report"
```

---

### Task 6: Final Verification and Documentation Polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README command list**

In `README.md`, update the Telegram commands section in Phase 2 or add a short current commands block:

```markdown
当前 Telegram 命令：
- `/brief`：一键组合概览（资产、现金、Top 持仓、风险灯），不调用 Grok
- `/report`：生成 IBKR HTML 持仓报告
- `/risk`：持仓风险分析（本地风险灯 + Grok 市场上下文，Grok 不可用时降级为本地概览）
- `/clear`：清除当前对话历史
```

- [ ] **Step 2: Run full local verification**

Run:

```bash
pytest -v
python -m compileall .
git status --short
```

Expected:

- pytest passes.
- compileall reports no syntax errors.
- `git status --short` shows only intentional README changes before commit, or is clean after commit.

- [ ] **Step 3: Commit README and final polish**

Run:

```bash
git add README.md
git commit -m "docs: document portfolio brief command"
```

- [ ] **Step 4: Manual Telegram smoke checklist**

With env vars configured and the bot running, manually check:

```bash
python main.py
```

Then in Telegram:

- `/start` shows `/brief`.
- `/brief` returns portfolio overview and does not call Grok.
- `/report` still sends an HTML file.
- `/risk` returns Grok analysis if `GROK_API_KEY` works.
- `/risk` returns local risk fallback if `GROK_API_KEY` is temporarily unset.
- Natural text like `今天账户怎么样？` can trigger the brief tool.

Stop the bot with `Ctrl-C` after the smoke test.

