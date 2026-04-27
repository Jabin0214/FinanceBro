"""Per-user runtime state shared across tool implementations.

`active_user_id` lets a tool know whose request it is currently serving
(set by the bot layer before each `chat()` call). `pending_files` is a
queue of files produced by tools (e.g. HTML reports) that the bot will
flush back to Telegram after the AI turn finishes.
"""

from contextvars import ContextVar

_active_user_id: ContextVar[int | None] = ContextVar("active_user_id", default=None)
_pending_files: dict[int, list[dict]] = {}


def set_active_user(user_id: int) -> object:
    """Bind the current tool-execution context to a Telegram user."""
    return _active_user_id.set(user_id)


def reset_active_user(token: object) -> None:
    _active_user_id.reset(token)


def current_user_id() -> int:
    user_id = _active_user_id.get()
    if user_id is None:
        raise RuntimeError("No active user bound; call set_active_user() first")
    return user_id


def queue_file(user_id: int, path: str, filename: str, caption: str) -> None:
    _pending_files.setdefault(user_id, []).append({
        "path": path,
        "filename": filename,
        "caption": caption,
    })


def pop_pending_files(user_id: int) -> list[dict]:
    """Drain the queued files for `user_id`. Bot calls this after each chat()."""
    return _pending_files.pop(user_id, [])
