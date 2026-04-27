"""Telegram user whitelist."""

from config import TELEGRAM_ALLOWED_USERS


def is_allowed(user_id: int) -> bool:
    """Empty whitelist means unrestricted access."""
    return not TELEGRAM_ALLOWED_USERS or user_id in TELEGRAM_ALLOWED_USERS
