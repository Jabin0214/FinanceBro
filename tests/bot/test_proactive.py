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


def test_build_opening_brief_includes_nlv_trend_when_series_has_two_entries():
    from bot.proactive import build_opening_brief

    report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1",
            "alias": "main",
            "base_currency": "USD",
            "summary": {
                "net_liquidation": 105000.0,
                "stock_value_base": 100000.0,
                "cash_base": 5000.0,
                "total_unrealized_pnl_base": 5000.0,
                "total_cost_base": 95000.0,
                "total_unrealized_pnl_pct": 5.26,
            },
            "positions": [{
                "symbol": "AAPL",
                "description": "Apple Inc",
                "currency": "USD",
                "asset_category": "STK",
                "quantity": 10.0,
                "cost_price": 150.0,
                "mark_price": 175.0,
                "market_value": 1750.0,
                "market_value_base": 1750.0,
                "cost_basis": 1500.0,
                "cost_basis_base": 1500.0,
                "unrealized_pnl": 250.0,
                "unrealized_pnl_base": 250.0,
                "unrealized_pnl_pct": 16.67,
                "fx_rate": 1.0,
            }],
            "cash_balances": [],
        }],
    }
    nlv_series = [("2026-05-11", 100000.0), ("2026-05-12", 105000.0)]

    text = build_opening_brief(report, nlv_series=nlv_series)

    assert "净值变动" in text
    assert "+5,000" in text or "+5000" in text
    assert "+5.0%" in text


def test_build_opening_brief_omits_trend_when_series_has_one_entry():
    from bot.proactive import build_opening_brief

    report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1",
            "alias": "main",
            "base_currency": "USD",
            "summary": {
                "net_liquidation": 100000.0,
                "stock_value_base": 95000.0,
                "cash_base": 5000.0,
                "total_unrealized_pnl_base": 0.0,
                "total_cost_base": 95000.0,
                "total_unrealized_pnl_pct": 0.0,
            },
            "positions": [{
                "symbol": "AAPL",
                "description": "Apple Inc",
                "currency": "USD",
                "asset_category": "STK",
                "quantity": 10.0,
                "cost_price": 150.0,
                "mark_price": 150.0,
                "market_value": 1500.0,
                "market_value_base": 1500.0,
                "cost_basis": 1500.0,
                "cost_basis_base": 1500.0,
                "unrealized_pnl": 0.0,
                "unrealized_pnl_base": 0.0,
                "unrealized_pnl_pct": 0.0,
                "fx_rate": 1.0,
            }],
            "cash_balances": [],
        }],
    }
    nlv_series = [("2026-05-12", 100000.0)]  # only one entry

    text = build_opening_brief(report, nlv_series=nlv_series)

    assert "净值变动" not in text


def test_build_opening_brief_includes_core_metrics():
    text = proactive.build_opening_brief(_report())

    assert "<b>开盘前简报</b>" in text
    assert "2026-04-29" in text
    assert "净值：$10,000.00" in text
    assert "前五大持仓：100.0%" in text
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


from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))


@pytest.mark.anyio
async def test_threshold_alert_uses_persistent_dedup(monkeypatch):
    """Two calls in the same session must only send once."""
    monkeypatch.setattr("bot.proactive.PROACTIVE_ALERT_USER_ID", 42)

    report = {
        "report_date": "2026-05-10",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 10000, "stock_value_base": 9000,
                        "cash_base": 1000, "total_unrealized_pnl_base": -1000,
                        "total_cost_base": 10000, "total_unrealized_pnl_pct": -10.0},
            "positions": [{
                "symbol": "AAA", "description": "", "asset_category": "STK",
                "currency": "USD", "market_value_base": 9000,
                "unrealized_pnl_base": -1000, "unrealized_pnl_pct": -10.0,
                "cost_basis_base": 10000,
            }],
            "cash_balances": [],
        }],
    }

    bot_mock = AsyncMock()
    context = type("Ctx", (), {"bot": bot_mock})()

    from bot import proactive

    with patch.object(proactive, "_fetch_and_save", return_value=report):
        await proactive.threshold_alert_job(context)
        await proactive.threshold_alert_job(context)

    assert bot_mock.send_message.await_count == 1


@pytest.mark.anyio
async def test_news_monitor_uses_persistent_dedup(monkeypatch):
    """Two calls with same digest must only send once."""
    monkeypatch.setattr("bot.proactive.PROACTIVE_NEWS_USER_ID", 42)

    report = {
        "report_date": "2026-05-10",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 10000, "stock_value_base": 10000,
                        "cash_base": 0, "total_unrealized_pnl_base": 0,
                        "total_cost_base": 10000, "total_unrealized_pnl_pct": 0},
            "positions": [
                {"symbol": "AAA", "description": "", "asset_category": "STK",
                 "currency": "USD", "market_value_base": 10000,
                 "unrealized_pnl_base": 0, "unrealized_pnl_pct": 0,
                 "cost_basis_base": 10000},
            ],
            "cash_balances": [],
        }],
    }

    bot_mock = AsyncMock()
    context = type("Ctx", (), {"bot": bot_mock})()

    from bot import proactive

    with patch.object(proactive, "_fetch_and_save", return_value=report), \
         patch.object(proactive, "_get_news", return_value="AAA reports strong Q1"):
        await proactive.news_monitor_job(context)
        await proactive.news_monitor_job(context)

    assert bot_mock.send_message.await_count == 1


@pytest.mark.anyio
async def test_news_monitor_prepends_high_impact_summary(monkeypatch):
    monkeypatch.setattr("bot.proactive.PROACTIVE_NEWS_USER_ID", 42)

    report = {
        "report_date": "2026-05-10",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 10000, "stock_value_base": 10000,
                        "cash_base": 0, "total_unrealized_pnl_base": 0,
                        "total_cost_base": 10000, "total_unrealized_pnl_pct": 0},
            "positions": [
                {"symbol": "AAPL", "description": "", "asset_category": "STK",
                 "currency": "USD", "market_value_base": 8000,
                 "unrealized_pnl_base": 0, "unrealized_pnl_pct": 0,
                 "cost_basis_base": 8000},
                {"symbol": "TSLA", "description": "", "asset_category": "STK",
                 "currency": "USD", "market_value_base": 2000,
                 "unrealized_pnl_base": 0, "unrealized_pnl_pct": 0,
                 "cost_basis_base": 2000},
            ],
            "cash": [],
        }],
    }

    grok_digest = (
        "AAPL beats earnings and raises guidance for next quarter.\n"
        "TSLA recall announced over battery defect.\n"
        "Generic market chatter with no ticker."
    )

    bot_mock = AsyncMock()
    context = type("Ctx", (), {"bot": bot_mock})()

    from bot import proactive

    with patch.object(proactive, "_fetch_and_save", return_value=report), \
         patch.object(proactive, "_get_news", return_value=grok_digest):
        await proactive.news_monitor_job(context)

    sent_text = bot_mock.send_message.await_args.kwargs["text"]
    assert "影响排序" in sent_text
    aapl_idx = sent_text.find("AAPL")
    tsla_idx = sent_text.find("TSLA")
    assert 0 <= aapl_idx < tsla_idx


@pytest.mark.anyio
async def test_drift_alert_job_fires_when_drift_exceeds_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "drift_test.db"))
    from bot import proactive

    sent = []

    _report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 100000.0, "stock_value_base": 100000.0,
                        "cash_base": 0.0, "total_unrealized_pnl_base": 0.0,
                        "total_cost_base": 100000.0, "total_unrealized_pnl_pct": 0.0},
            "positions": [{"symbol": "AAPL", "description": "", "currency": "USD",
                           "asset_category": "STK", "quantity": 100.0, "cost_price": 150.0,
                           "mark_price": 170.0, "market_value": 17000.0, "market_value_base": 17000.0,
                           "cost_basis": 15000.0, "cost_basis_base": 15000.0, "unrealized_pnl": 2000.0,
                           "unrealized_pnl_base": 2000.0, "unrealized_pnl_pct": 13.33, "fx_rate": 1.0}],
            "cash_balances": [],
        }],
    }

    monkeypatch.setattr(proactive, "DRIFT_ALERT_USER_ID", 42)
    monkeypatch.setattr(proactive, "DRIFT_ALERT_THRESHOLD_PCT", 5.0)
    monkeypatch.setattr(proactive, "get_latest_portfolio_report", lambda user_id: _report)
    monkeypatch.setattr(proactive, "get_targets", lambda user_id: {"AAPL": 80.0})
    monkeypatch.setattr(proactive, "should_fire", lambda trigger, user_id, fingerprint: True)
    monkeypatch.setattr(proactive, "record_fire", lambda trigger, user_id, fingerprint: None)
    monkeypatch.setattr(proactive, "_send", AsyncMock(side_effect=lambda ctx, uid, text: sent.append(text)))

    context = SimpleNamespace(bot=AsyncMock())
    await proactive.drift_alert_job(context)

    assert sent
    assert "仓位偏离预警" in sent[0]
    assert "AAPL" in sent[0]


@pytest.mark.anyio
async def test_drift_alert_job_skips_when_drift_below_threshold(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "drift_test2.db"))
    from bot import proactive

    sent = []

    _report = {
        "report_date": "2026-05-12",
        "accounts": [{
            "account_id": "U1", "alias": "main", "base_currency": "USD",
            "summary": {"net_liquidation": 100000.0, "stock_value_base": 100000.0,
                        "cash_base": 0.0, "total_unrealized_pnl_base": 0.0,
                        "total_cost_base": 100000.0, "total_unrealized_pnl_pct": 0.0},
            "positions": [{"symbol": "AAPL", "description": "", "currency": "USD",
                           "asset_category": "STK", "quantity": 100.0, "cost_price": 150.0,
                           "mark_price": 150.0, "market_value": 15000.0, "market_value_base": 15000.0,
                           "cost_basis": 15000.0, "cost_basis_base": 15000.0, "unrealized_pnl": 0.0,
                           "unrealized_pnl_base": 0.0, "unrealized_pnl_pct": 0.0, "fx_rate": 1.0}],
            "cash_balances": [],
        }],
    }

    monkeypatch.setattr(proactive, "DRIFT_ALERT_USER_ID", 42)
    monkeypatch.setattr(proactive, "DRIFT_ALERT_THRESHOLD_PCT", 20.0)
    monkeypatch.setattr(proactive, "get_latest_portfolio_report", lambda user_id: _report)
    monkeypatch.setattr(proactive, "get_targets", lambda user_id: {"AAPL": 14.0})
    monkeypatch.setattr(proactive, "_send", AsyncMock(side_effect=lambda ctx, uid, text: sent.append(text)))

    context = SimpleNamespace(bot=AsyncMock())
    await proactive.drift_alert_job(context)

    assert not sent


@pytest.mark.anyio
async def test_drift_alert_job_skips_when_no_targets(monkeypatch, tmp_path):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "drift_test3.db"))
    from bot import proactive

    sent = []
    monkeypatch.setattr(proactive, "DRIFT_ALERT_USER_ID", 42)
    monkeypatch.setattr(proactive, "get_latest_portfolio_report", lambda user_id: {"report_date": "2026-05-12", "accounts": []})
    monkeypatch.setattr(proactive, "get_targets", lambda user_id: {})
    monkeypatch.setattr(proactive, "_send", AsyncMock(side_effect=lambda ctx, uid, text: sent.append(text)))

    context = SimpleNamespace(bot=AsyncMock())
    await proactive.drift_alert_job(context)

    assert not sent
