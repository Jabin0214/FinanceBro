"""Per-user conversation history."""

from storage.memory import clear_history, get_history, set_history


def get(user_id: int) -> list[dict]:
    return get_history(user_id)


def set(user_id: int, history: list[dict]) -> None:
    set_history(user_id, history)


def clear(user_id: int) -> None:
    clear_history(user_id)
