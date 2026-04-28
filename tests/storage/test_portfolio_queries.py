from storage.portfolio_store import (
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
    return {
        "report_date": report_date,
        "accounts": [
            {
                "account_id": "U123",
                "alias": "Main",
                "base_currency": "USD",
                "summary": {
                    "net_liquidation": net_liquidation,
                    "stock_value_base": 9000.0,
                    "cash_base": 1000.0,
                    "total_unrealized_pnl_base": 500.0,
                    "total_cost_base": 8500.0,
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
