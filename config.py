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

# IBKR TWS / IB Gateway（Phase 4）
IBKR_TWS_HOST      = os.getenv("IBKR_TWS_HOST", "127.0.0.1")
IBKR_TWS_PORT      = int(os.getenv("IBKR_TWS_PORT", "4001"))   # IB Gateway 实盘:4001 / 模拟:4002
IBKR_TWS_CLIENT_ID = int(os.getenv("IBKR_TWS_CLIENT_ID", "10"))

# 模型分工
ORCHESTRATOR_MODEL = "claude-sonnet-4-6"   # 调度 + 格式化
ANALYZER_MODEL = "claude-opus-4-6"          # 深度分析（Phase 3+）
