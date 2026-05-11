import math
import pytest

from agent.risk_metrics import daily_returns, annualized_volatility


def test_daily_returns_simple():
    series = [("d1", 100.0), ("d2", 110.0), ("d3", 99.0)]
    out = daily_returns(series)
    assert out == pytest.approx([0.10, -0.10], rel=1e-6)


def test_daily_returns_skips_zero_or_negative_priors():
    series = [("d1", 0.0), ("d2", 100.0), ("d3", 110.0)]
    out = daily_returns(series)
    assert out == pytest.approx([0.10], rel=1e-6)


def test_annualized_volatility_252_trading_days():
    returns = [0.01, -0.01, 0.01, -0.01, 0.01, -0.01]
    vol = annualized_volatility(returns)
    expected = math.sqrt(sum(r * r for r in returns) / (len(returns) - 1)) * math.sqrt(252)
    assert vol == pytest.approx(expected, rel=1e-6)


def test_annualized_volatility_requires_two_points():
    assert annualized_volatility([]) == 0.0
    assert annualized_volatility([0.01]) == 0.0
