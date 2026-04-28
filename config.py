import os
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _parse_daily_snapshot_time(raw: str, timezone: str) -> time:
    try:
        hour_raw, minute_raw = raw.split(":", 1)
        hour = int(hour_raw)
        minute = int(minute_raw)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError as e:
        raise ValueError("DAILY_SNAPSHOT_TIME must use HH:MM 24-hour format") from e

    return time(hour, minute, tzinfo=ZoneInfo(timezone))


# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOWED_USERS = [
    int(uid.strip())
    for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
]

# IBKR Flex Query
IBKR_FLEX_TOKEN = os.getenv("IBKR_FLEX_TOKEN")
IBKR_FLEX_QUERY_ID = os.getenv("IBKR_FLEX_QUERY_ID")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# xAI (Grok) — 新闻搜索
GROK_API_KEY = os.getenv("GROK_API_KEY")

# 模型分工
ORCHESTRATOR_MODEL = "claude-sonnet-4-6"   # 调度 + 格式化

# Daily portfolio snapshot
_daily_snapshot_enabled_default = "true" if TELEGRAM_ALLOWED_USERS else "false"
DAILY_SNAPSHOT_ENABLED = os.getenv(
    "DAILY_SNAPSHOT_ENABLED",
    _daily_snapshot_enabled_default,
).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DAILY_SNAPSHOT_USER_ID = (
    int(os.getenv("DAILY_SNAPSHOT_USER_ID"))
    if os.getenv("DAILY_SNAPSHOT_USER_ID")
    else (TELEGRAM_ALLOWED_USERS[0] if TELEGRAM_ALLOWED_USERS else None)
)
DAILY_SNAPSHOT_TIMEZONE = os.getenv("DAILY_SNAPSHOT_TIMEZONE", "Pacific/Auckland")
DAILY_SNAPSHOT_TIME = _parse_daily_snapshot_time(
    os.getenv("DAILY_SNAPSHOT_TIME", "07:00"),
    DAILY_SNAPSHOT_TIMEZONE,
)
DAILY_SNAPSHOT_NOTIFY = os.getenv("DAILY_SNAPSHOT_NOTIFY", "true").lower() not in {
    "0",
    "false",
    "no",
    "off",
}
