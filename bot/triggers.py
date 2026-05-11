"""Persistent trigger evaluator with cooldown and daily cap.

Pattern adapted from pavelsukhachev/hybrid-orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from storage.db import transaction


@dataclass(frozen=True)
class Trigger:
    name: str
    cooldown_seconds: int = 3600
    max_fires_per_day: int = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def should_fire(trigger: Trigger, user_id: int, fingerprint: str) -> bool:
    """Return True if this (trigger, user, fingerprint) is allowed to fire now."""
    now = _utcnow()
    with transaction() as conn:
        # Same fingerprint within cooldown blocks.
        row = conn.execute(
            """
            select fired_at from trigger_fires
            where trigger_name = ? and user_id = ? and fingerprint = ?
            order by id desc limit 1
            """,
            (trigger.name, user_id, fingerprint),
        ).fetchone()
        if row is not None:
            fired_at = datetime.fromisoformat(row["fired_at"]).replace(
                tzinfo=timezone.utc
            )
            age = (now - fired_at).total_seconds()
            if age < trigger.cooldown_seconds:
                return False

        # Daily cap across all fingerprints.
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = conn.execute(
            """
            select count(*) as n from trigger_fires
            where trigger_name = ? and user_id = ? and fired_at >= ?
            """,
            (trigger.name, user_id, today_start.isoformat(sep=" ", timespec="seconds")),
        ).fetchone()["n"]
        if count >= trigger.max_fires_per_day:
            return False

    return True


def record_fire(trigger: Trigger, user_id: int, fingerprint: str) -> None:
    """Persist a trigger fire. Call only after the side effect (Telegram send) succeeds."""
    now = _utcnow().isoformat(sep=" ", timespec="seconds")
    with transaction() as conn:
        conn.execute(
            """
            insert into trigger_fires (trigger_name, user_id, fingerprint, fired_at)
            values (?, ?, ?, ?)
            """,
            (trigger.name, user_id, fingerprint, now),
        )
