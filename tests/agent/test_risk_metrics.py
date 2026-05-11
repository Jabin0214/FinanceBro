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


from agent.risk_metrics import max_drawdown


def test_max_drawdown_classic_peak_trough():
    series = [("d1", 100.0), ("d2", 120.0), ("d3", 90.0), ("d4", 110.0)]
    result = max_drawdown(series)
    assert result["max_drawdown_pct"] == pytest.approx(-25.0, rel=1e-6)
    assert result["peak_date"] == "d2"
    assert result["trough_date"] == "d3"


def test_max_drawdown_monotonic_up_is_zero():
    series = [("d1", 100.0), ("d2", 110.0), ("d3", 120.0)]
    result = max_drawdown(series)
    assert result["max_drawdown_pct"] == 0.0


def test_max_drawdown_empty_returns_zero():
    result = max_drawdown([])
    assert result["max_drawdown_pct"] == 0.0
    assert result["peak_date"] is None


from agent.risk_metrics import historical_var, historical_cvar


def test_historical_var_95_picks_5th_percentile_loss():
    returns = [-0.10, -0.08, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0,
               0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.04, 0.05,
               0.05, 0.06, 0.07, 0.08]
    var95 = historical_var(returns, confidence=0.95)
    assert var95 == pytest.approx(-0.08, rel=1e-6)


def test_historical_var_returns_zero_when_insufficient_data():
    assert historical_var([], confidence=0.95) == 0.0
    assert historical_var([0.01], confidence=0.95) == 0.0


def test_historical_cvar_is_mean_of_tail():
    returns = [-0.10, -0.08, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0,
               0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.04, 0.05,
               0.05, 0.06, 0.07, 0.08]
    cvar95 = historical_cvar(returns, confidence=0.95)
    assert cvar95 == pytest.approx(-0.10, rel=1e-6)


from agent.risk_metrics import sharpe_ratio, sortino_ratio


def test_sharpe_ratio_constant_positive_returns():
    returns = [0.001] * 30
    assert sharpe_ratio(returns) == 0.0  # zero variance returns zero


def test_sharpe_ratio_basic_shape():
    returns = [0.01, -0.005, 0.015, -0.002, 0.008]
    sr = sharpe_ratio(returns, risk_free_annual=0.0)
    assert sr > 0
    assert math.isfinite(sr)


def test_sortino_ratio_only_uses_downside():
    returns = [0.02, 0.02, 0.02, -0.01, -0.01]
    so = sortino_ratio(returns)
    assert so > 0
    assert math.isfinite(so)


def test_sortino_ratio_no_downside_returns_zero():
    returns = [0.01, 0.02, 0.03]
    assert sortino_ratio(returns) == 0.0


from agent.risk_metrics import compute_history_metrics


def test_compute_history_metrics_returns_full_payload():
    series = [
        ("2026-04-01", 10000.0),
        ("2026-04-02", 10100.0),
        ("2026-04-03",  9900.0),
        ("2026-04-04", 10050.0),
        ("2026-04-05",  9800.0),
        ("2026-04-06",  9950.0),
    ]
    out = compute_history_metrics(series)
    assert out["sample_size"] == 6
    assert out["window_days"] == 5
    assert "annualized_volatility" in out
    assert "max_drawdown" in out
    assert "var_95" in out
    assert "cvar_95" in out
    assert "sharpe" in out
    assert "sortino" in out
    assert out["start_date"] == "2026-04-01"
    assert out["end_date"] == "2026-04-06"


def test_compute_history_metrics_too_short_returns_error():
    out = compute_history_metrics([("2026-04-01", 10000.0)])
    assert "error" in out
