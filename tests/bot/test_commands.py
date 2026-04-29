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
    monkeypatch.setattr(handlers.proactive, "build_opening_brief", lambda data: f"brief {data['report_date']}")
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_brief(_update(), _context())

    assert sent == ["brief 2026-04-29"]


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
async def test_cmd_history_lists_snapshot_dates(monkeypatch):
    sent = []
    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "get_snapshot_dates", lambda user_id, limit=10: ["2026-04-29", "2026-04-28"])
    monkeypatch.setattr(
        handlers,
        "send_html_with_fallback",
        AsyncMock(side_effect=lambda _message, text: sent.append(text)),
    )

    await handlers.cmd_history(_update(), _context())

    assert "2026-04-29" in sent[0]
    assert "2026-04-28" in sent[0]
