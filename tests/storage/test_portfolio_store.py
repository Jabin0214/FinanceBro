import json

from storage import db
from storage.portfolio_store import save_portfolio_report


def _sample_report(symbol="AAPL", quantity=2.0):
    return {
        "generated_at": "2026-04-28 07:00:00",
        "report_date": "2026-04-28",
        "accounts": [
            {
                "account_id": "U123",
                "alias": "Main",
                "base_currency": "USD",
                "summary": {
                    "net_liquidation": 10000.0,
                    "stock_value_base": 9000.0,
                    "cash_base": 1000.0,
                    "total_unrealized_pnl_base": 500.0,
                    "total_cost_base": 8500.0,
                    "total_unrealized_pnl_pct": 5.88,
                },
                "positions": [
                    {
                        "symbol": symbol,
                        "description": "Apple Inc",
                        "currency": "USD",
                        "asset_category": "STK",
                        "quantity": quantity,
                        "cost_price": 150.0,
                        "mark_price": 175.0,
                        "market_value": 350.0,
                        "market_value_base": 350.0,
                        "cost_basis": 300.0,
                        "cost_basis_base": 300.0,
                        "unrealized_pnl": 50.0,
                        "unrealized_pnl_base": 50.0,
                        "unrealized_pnl_pct": 16.67,
                        "fx_rate": 1.0,
                    }
                ],
                "cash_balances": [
                    {
                        "currency": "USD",
                        "ending_cash": 1000.0,
                        "ending_cash_base": 1000.0,
                    }
                ],
            }
        ],
    }


def test_save_portfolio_report_writes_raw_report_and_snapshot_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    report = _sample_report()

    snapshot_ids = save_portfolio_report(42, report)

    with db.connect() as conn:
        raw = conn.execute("select * from raw_reports").fetchone()
        snapshot = conn.execute("select * from portfolio_snapshots").fetchone()
        position = conn.execute("select * from position_snapshots").fetchone()
        cash = conn.execute("select * from cash_snapshots").fetchone()

    assert len(snapshot_ids) == 1
    assert json.loads(raw["payload_json"]) == report
    assert snapshot["user_id"] == 42
    assert snapshot["account_id"] == "U123"
    assert snapshot["report_date"] == "2026-04-28"
    assert snapshot["net_liquidation"] == 10000.0
    assert position["symbol"] == "AAPL"
    assert position["quantity"] == 2.0
    assert cash["currency"] == "USD"
    assert cash["ending_cash_base"] == 1000.0


def test_save_portfolio_report_replaces_same_day_snapshot_children(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    save_portfolio_report(42, _sample_report(symbol="AAPL", quantity=2.0))

    save_portfolio_report(42, _sample_report(symbol="MSFT", quantity=3.0))

    with db.connect() as conn:
        snapshots = conn.execute("select * from portfolio_snapshots").fetchall()
        positions = conn.execute("select * from position_snapshots").fetchall()
        cash_rows = conn.execute("select * from cash_snapshots").fetchall()

    assert len(snapshots) == 1
    assert len(positions) == 1
    assert positions[0]["symbol"] == "MSFT"
    assert positions[0]["quantity"] == 3.0
    assert len(cash_rows) == 1
