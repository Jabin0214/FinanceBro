import os
from dotenv import load_dotenv

load_dotenv()

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
ANALYZER_MODEL = "claude-opus-4-6"          # 深度分析（Phase 3+）
