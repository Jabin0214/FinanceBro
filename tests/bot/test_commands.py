from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot import handlers


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _update(user_id=42):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=99, type="private"),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )


def _context(args=None):
    return SimpleNamespace(
        args=args or [],
        bot=SimpleNamespace(send_chat_action=AsyncMock()),
    )


@pytest.mark.anyio
async def test_cmd_news_requires_query(monkeypatch):
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    update = _update()
    context = _context()

    await handlers.cmd_news(update, context)

    update.message.reply_text.assert_awaited_once()
    assert "/news AAPL" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_cmd_news_calls_news_agent(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "_get_news", lambda query: f"news for {query}")
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )
    context = _context(["AAPL", "earnings"])

    await handlers.cmd_news(_update(), context)

    assert sent == ["news for AAPL earnings"]


@pytest.mark.anyio
async def test_cmd_risk_binds_user_and_sends_result(monkeypatch):
    sent = []
    bound = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "set_active_user", lambda user_id: bound.append(user_id) or "token")
    monkeypatch.setattr(handlers, "reset_active_user", lambda token: bound.append(token))
    monkeypatch.setattr(handlers.risk_tool, "execute", lambda _input: "risk result")
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_risk(_update(user_id=77), _context())

    assert sent == ["risk result"]
    assert bound == [77, "token"]


@pytest.mark.anyio
async def test_cmd_brief_sends_opening_brief(monkeypatch):
    sent = []
    report = {"report_date": "2026-04-29", "accounts": [{"account_id": "U1"}]}
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers.proactive, "_fetch_and_save", lambda user_id: report)
    monkeypatch.setattr(handlers, "get_investor_profile", lambda user_id: {"risk_level": "balanced"})
    monkeypatch.setattr(
        handlers.proactive,
        "build_opening_brief",
        lambda data, profile=None: f"brief {data['report_date']} {profile['risk_level']}",
    )
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_brief(_update(), _context())

    assert sent == ["brief 2026-04-29 balanced"]


@pytest.mark.anyio
async def test_cmd_profile_updates_and_shows_profile(monkeypatch):
    stored = []
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(
        handlers,
        "update_investor_profile",
        lambda user_id, **fields: stored.append((user_id, fields)),
    )
    monkeypatch.setattr(
        handlers,
        "get_investor_profile",
        lambda user_id: {
            "risk_level": "balanced",
            "time_horizon": "medium",
            "max_position_weight_pct": 30.0,
            "cash_floor_pct": 8.0,
            "preferred_markets": "US",
            "notes": "learn slowly",
        },
    )
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_profile(
        _update(user_id=77),
        _context(["set", "risk", "conservative", "max", "25", "cash", "12"]),
    )
    await handlers.cmd_profile(_update(user_id=77), _context())

    assert stored == [
        (
            77,
            {
                "risk_level": "conservative",
                "max_position_weight_pct": 25.0,
                "cash_floor_pct": 12.0,
            },
        )
    ]
    assert "<b>投资画像</b>" in sent[-1]
    assert "单一持仓上限：30.0%" in sent[-1]


@pytest.mark.anyio
async def test_cmd_profile_setup_shows_guided_template(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_profile(_update(user_id=77), _context(["setup"]))

    assert "<b>投资画像设置</b>" in sent[0]
    assert "/profile set risk balanced max 35 cash 10" in sent[0]
    assert "conservative" in sent[0]


@pytest.mark.anyio
async def test_cmd_alerts_sends_no_alert_message(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers.proactive, "_fetch_and_save", lambda user_id: {"accounts": []})
    monkeypatch.setattr(handlers.proactive, "build_threshold_alerts", lambda report, pnl_threshold_pct, position_weight_threshold_pct: [])
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_alerts(_update(), _context())

    assert sent == ["🟢 当前未触发持仓阈值预警。"]


@pytest.mark.anyio
async def test_cmd_history_sends_historian_recap(monkeypatch):
    sent = []
    analyzed = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(
        handlers,
        "get_portfolio_history_summary",
        lambda user_id, days=30: {
            "period_days": days,
            "snapshot_count": 2,
            "start_date": "2026-04-01",
            "end_date": "2026-04-28",
            "totals": {
                "net_liquidation": {"start": 10000.0, "end": 12500.0, "change": 2500.0, "change_pct": 25.0},
                "cash_base": {"start": 1500.0, "end": 900.0, "change": -600.0, "change_pct": -40.0},
                "total_unrealized_pnl_base": {"start": 100.0, "end": 650.0, "change": 550.0, "change_pct": 550.0},
            },
            "position_changes": [
                {"symbol": "AAPL", "status": "increased", "quantity_change": 3.0, "market_value_change_base": 1200.0},
                {"symbol": "TSLA", "status": "closed", "quantity_change": -1.0, "market_value_change_base": -700.0},
            ],
            "top_unrealized_pnl_contributors": [
                {"symbol": "AAPL", "unrealized_pnl_base": 650.0},
            ],
        },
    )
    monkeypatch.setattr(
        handlers,
        "analyze_history",
        lambda summary: analyzed.append(summary) or "<b>一句话结论</b>\n历史复盘结果",
    )
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_history(_update(), _context())

    assert analyzed[0]["period_days"] == 30
    assert sent == ["<b>一句话结论</b>\n历史复盘结果"]


@pytest.mark.anyio
async def test_cmd_watchlist_adds_symbol_with_note(monkeypatch):
    calls = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(
        handlers,
        "add_watchlist_item",
        lambda user_id, symbol, note="": calls.append((user_id, symbol, note)),
    )
    update = _update(user_id=77)

    await handlers.cmd_watchlist(update, _context(["add", "nvda", "AI", "infra"]))

    assert calls == [(77, "nvda", "AI infra")]
    update.message.reply_text.assert_awaited_once()
    assert "NVDA" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_cmd_watchlist_lists_items(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(
        handlers,
        "list_watchlist_items",
        lambda user_id: [
            {
                "symbol": "AAPL",
                "note": "pullback",
                "status": "waiting",
                "thesis": "AI cycle",
                "trigger_price": 175.0,
                "risk_note": "valuation",
            },
            {
                "symbol": "MSFT",
                "note": "",
                "status": "watching",
                "thesis": "",
                "trigger_price": None,
                "risk_note": "",
            },
        ],
    )
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_watchlist(_update(), _context())

    assert "<b>观察列表</b>" in sent[0]
    assert "AAPL — waiting — pullback" in sent[0]
    assert "买入/跟踪触发：175.0" in sent[0]
    assert "风险点：valuation" in sent[0]
    assert "MSFT" in sent[0]


@pytest.mark.anyio
async def test_cmd_watchlist_sets_research_fields(monkeypatch):
    calls = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(
        handlers,
        "update_watchlist_research",
        lambda user_id, symbol, **fields: calls.append((user_id, symbol, fields)),
    )
    update = _update(user_id=77)

    await handlers.cmd_watchlist(
        update,
        _context(["set", "nvda", "status", "waiting", "trigger", "850", "risk", "valuation"]),
    )

    assert calls == [
        (
            77,
            "nvda",
            {
                "status": "waiting",
                "trigger_price": 850.0,
                "risk_note": "valuation",
            },
        )
    ]
    update.message.reply_text.assert_awaited_once()
    assert "NVDA" in update.message.reply_text.await_args.args[0]


@pytest.mark.anyio
async def test_cmd_scout_binds_user_and_sends_result(monkeypatch):
    sent = []
    bound = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "set_active_user", lambda user_id: bound.append(user_id) or "token")
    monkeypatch.setattr(handlers, "reset_active_user", lambda token: bound.append(token))
    monkeypatch.setattr(handlers.watchlist_tool, "execute", lambda _input: "scout result")
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_scout(_update(user_id=66), _context())

    assert sent == ["scout result"]
    assert bound == [66, "token"]
