from agent import analyzer


def test_build_prompt_includes_profile_discipline():
    metrics = {
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
    }

    prompt = analyzer._build_prompt(
        metrics,
        {"risk_level": "conservative", "max_position_weight_pct": 25, "cash_floor_pct": 10},
    )

    assert "【用户投资画像】" in prompt
    assert "风险偏好：conservative" in prompt
    assert "单一持仓上限：25%" in prompt
    assert "现金底线：10%" in prompt
