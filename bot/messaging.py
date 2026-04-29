"""Telegram message helpers: chunking, HTML-with-fallback send, typing heartbeat."""

import asyncio
from contextlib import asynccontextmanager

from telegram import Message
from telegram.constants import ParseMode
from telegram.error import BadRequest

TELEGRAM_TEXT_LIMIT = 4000
_TYPING_INTERVAL_S = 4


def split_long(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    """Split text into Telegram-sized chunks on paragraph boundaries."""
    if len(text) <= limit:
        return [text]

    parts, current = [], ""
    for para in text.split("\n\n"):
        if len(para) > limit:
            if current:
                parts.append(current)
                current = ""
            parts.extend(_split_hard(para, limit))
            continue

        if len(current) + len(para) + 2 <= limit:
            current = current + ("\n\n" if current else "") + para
        else:
            if current:
                parts.append(current)
            current = para
    if current:
        parts.append(current)
    return parts


def _split_hard(text: str, limit: int) -> list[str]:
    return [text[i:i + limit] for i in range(0, len(text), limit)]


async def send_html_with_fallback(message: Message, text: str) -> None:
    """Send `text` as HTML, falling back to plain text if Telegram rejects the markup."""
    for chunk in split_long(text):
        try:
            await message.reply_text(chunk, parse_mode=ParseMode.HTML)
        except BadRequest:
            await message.reply_text(chunk)


@asynccontextmanager
async def typing_indicator(bot, chat_id: int):
    """Keep a 'typing…' indicator alive until the block exits."""
    stop = asyncio.Event()

    async def _loop():
        while not stop.is_set():
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(_TYPING_INTERVAL_S)

    task = asyncio.create_task(_loop())
    try:
        yield
    finally:
        stop.set()
        task.cancel()
