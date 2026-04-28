"""Persistence for daily IBKR portfolio snapshots."""

from __future__ import annotations

import json

from storage import db


def save_portfolio_report(user_id: int, report: dict) -> list[int]:
    """Save a structured IBKR report and return saved account snapshot IDs."""
    report_date = report.get("report_date") or ""
    snapshot_ids: list[int] = []

    with db.transaction() as conn:
        conn.execute(
            """
            insert into raw_reports (user_id, report_date, source, payload_json)
            values (?, ?, ?, ?)
            on conflict(user_id, report_date, source) do update set
                payload_json = excluded.payload_json,
                created_at = current_timestamp
            """,
            (
                user_id,
                report_date,
                "ibkr_flex",
                json.dumps(report, ensure_ascii=False),
            ),
        )

        for account in report.get("accounts", []):
            summary = account.get("summary", {})
            snapshot_id = _upsert_snapshot(conn, user_id, report_date, account, summary)
            _replace_positions(conn, snapshot_id, account.get("positions", []))
            _replace_cash(conn, snapshot_id, account.get("cash_balances", []))
            snapshot_ids.append(snapshot_id)

    return snapshot_ids


def _upsert_snapshot(conn, user_id: int, report_date: str, account: dict, summary: dict) -> int:
    conn.execute(
        """
        insert into portfolio_snapshots (
            user_id,
            account_id,
            report_date,
            alias,
            base_currency,
            net_liquidation,
            stock_value_base,
            cash_base,
            total_unrealized_pnl_base,
            total_cost_base,
            total_unrealized_pnl_pct
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(user_id, account_id, report_date) do update set
            alias = excluded.alias,
            base_currency = excluded.base_currency,
            net_liquidation = excluded.net_liquidation,
            stock_value_base = excluded.stock_value_base,
            cash_base = excluded.cash_base,
            total_unrealized_pnl_base = excluded.total_unrealized_pnl_base,
            total_cost_base = excluded.total_cost_base,
            total_unrealized_pnl_pct = excluded.total_unrealized_pnl_pct,
            updated_at = current_timestamp
        """,
        (
            user_id,
            account.get("account_id", ""),
            report_date,
            account.get("alias", "") or "",
            account.get("base_currency", "") or "",
            summary.get("net_liquidation", 0) or 0,
            summary.get("stock_value_base", 0) or 0,
            summary.get("cash_base", 0) or 0,
            summary.get("total_unrealized_pnl_base", 0) or 0,
            summary.get("total_cost_base", 0) or 0,
            summary.get("total_unrealized_pnl_pct", 0) or 0,
        ),
    )
    row = conn.execute(
        """
        select id from portfolio_snapshots
        where user_id = ? and account_id = ? and report_date = ?
        """,
        (user_id, account.get("account_id", ""), report_date),
    ).fetchone()
    return int(row["id"])


def _replace_positions(conn, snapshot_id: int, positions: list[dict]) -> None:
    conn.execute("delete from position_snapshots where snapshot_id = ?", (snapshot_id,))
    conn.executemany(
        """
        insert into position_snapshots (
            snapshot_id,
            symbol,
            description,
            currency,
            asset_category,
            quantity,
            cost_price,
            mark_price,
            market_value,
            market_value_base,
            cost_basis,
            cost_basis_base,
            unrealized_pnl,
            unrealized_pnl_base,
            unrealized_pnl_pct,
            fx_rate
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                snapshot_id,
                pos.get("symbol", "") or "",
                pos.get("description", "") or "",
                pos.get("currency", "") or "",
                pos.get("asset_category", "") or "",
                pos.get("quantity", 0) or 0,
                pos.get("cost_price", 0) or 0,
                pos.get("mark_price", 0) or 0,
                pos.get("market_value", 0) or 0,
                pos.get("market_value_base", 0) or 0,
                pos.get("cost_basis", 0) or 0,
                pos.get("cost_basis_base", 0) or 0,
                pos.get("unrealized_pnl", 0) or 0,
                pos.get("unrealized_pnl_base", 0) or 0,
                pos.get("unrealized_pnl_pct", 0) or 0,
                pos.get("fx_rate", 1) or 1,
            )
            for pos in positions
        ],
    )


def _replace_cash(conn, snapshot_id: int, cash_balances: list[dict]) -> None:
    conn.execute("delete from cash_snapshots where snapshot_id = ?", (snapshot_id,))
    conn.executemany(
        """
        insert into cash_snapshots (
            snapshot_id,
            currency,
            ending_cash,
            ending_cash_base
        )
        values (?, ?, ?, ?)
        """,
        [
            (
                snapshot_id,
                cash.get("currency", "") or "",
                cash.get("ending_cash", 0) or 0,
                cash.get("ending_cash_base", 0) or 0,
            )
            for cash in cash_balances
        ],
    )
