import os
from datetime import time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

def _parse_bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ALLOW_ALL = False
DEFAULT_TELEGRAM_USER_IDS = [8615575214]
TELEGRAM_ALLOWED_USERS = [
    int(uid.strip())
    for uid in os.getenv(
        "TELEGRAM_ALLOWED_USERS",
        ",".join(str(uid) for uid in DEFAULT_TELEGRAM_USER_IDS),
    ).split(",")
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

# Product defaults
APP_TIMEZONE = ZoneInfo("Pacific/Auckland")
DEFAULT_USER_ID = TELEGRAM_ALLOWED_USERS[0] if TELEGRAM_ALLOWED_USERS else None

# Daily portfolio snapshot
DAILY_SNAPSHOT_ENABLED = DEFAULT_USER_ID is not None
DAILY_SNAPSHOT_USER_ID = DEFAULT_USER_ID
DAILY_SNAPSHOT_TIME = time(7, 0, tzinfo=APP_TIMEZONE)
DAILY_SNAPSHOT_NOTIFY = True

# Phase 6 proactive push
PROACTIVE_BRIEF_ENABLED = DEFAULT_USER_ID is not None
PROACTIVE_BRIEF_USER_ID = DEFAULT_USER_ID
PROACTIVE_BRIEF_TIME = time(8, 30, tzinfo=APP_TIMEZONE)

PROACTIVE_ALERT_ENABLED = DEFAULT_USER_ID is not None
PROACTIVE_ALERT_USER_ID = DEFAULT_USER_ID
PROACTIVE_ALERT_TIME = time(8, 35, tzinfo=APP_TIMEZONE)
PROACTIVE_ALERT_PNL_PCT = -5.0
PROACTIVE_ALERT_POSITION_WEIGHT_PCT = 35.0

PROACTIVE_NEWS_ENABLED = _parse_bool("PROACTIVE_NEWS_ENABLED", "false")
PROACTIVE_NEWS_USER_ID = DEFAULT_USER_ID
PROACTIVE_NEWS_INTERVAL_MINUTES = 180
