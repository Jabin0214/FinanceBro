"""Telegram application wiring.

Commands:
  /start   — show help
  /report  — fetch IBKR portfolio HTML report (no AI, saves tokens)
  /risk    — run risk analysis
  /news    — search market news
  /brief   — generate opening brief now
  /profile — manage investing profile
  /alerts  — check threshold alerts now
  /history — summarize recent portfolio changes
  /watchlist — manage watchlist symbols
  /scout   — run Watchlist Scout
  /clear   — clear current conversation history

Plain text → routed to the Orchestrator agent (Claude Sonnet); the agent
auto-invokes tools (portfolio, news, risk, report) as needed.
"""

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import (
    cmd_alerts,
    cmd_brief,
    cmd_clear,
    cmd_history,
    cmd_news,
    cmd_profile,
    cmd_report,
    cmd_risk,
    cmd_scout,
    cmd_start,
    cmd_watchlist,
    handle_message,
)
from bot.scheduler import setup_jobs
from config import TELEGRAM_BOT_TOKEN


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("risk", cmd_risk))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("brief", cmd_brief))
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("scout", cmd_scout))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    setup_jobs(app)
    return app
