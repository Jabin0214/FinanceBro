import json

from agent.tools import TOOL_DEFINITIONS, execute_tool
from agent.tools import history
from agent.tools._state import reset_active_user, set_active_user


def test_history_tool_uses_active_user_and_requested_period(monkeypatch):
    calls = []

    def fake_summary(user_id, days):
        calls.append((user_id, days))
        return {
            "period_days": days,
            "snapshot_count": 2,
            "start_date": "2026-04-01",
            "end_date": "2026-04-28",
        }

    monkeypatch.setattr(history, "get_portfolio_history_summary", fake_summary)

    token = set_active_user(77)
    try:
        payload = json.loads(history.execute({"days": 7}))
    finally:
        reset_active_user(token)

    assert calls == [(77, 7)]
    assert payload["period_days"] == 7
    assert payload["snapshot_count"] == 2


def test_history_tool_defaults_to_30_days_for_invalid_input(monkeypatch):
    calls = []
    monkeypatch.setattr(
        history,
        "get_portfolio_history_summary",
        lambda user_id, days: calls.append((user_id, days)) or {"period_days": days},
    )

    token = set_active_user(88)
    try:
        payload = json.loads(history.execute({"days": 365}))
    finally:
        reset_active_user(token)

    assert calls == [(88, 30)]
    assert payload["period_days"] == 30


def test_history_tool_is_registered(monkeypatch):
    assert any(tool["name"] == "get_portfolio_history" for tool in TOOL_DEFINITIONS)
    monkeypatch.setattr(history, "get_portfolio_history_summary", lambda user_id, days: {"user_id": user_id, "days": days})

    token = set_active_user(99)
    try:
        payload = json.loads(execute_tool("get_portfolio_history", {"days": 30}))
    finally:
        reset_active_user(token)

    assert payload == {"user_id": 99, "days": 30}
