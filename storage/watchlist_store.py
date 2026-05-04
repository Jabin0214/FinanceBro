"""Persistent per-user watchlist storage."""

from __future__ import annotations

from storage import db


def add_watchlist_item(user_id: int, symbol: str, note: str = "") -> None:
    normalized = _normalize_symbol(symbol)
    with db.transaction() as conn:
        conn.execute(
            """
            insert into watchlist_items (user_id, symbol, note)
            values (?, ?, ?)
            on conflict(user_id, symbol) do update set
                note = excluded.note,
                updated_at = current_timestamp
            """,
            (user_id, normalized, note.strip()),
        )


def update_watchlist_research(user_id: int, symbol: str, **fields) -> None:
    normalized = _normalize_symbol(symbol)
    allowed = {
        "status": fields.get("status"),
        "thesis": fields.get("thesis"),
        "trigger_price": fields.get("trigger_price"),
        "risk_note": fields.get("risk_note"),
    }
    updates = {key: value for key, value in allowed.items() if value is not None}

    with db.transaction() as conn:
        conn.execute(
            """
            insert into watchlist_items (user_id, symbol)
            values (?, ?)
            on conflict(user_id, symbol) do nothing
            """,
            (user_id, normalized),
        )
        if not updates:
            return
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = [
            float(value) if key == "trigger_price" else str(value).strip()
            for key, value in updates.items()
        ]
        conn.execute(
            f"""
            update watchlist_items
            set {set_clause}, updated_at = current_timestamp
            where user_id = ? and symbol = ?
            """,
            (*values, user_id, normalized),
        )


def remove_watchlist_item(user_id: int, symbol: str) -> bool:
    normalized = _normalize_symbol(symbol)
    with db.transaction() as conn:
        cur = conn.execute(
            "delete from watchlist_items where user_id = ? and symbol = ?",
            (user_id, normalized),
        )
        return cur.rowcount > 0


def list_watchlist_items(user_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            select symbol, note, status, thesis, trigger_price, risk_note
            from watchlist_items
            where user_id = ?
            order by symbol asc
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol is required")
    return normalized
