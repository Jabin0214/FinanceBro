from types import SimpleNamespace

from agent import historian


def _summary():
    return {
        "period_days": 30,
        "snapshot_count": 2,
        "start_date": "2026-04-01",
        "end_date": "2026-04-28",
        "totals": {
            "net_liquidation": {"start": 10000.0, "end": 12500.0, "change": 2500.0, "change_pct": 25.0},
            "cash_base": {"start": 1500.0, "end": 900.0, "change": -600.0, "change_pct": -40.0},
        },
        "position_changes": [
            {"symbol": "AAPL", "status": "increased", "quantity_change": 3.0},
        ],
        "top_unrealized_pnl_contributors": [
            {"symbol": "AAPL", "unrealized_pnl_base": 650.0},
        ],
    }


def test_analyze_history_invokes_claude_with_structured_summary(monkeypatch):
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text="<b>一句话结论</b>\n组合净值改善，AAPL 是主要贡献。"
                    )
                ]
            )

    monkeypatch.setattr(historian, "ANTHROPIC_API_KEY", "key")
    monkeypatch.setattr(historian, "_get_client", lambda: SimpleNamespace(messages=FakeMessages()))

    result = historian.analyze_history(_summary())

    assert "<b>一句话结论</b>" in result
    assert captured["model"] == historian.HISTORIAN_MODEL
    assert "Portfolio Historian" in captured["system"]
    assert "net_liquidation" in captured["messages"][0]["content"]
    assert "AAPL" in captured["messages"][0]["content"]


def test_analyze_history_returns_data_message_without_snapshots(monkeypatch):
    result = historian.analyze_history({"period_days": 30, "snapshot_count": 0})

    assert "暂无足够历史快照" in result


def test_analyze_history_sanitizes_markdown_and_urls(monkeypatch):
    class FakeMessages:
        def create(self, **_kwargs):
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text="<b>一句话结论</b>\n**强势** [[1]](https://example.com) https://example.com"
                    )
                ]
            )

    monkeypatch.setattr(historian, "ANTHROPIC_API_KEY", "key")
    monkeypatch.setattr(historian, "_get_client", lambda: SimpleNamespace(messages=FakeMessages()))

    result = historian.analyze_history(_summary())

    assert "**" not in result
    assert "[[1]]" not in result
    assert "https://" not in result
