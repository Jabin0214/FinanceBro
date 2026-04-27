"""Telegram application wiring.

Commands:
  /start   — show help
  /report  — fetch IBKR portfolio HTML report (no AI, saves tokens)
  /clear   — clear current conversation history

Plain text → routed to the Orchestrator agent (Claude Sonnet); the agent
auto-invokes tools (portfolio, news, risk, report) as needed.
"""

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.handlers import cmd_clear, cmd_report, cmd_start, handle_message
from config import TELEGRAM_BOT_TOKEN


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
