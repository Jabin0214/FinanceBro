"""Telegram user authorization."""

from config import TELEGRAM_ALLOW_ALL, TELEGRAM_ALLOWED_USERS


def is_allowed(user_id: int) -> bool:
    """Allow listed users, or everyone only when explicitly configured."""
    return TELEGRAM_ALLOW_ALL or user_id in TELEGRAM_ALLOWED_USERS
