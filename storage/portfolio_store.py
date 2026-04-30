"""Persistence for daily IBKR portfolio snapshots."""

from __future__ import annotations

import json
from datetime import date, timedelta

from storage import db


def get_portfolio_history_summary(user_id: int, days: int = 30) -> dict:
    """Return a compact historical portfolio summary for agent analysis."""
    days = _normalize_history_days(days)

    with db.connect() as conn:
        latest_row = conn.execute(
            """
            select max(report_date) as report_date
            from portfolio_snapshots
            where user_id = ?
            """,
            (user_id,),
        ).fetchone()
        latest_date = latest_row["report_date"] if latest_row else None
        if not latest_date:
            return _empty_history_summary(days)

        cutoff_date = (date.fromisoformat(latest_date) - timedelta(days=days - 1)).isoformat()
        totals = conn.execute(
            """
            select
                report_date,
                sum(net_liquidation) as net_liquidation,
                sum(stock_value_base) as stock_value_base,
                sum(cash_base) as cash_base,
                sum(total_unrealized_pnl_base) as total_unrealized_pnl_base,
                sum(total_cost_base) as total_cost_base
            from portfolio_snapshots
            where user_id = ? and report_date >= ? and report_date <= ?
            group by report_date
            order by report_date asc
            """,
            (user_id, cutoff_date, latest_date),
        ).fetchall()

        if not totals:
            return _empty_history_summary(days)

        positions = conn.execute(
            """
            select
                ps.report_date,
                upper(pos.symbol) as symbol,
                max(pos.description) as description,
                max(pos.currency) as currency,
                max(pos.asset_category) as asset_category,
                sum(pos.quantity) as quantity,
                sum(pos.market_value_base) as market_value_base,
                sum(pos.cost_basis_base) as cost_basis_base,
                sum(pos.unrealized_pnl_base) as unrealized_pnl_base
            from position_snapshots pos
            join portfolio_snapshots ps on ps.id = pos.snapshot_id
            where ps.user_id = ? and ps.report_date >= ? and ps.report_date <= ?
            group by ps.report_date, upper(pos.symbol)
            order by ps.report_date asc, symbol asc
            """,
            (user_id, cutoff_date, latest_date),
        ).fetchall()

    start = dict(totals[0])
    end = dict(totals[-1])
    position_changes, top_contributors = _summarize_position_history(positions, start["report_date"], end["report_date"])

    return {
        "period_days": days,
        "snapshot_count": len(totals),
        "start_date": start["report_date"],
        "end_date": end["report_date"],
        "totals": {
            "net_liquidation": _change(start["net_liquidation"], end["net_liquidation"]),
            "stock_value_base": _change(start["stock_value_base"], end["stock_value_base"]),
            "cash_base": _change(start["cash_base"], end["cash_base"]),
            "total_unrealized_pnl_base": _change(
                start["total_unrealized_pnl_base"],
                end["total_unrealized_pnl_base"],
            ),
            "total_cost_base": _change(start["total_cost_base"], end["total_cost_base"]),
        },
        "position_changes": position_changes,
        "top_unrealized_pnl_contributors": top_contributors,
    }


def get_latest_snapshot(user_id: int) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            """
            select *
            from portfolio_snapshots
            where user_id = ?
            order by report_date desc, id desc
            limit 1
            """,
            (user_id,),
        ).fetchone()

    return dict(row) if row else None


def get_snapshot_dates(user_id: int, limit: int = 30) -> list[str]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            select distinct report_date
            from portfolio_snapshots
            where user_id = ?
            order by report_date desc
            limit ?
            """,
            (user_id, limit),
        ).fetchall()

    return [row["report_date"] for row in rows]


def get_position_history(user_id: int, symbol: str, limit: int = 30) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            select
                ps.report_date,
                ps.account_id,
                pos.symbol,
                pos.description,
                pos.currency,
                pos.asset_category,
                pos.quantity,
                pos.cost_price,
                pos.mark_price,
                pos.market_value,
                pos.market_value_base,
                pos.cost_basis,
                pos.cost_basis_base,
                pos.unrealized_pnl,
                pos.unrealized_pnl_base,
                pos.unrealized_pnl_pct,
                pos.fx_rate
            from position_snapshots pos
            join portfolio_snapshots ps on ps.id = pos.snapshot_id
            where ps.user_id = ? and upper(pos.symbol) = upper(?)
            order by ps.report_date desc, ps.id desc
            limit ?
            """,
            (user_id, symbol, limit),
        ).fetchall()

    return [dict(row) for row in rows]


def _normalize_history_days(days: int) -> int:
    return days if days in {7, 30, 90} else 30


def _empty_history_summary(days: int) -> dict:
    return {
        "period_days": days,
        "snapshot_count": 0,
        "start_date": None,
        "end_date": None,
        "totals": {},
        "position_changes": [],
        "top_unrealized_pnl_contributors": [],
    }


def _change(start: float | None, end: float | None) -> dict:
    start_value = float(start or 0)
    end_value = float(end or 0)
    delta = end_value - start_value
    return {
        "start": start_value,
        "end": end_value,
        "change": delta,
        "change_pct": (delta / start_value * 100) if start_value else None,
    }


def _summarize_position_history(rows, start_date: str, end_date: str) -> tuple[list[dict], list[dict]]:
    start_positions = {
        row["symbol"]: dict(row)
        for row in rows
        if row["report_date"] == start_date
    }
    end_positions = {
        row["symbol"]: dict(row)
        for row in rows
        if row["report_date"] == end_date
    }
    symbols = sorted(set(start_positions) | set(end_positions))

    changes = []
    for symbol in symbols:
        before = start_positions.get(symbol, {})
        after = end_positions.get(symbol, {})
        quantity_change = float(after.get("quantity") or 0) - float(before.get("quantity") or 0)
        market_value_change = float(after.get("market_value_base") or 0) - float(before.get("market_value_base") or 0)
        changes.append({
            "symbol": symbol,
            "description": after.get("description") or before.get("description") or "",
            "asset_category": after.get("asset_category") or before.get("asset_category") or "",
            "currency": after.get("currency") or before.get("currency") or "",
            "start_quantity": float(before.get("quantity") or 0),
            "end_quantity": float(after.get("quantity") or 0),
            "quantity_change": quantity_change,
            "start_market_value_base": float(before.get("market_value_base") or 0),
            "end_market_value_base": float(after.get("market_value_base") or 0),
            "market_value_change_base": market_value_change,
            "status": _position_status(before, after, quantity_change),
        })

    changes.sort(key=lambda row: abs(row["market_value_change_base"]), reverse=True)
    contributors = [
        {
            "symbol": symbol,
            "description": row.get("description") or "",
            "unrealized_pnl_base": float(row.get("unrealized_pnl_base") or 0),
            "market_value_base": float(row.get("market_value_base") or 0),
        }
        for symbol, row in end_positions.items()
    ]
    contributors.sort(key=lambda row: abs(row["unrealized_pnl_base"]), reverse=True)
    return changes[:10], contributors[:10]


def _position_status(before: dict, after: dict, quantity_change: float) -> str:
    if not before and after:
        return "opened"
    if before and not after:
        return "closed"
    if quantity_change > 0:
        return "increased"
    if quantity_change < 0:
        return "decreased"
    return "unchanged"


def save_portfolio_report(user_id: int, report: dict) -> list[int]:
    """Save a structured IBKR report and return saved account snapshot IDs."""
    report_date = report.get("report_date") or ""
    accounts = report.get("accounts", [])
    if not accounts:
        raise ValueError("portfolio report contains no accounts")

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

        for account in accounts:
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
