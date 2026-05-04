from agent.tools import TOOL_DEFINITIONS, execute_tool
from agent.tools import watchlist
from agent.tools._state import reset_active_user, set_active_user


def test_watchlist_scout_tool_uses_active_user_watchlist_and_portfolio(monkeypatch):
    calls = []
    monkeypatch.setattr(
        watchlist,
        "list_watchlist_items",
        lambda user_id: calls.append(("list", user_id)) or [{"symbol": "NVDA", "note": "AI infra"}],
    )
    monkeypatch.setattr(
        watchlist,
        "get_cached_portfolio",
        lambda: calls.append(("portfolio",)) or {"accounts": []},
    )
    monkeypatch.setattr(
        watchlist,
        "analyze_watchlist",
        lambda items, portfolio: calls.append(("analyze", items, portfolio)) or "scout result",
    )

    token = set_active_user(42)
    try:
        result = watchlist.execute({})
    finally:
        reset_active_user(token)

    assert result == "scout result"
    assert calls == [
        ("list", 42),
        ("portfolio",),
        ("analyze", [{"symbol": "NVDA", "note": "AI infra"}], {"accounts": []}),
    ]


def test_watchlist_scout_tool_is_registered(monkeypatch):
    assert any(tool["name"] == "run_watchlist_scout" for tool in TOOL_DEFINITIONS)
    monkeypatch.setattr(watchlist, "list_watchlist_items", lambda user_id: [{"symbol": "AAPL", "note": ""}])
    monkeypatch.setattr(watchlist, "get_cached_portfolio", lambda: {"accounts": []})
    monkeypatch.setattr(watchlist, "analyze_watchlist", lambda items, portfolio: "registered scout")

    token = set_active_user(99)
    try:
        result = execute_tool("run_watchlist_scout", {})
    finally:
        reset_active_user(token)

    assert result == "registered scout"
