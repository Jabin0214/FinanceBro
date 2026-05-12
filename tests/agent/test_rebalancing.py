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
