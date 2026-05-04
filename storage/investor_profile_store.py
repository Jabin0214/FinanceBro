"""Persistent per-user investing profile."""

from __future__ import annotations

from storage import db

DEFAULT_PROFILE = {
    "risk_level": "balanced",
    "time_horizon": "medium",
    "max_position_weight_pct": 35.0,
    "cash_floor_pct": 5.0,
    "preferred_markets": "",
    "notes": "",
}

_FIELDS = set(DEFAULT_PROFILE)


def get_investor_profile(user_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute(
            """
            select risk_level, time_horizon, max_position_weight_pct,
                   cash_floor_pct, preferred_markets, notes
            from investor_profiles
            where user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return dict(DEFAULT_PROFILE)

    profile = dict(row)
    profile["max_position_weight_pct"] = float(profile["max_position_weight_pct"])
    profile["cash_floor_pct"] = float(profile["cash_floor_pct"])
    return profile


def update_investor_profile(user_id: int, **fields) -> dict:
    clean = {key: value for key, value in fields.items() if key in _FIELDS and value is not None}
    if not clean:
        return get_investor_profile(user_id)

    current = get_investor_profile(user_id)
    current.update(clean)

    with db.transaction() as conn:
        conn.execute(
            """
            insert into investor_profiles (
                user_id, risk_level, time_horizon, max_position_weight_pct,
                cash_floor_pct, preferred_markets, notes
            )
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(user_id) do update set
                risk_level = excluded.risk_level,
                time_horizon = excluded.time_horizon,
                max_position_weight_pct = excluded.max_position_weight_pct,
                cash_floor_pct = excluded.cash_floor_pct,
                preferred_markets = excluded.preferred_markets,
                notes = excluded.notes,
                updated_at = current_timestamp
            """,
            (
                user_id,
                current["risk_level"],
                current["time_horizon"],
                float(current["max_position_weight_pct"]),
                float(current["cash_floor_pct"]),
                current["preferred_markets"],
                current["notes"],
            ),
        )

    return get_investor_profile(user_id)
