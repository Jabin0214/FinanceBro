from unittest.mock import patch

from agent.tools.risk_metrics import DEFINITION, execute


def test_definition_shape():
    assert DEFINITION["name"] == "get_risk_metrics"
    assert "description" in DEFINITION
    assert "input_schema" in DEFINITION


def test_execute_returns_formatted_text_on_success():
    series = [
        ("2026-04-01", 10000.0),
        ("2026-04-02", 10100.0),
        ("2026-04-03",  9900.0),
        ("2026-04-04", 10050.0),
    ]
    with patch("agent.tools.risk_metrics.current_user_id", return_value=42), \
         patch("agent.tools.risk_metrics.get_net_liquidation_series", return_value=series):
        out = execute({"days": 30})
    assert "波动" in out or "volatility" in out.lower()
    assert "最大回撤" in out or "drawdown" in out.lower()


def test_execute_handles_insufficient_data():
    with patch("agent.tools.risk_metrics.current_user_id", return_value=42), \
         patch("agent.tools.risk_metrics.get_net_liquidation_series", return_value=[]):
        out = execute({"days": 30})
    assert "不足" in out or "error" in out.lower() or "⚠️" in out


def test_execute_missing_user_id():
    with patch("agent.tools.risk_metrics.current_user_id", return_value=None):
        out = execute({"days": 30})
    assert "用户" in out or "user" in out.lower() or "❌" in out
