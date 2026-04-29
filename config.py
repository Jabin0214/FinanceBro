import os
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _parse_time(raw: str, timezone: str, var_name: str) -> time:
    try:
        hour_raw, minute_raw = raw.split(":", 1)
        hour = int(hour_raw)
        minute = int(minute_raw)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except ValueError as e:
        raise ValueError(f"{var_name} must use HH:MM 24-hour format") from e

    return time(hour, minute, tzinfo=ZoneInfo(timezone))


def _parse_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _parse_falsey_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOW_ALL = os.getenv("TELEGRAM_ALLOW_ALL", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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
DAILY_SNAPSHOT_ENABLED = _parse_bool("DAILY_SNAPSHOT_ENABLED", _daily_snapshot_enabled_default)
DAILY_SNAPSHOT_USER_ID = (
    int(os.getenv("DAILY_SNAPSHOT_USER_ID"))
    if os.getenv("DAILY_SNAPSHOT_USER_ID")
    else (TELEGRAM_ALLOWED_USERS[0] if TELEGRAM_ALLOWED_USERS else None)
)
DAILY_SNAPSHOT_TIMEZONE = os.getenv("DAILY_SNAPSHOT_TIMEZONE", "Pacific/Auckland")
DAILY_SNAPSHOT_TIME = _parse_time(
    os.getenv("DAILY_SNAPSHOT_TIME", "07:00"),
    DAILY_SNAPSHOT_TIMEZONE,
    "DAILY_SNAPSHOT_TIME",
)
DAILY_SNAPSHOT_NOTIFY = _parse_falsey_bool("DAILY_SNAPSHOT_NOTIFY", "true")

# Phase 6 proactive push
PROACTIVE_BRIEF_ENABLED = _parse_bool(
    "PROACTIVE_BRIEF_ENABLED",
    "true" if DAILY_SNAPSHOT_ENABLED else "false",
)
PROACTIVE_BRIEF_USER_ID = (
    int(os.getenv("PROACTIVE_BRIEF_USER_ID"))
    if os.getenv("PROACTIVE_BRIEF_USER_ID")
    else DAILY_SNAPSHOT_USER_ID
)
PROACTIVE_BRIEF_TIMEZONE = os.getenv("PROACTIVE_BRIEF_TIMEZONE", DAILY_SNAPSHOT_TIMEZONE)
PROACTIVE_BRIEF_TIME = _parse_time(
    os.getenv("PROACTIVE_BRIEF_TIME", "08:30"),
    PROACTIVE_BRIEF_TIMEZONE,
    "PROACTIVE_BRIEF_TIME",
)

PROACTIVE_ALERT_ENABLED = _parse_bool(
    "PROACTIVE_ALERT_ENABLED",
    "true" if DAILY_SNAPSHOT_ENABLED else "false",
)
PROACTIVE_ALERT_USER_ID = (
    int(os.getenv("PROACTIVE_ALERT_USER_ID"))
    if os.getenv("PROACTIVE_ALERT_USER_ID")
    else DAILY_SNAPSHOT_USER_ID
)
PROACTIVE_ALERT_TIMEZONE = os.getenv("PROACTIVE_ALERT_TIMEZONE", DAILY_SNAPSHOT_TIMEZONE)
PROACTIVE_ALERT_TIME = _parse_time(
    os.getenv("PROACTIVE_ALERT_TIME", "08:35"),
    PROACTIVE_ALERT_TIMEZONE,
    "PROACTIVE_ALERT_TIME",
)
PROACTIVE_ALERT_PNL_PCT = float(os.getenv("PROACTIVE_ALERT_PNL_PCT", "-5"))
PROACTIVE_ALERT_POSITION_WEIGHT_PCT = float(
    os.getenv("PROACTIVE_ALERT_POSITION_WEIGHT_PCT", "35")
)

PROACTIVE_NEWS_ENABLED = _parse_bool("PROACTIVE_NEWS_ENABLED", "false")
PROACTIVE_NEWS_USER_ID = (
    int(os.getenv("PROACTIVE_NEWS_USER_ID"))
    if os.getenv("PROACTIVE_NEWS_USER_ID")
    else DAILY_SNAPSHOT_USER_ID
)
PROACTIVE_NEWS_INTERVAL_MINUTES = int(os.getenv("PROACTIVE_NEWS_INTERVAL_MINUTES", "180"))
