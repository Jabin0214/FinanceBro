"""Shared model-output cleanup for Telegram-safe agent replies."""

from __future__ import annotations

import re

_STRIP_PATTERNS = [
    re.compile(r"<\s*g?\s*rok\s*:\s*render\b[^>]*>.*?<\s*/\s*g?\s*rok\s*:\s*render\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*g?\s*rok\s*:\s*render\b[^>]*/?>", re.IGNORECASE),
    re.compile(r"<argument\s+name=\"citation_id\">\s*\d+\s*</argument>", re.IGNORECASE),
    re.compile(r"\[\[\s*\d+\s*\]\]\([^)]*\)"),
    re.compile(r"\[\[\s*\d+\s*\]\]"),
    re.compile(r"\[\s*\d+\s*\]"),
    re.compile(r"https?://\S+"),
    re.compile(r"\*\*"),
    re.compile(r"__"),
    re.compile(r"`"),
    re.compile(r"#+\s*"),
]


def sanitize_model_output(text: str, allowed_tags: tuple[str, ...] = ("b", "i")) -> str:
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub("", text)
    text = text.replace("🟡", "⚪")
    allowed = "|".join(re.escape(tag) for tag in allowed_tags)
    text = re.sub(rf"<(?!/?(?:{allowed})\b)[^>]+>", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
