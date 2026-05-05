from agent.tools import risk as risk_tool


def test_risk_tool_passes_investor_profile_to_analyzer(monkeypatch):
    captured = {}

    monkeypatch.setattr(risk_tool, "get_cached_portfolio", lambda: {"accounts": [{"positions": []}]})
    monkeypatch.setattr(
        "agent.risk_calculator.compute_metrics",
        lambda portfolio: {
            "total_net_liquidation": 10000,
            "positions_count": 1,
            "hhi": 10000,
            "top5_concentration_pct": 100,
            "currency_exposure": {"USD": 100},
            "asset_class": {"STK": 100},
            "concentration": [{"symbol": "AAPL", "weight_pct": 100, "unrealized_pnl_pct": -5}],
            "pnl_summary": {
                "profitable_count": 0,
                "loss_count": 1,
                "total_pnl_pct": -5,
                "biggest_gainer": None,
                "biggest_loser": {"symbol": "AAPL", "unrealized_pnl_pct": -5},
            },
        },
    )
    monkeypatch.setattr(risk_tool, "current_user_id", lambda: 42)
    monkeypatch.setattr(
        risk_tool,
        "get_investor_profile",
        lambda user_id: {"risk_level": "conservative", "max_position_weight_pct": 25, "cash_floor_pct": 10},
    )
    monkeypatch.setattr(
        "agent.analyzer.analyze_risk",
        lambda metrics, profile=None: captured.update({"metrics": metrics, "profile": profile}) or "risk with profile",
    )

    assert risk_tool.execute({}) == "risk with profile"
    assert captured["profile"]["risk_level"] == "conservative"
