from types import SimpleNamespace

import pytest

from bot import proactive


def _report():
    return {
        "report_date": "2026-04-29",
        "accounts": [
            {
                "account_id": "U123",
                "base_currency": "USD",
                "summary": {
                    "net_liquidation": 10000.0,
                    "cash_base": 1500.0,
                    "total_unrealized_pnl_base": -900.0,
                    "total_cost_base": 10000.0,
                    "total_unrealized_pnl_pct": -9.0,
                },
                "positions": [
                    {
                        "symbol": "AAPL",
                        "description": "Apple Inc",
                        "currency": "USD",
                        "asset_category": "STK",
                        "market_value_base": 5000.0,
                        "cost_basis_base": 5500.0,
                        "unrealized_pnl_base": -500.0,
                        "unrealized_pnl_pct": -9.09,
                    },
                    {
                        "symbol": "MSFT",
                        "description": "Microsoft",
                        "currency": "USD",
                        "asset_category": "STK",
                        "market_value_base": 3000.0,
                        "cost_basis_base": 3500.0,
                        "unrealized_pnl_base": -400.0,
                        "unrealized_pnl_pct": -11.43,
                    },
                ],
                "cash_balances": [],
            }
        ],
    }


def test_build_opening_brief_includes_core_metrics():
    text = proactive.build_opening_brief(
        _report(),
        {
            "risk_level": "conservative",
            "max_position_weight_pct": 45.0,
            "cash_floor_pct": 20.0,
        },
    )

    assert "<b>开盘前简报</b>" in text
    assert "2026-04-29" in text
    assert "净值：$10,000.00" in text
    assert "前五大持仓：100.0%" in text
    assert "<b>今天只看三件事</b>" in text
    assert "现金低于你的底线 20.0%" in text
    assert "AAPL 单一持仓 62.5%" in text
    assert "<b>风险提醒</b>" in text
    assert "整体浮亏 -10.0%" in text
    assert "AAPL" in text


def test_build_threshold_alerts_flags_loss_and_concentration():
    alerts = proactive.build_threshold_alerts(
        _report(),
        pnl_threshold_pct=-5.0,
        position_weight_threshold_pct=40.0,
    )

    assert any("整体浮亏" in alert for alert in alerts)
    assert any("AAPL" in alert for alert in alerts)


@pytest.mark.anyio
async def test_opening_brief_job_fetches_saves_and_sends(monkeypatch):
    sent = []
    saved = []
    monkeypatch.setattr(proactive, "PROACTIVE_BRIEF_USER_ID", 42)
    monkeypatch.setattr(proactive, "fetch_flex_report", _report)
    monkeypatch.setattr(
        proactive,
        "save_portfolio_report",
        lambda user_id, report: saved.append((user_id, report)) or [7],
    )
    monkeypatch.setattr(
        proactive,
        "get_investor_profile",
        lambda user_id: {"max_position_weight_pct": 35.0, "cash_floor_pct": 5.0},
    )

    async def send_message(chat_id, text, parse_mode=None):
        sent.append((chat_id, text, parse_mode))

    context = SimpleNamespace(bot=SimpleNamespace(send_message=send_message))

    await proactive.opening_brief_job(context)

    assert saved == [(42, _report())]
    assert sent[0][0] == 42
    assert "<b>开盘前简报</b>" in sent[0][1]


@pytest.fixture
def anyio_backend():
    return "asyncio"
