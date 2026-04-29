"""Telegram user authorization."""

from config import TELEGRAM_ALLOW_ALL, TELEGRAM_ALLOWED_USERS


def is_allowed(user_id: int) -> bool:
    """Allow listed users, or everyone only when explicitly configured."""
    return TELEGRAM_ALLOW_ALL or user_id in TELEGRAM_ALLOWED_USERS


def is_private_chat(chat_type: str | None) -> bool:
    """Finance data should only be sent in 1:1 Telegram chats."""
    return chat_type == "private"
