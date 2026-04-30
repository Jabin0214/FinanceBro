from storage.portfolio_store import (
    get_portfolio_history_summary,
    get_latest_snapshot,
    get_position_history,
    get_snapshot_dates,
    save_portfolio_report,
)


def _report(report_date, symbol="AAPL", quantity=2.0, net_liquidation=10000.0):
    position = _position(symbol, quantity)
    return _report_with_positions(report_date, [position], net_liquidation)


def _position(symbol, quantity):
    return {
        "symbol": symbol,
        "description": f"{symbol} Inc",
        "currency": "USD",
        "asset_category": "STK",
        "quantity": quantity,
        "cost_price": 150.0,
        "mark_price": 175.0,
        "market_value": quantity * 175.0,
        "market_value_base": quantity * 175.0,
        "cost_basis": quantity * 150.0,
        "cost_basis_base": quantity * 150.0,
        "unrealized_pnl": quantity * 25.0,
        "unrealized_pnl_base": quantity * 25.0,
        "unrealized_pnl_pct": 16.67,
        "fx_rate": 1.0,
    }


def _report_with_positions(report_date, positions, net_liquidation=10000.0):
    stock_value_base = sum(pos["market_value_base"] for pos in positions)
    total_cost_base = sum(pos["cost_basis_base"] for pos in positions)
    total_unrealized_pnl_base = sum(pos["unrealized_pnl_base"] for pos in positions)
    return {
        "report_date": report_date,
        "accounts": [
            {
                "account_id": "U123",
                "alias": "Main",
                "base_currency": "USD",
                "summary": {
                    "net_liquidation": net_liquidation,
                    "stock_value_base": stock_value_base,
                    "cash_base": net_liquidation - stock_value_base,
                    "total_unrealized_pnl_base": total_unrealized_pnl_base,
                    "total_cost_base": total_cost_base,
                    "total_unrealized_pnl_pct": 5.88,
                },
                "positions": positions,
                "cash_balances": [],
            }
        ],
    }


def test_get_latest_snapshot_returns_most_recent_account(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    save_portfolio_report(42, _report("2026-04-27", net_liquidation=9000.0))
    save_portfolio_report(42, _report("2026-04-28", net_liquidation=10000.0))

    latest = get_latest_snapshot(42)

    assert latest["report_date"] == "2026-04-28"
    assert latest["account_id"] == "U123"
    assert latest["net_liquidation"] == 10000.0


def test_get_snapshot_dates_returns_recent_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    save_portfolio_report(42, _report("2026-04-26"))
    save_portfolio_report(42, _report("2026-04-27"))
    save_portfolio_report(42, _report("2026-04-28"))

    assert get_snapshot_dates(42, limit=2) == ["2026-04-28", "2026-04-27"]


def test_get_position_history_returns_symbol_rows_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    save_portfolio_report(42, _report("2026-04-27", symbol="AAPL", quantity=2.0))
    save_portfolio_report(
        42,
        _report_with_positions(
            "2026-04-28",
            [_position("AAPL", 3.0), _position("MSFT", 5.0)],
        ),
    )

    rows = get_position_history(42, "aapl", limit=5)

    assert [row["report_date"] for row in rows] == ["2026-04-28", "2026-04-27"]
    assert [row["quantity"] for row in rows] == [3.0, 2.0]
    assert rows[0]["symbol"] == "AAPL"


def test_get_portfolio_history_summary_compares_oldest_and_newest_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    save_portfolio_report(
        42,
        _report_with_positions(
            "2026-04-01",
            [_position("AAPL", 2.0), _position("TSLA", 1.0)],
            net_liquidation=10000.0,
        ),
    )
    save_portfolio_report(
        42,
        _report_with_positions(
            "2026-04-28",
            [_position("AAPL", 5.0), _position("MSFT", 4.0)],
            net_liquidation=12500.0,
        ),
    )

    summary = get_portfolio_history_summary(42, days=30)

    assert summary["period_days"] == 30
    assert summary["snapshot_count"] == 2
    assert summary["start_date"] == "2026-04-01"
    assert summary["end_date"] == "2026-04-28"
    assert summary["totals"]["net_liquidation"]["start"] == 10000.0
    assert summary["totals"]["net_liquidation"]["end"] == 12500.0
    assert summary["totals"]["net_liquidation"]["change"] == 2500.0
    assert summary["totals"]["net_liquidation"]["change_pct"] == 25.0
    assert summary["position_changes"][0]["symbol"] == "MSFT"
    assert summary["position_changes"][0]["status"] == "opened"
    assert summary["position_changes"][1]["symbol"] == "AAPL"
    assert summary["position_changes"][1]["quantity_change"] == 3.0
    assert summary["position_changes"][2]["symbol"] == "TSLA"
    assert summary["position_changes"][2]["status"] == "closed"
    assert summary["top_unrealized_pnl_contributors"][0]["symbol"] == "AAPL"
