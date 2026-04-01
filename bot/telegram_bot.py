"""
Telegram Bot — Phase 1

命令：
  /start   — 显示帮助
  /report  — 获取 IBKR 持仓报告
"""

import logging
import tempfile
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS
from ibkr.flex_query import fetch_flex_report
from agent.html_report import build_html_file

logger = logging.getLogger(__name__)


def _is_allowed(user_id: int) -> bool:
    """白名单校验，空列表表示不限制。"""
    return not TELEGRAM_ALLOWED_USERS or user_id in TELEGRAM_ALLOWED_USERS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ 未授权")
        return

    await update.message.reply_text(
        "👋 <b>FinanceBro</b> 已就绪\n\n"
        "📋 <b>可用命令</b>\n"
        "/report — 获取当前持仓报告\n\n"
        "<i>更多功能陆续开放...</i>",
        parse_mode=ParseMode.HTML,
    )


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ 未授权")
        return

    # 发送等待提示
    status_msg = await update.message.reply_text("⏳ 正在从 IBKR 获取报告，请稍候...")

    try:
        # 1. 获取原始数据
        raw_data = fetch_flex_report()

        # 2. 生成 HTML 文件
        report_date = raw_data.get("report_date", "report").replace("-", "")
        tmp_path = os.path.join(tempfile.gettempdir(), f"ibkr_report_{report_date}.html")
        build_html_file(raw_data, tmp_path)

        # 3. 删除等待消息，发送 HTML 文件
        await status_msg.delete()
        with open(tmp_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"ibkr_report_{report_date}.html",
                caption=f"📊 IBKR 持仓报告 {raw_data.get('report_date', '')}",
            )
        os.remove(tmp_path)

    except Exception as e:
        logger.exception(f"获取报告失败：{e}")
        await status_msg.edit_text(
            f"❌ <b>获取报告失败</b>\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML,
        )


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    return app
