"""CRUD for user target allocation profiles."""

from __future__ import annotations

from storage import db


def set_targets(user_id: int, targets: dict[str, float]) -> None:
    """Replace all target allocations for user. targets = {SYMBOL: target_pct}."""
    with db.transaction() as conn:
        conn.execute("delete from target_allocations where user_id = ?", (user_id,))
        conn.executemany(
            "insert into target_allocations (user_id, symbol, target_pct) values (?, ?, ?)",
            [(user_id, sym.upper(), round(float(pct), 2)) for sym, pct in targets.items()],
        )


def get_targets(user_id: int) -> dict[str, float]:
    """Return {SYMBOL: target_pct} for user, empty dict if none set."""
    with db.connect() as conn:
        rows = conn.execute(
            "select symbol, target_pct from target_allocations where user_id = ? order by symbol",
            (user_id,),
        ).fetchall()
    return {row["symbol"]: row["target_pct"] for row in rows}
