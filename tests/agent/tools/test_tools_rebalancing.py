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
