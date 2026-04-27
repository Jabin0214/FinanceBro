"""Per-user conversation history (in-memory, cleared on restart)."""

_histories: dict[int, list[dict]] = {}


def get(user_id: int) -> list[dict]:
    return _histories.get(user_id, [])


def set(user_id: int, history: list[dict]) -> None:
    _histories[user_id] = history


def clear(user_id: int) -> None:
    _histories.pop(user_id, None)
