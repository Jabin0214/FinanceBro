"""Persistent per-user conversation history."""

from __future__ import annotations

import json

from storage import db


def get_history(user_id: int) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            select role, content_json
            from chat_messages
            where user_id = ?
            order by idx
            """,
            (user_id,),
        ).fetchall()

    return [
        {"role": row["role"], "content": json.loads(row["content_json"])}
        for row in rows
    ]


def set_history(user_id: int, history: list[dict]) -> None:
    with db.transaction() as conn:
        conn.execute("delete from chat_messages where user_id = ?", (user_id,))
        conn.executemany(
            """
            insert into chat_messages (user_id, idx, role, content_json)
            values (?, ?, ?, ?)
            """,
            [
                (
                    user_id,
                    idx,
                    msg["role"],
                    json.dumps(msg["content"], ensure_ascii=False),
                )
                for idx, msg in enumerate(history)
            ],
        )


def clear_history(user_id: int) -> None:
    with db.transaction() as conn:
        conn.execute("delete from chat_messages where user_id = ?", (user_id,))
