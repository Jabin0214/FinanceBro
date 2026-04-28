"""Telegram command and message handlers."""

import asyncio
import logging
import os
import tempfile
from uuid import uuid4

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from agent.orchestrator import chat
from agent.tools import pop_pending_files, reset_active_user, set_active_user
from bot import history
from bot.auth import is_allowed
from bot.messaging import send_html_with_fallback, typing_indicator
from ibkr.flex_query import fetch_flex_report
from report.html_report import build_html_file
from storage.portfolio_store import save_portfolio_report

logger = logging.getLogger(__name__)

_DENIED = "⛔ 未授权"


async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update.effective_user.id):
        await update.message.reply_text(_DENIED)
        return

    await update.message.reply_text(
        "👋 <b>FinanceBro</b> 已就绪\n\n"
        "💬 <b>直接发消息</b>即可与 AI 对话，可询问持仓、盈亏分析等\n\n"
        "📋 <b>命令</b>\n"
        "/report — 直接获取持仓 HTML 报告\n"
        "/clear  — 清除对话历史",
        parse_mode=ParseMode.HTML,
    )


async def cmd_report(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text(_DENIED)
        return

    status_msg = await update.message.reply_text("⏳ 正在从 IBKR 获取报告，请稍候...")
    try:
        data = fetch_flex_report()
        save_portfolio_report(user_id, data)
        report_date = data.get("report_date", "report").replace("-", "")
        tmp_path = os.path.join(
            tempfile.gettempdir(),
            f"ibkr_report_{report_date}_{user_id}_{uuid4().hex[:8]}.html",
        )
        build_html_file(data, tmp_path)

        await status_msg.delete()
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"ibkr_report_{report_date}.html",
                    caption=f"📊 IBKR 持仓报告 {data.get('report_date', '')}",
                )
        finally:
            os.remove(tmp_path)
    except Exception as e:
        logger.exception("获取报告失败")
        await status_msg.edit_text(
            f"❌ <b>获取报告失败</b>\n<code>{e}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text(_DENIED)
        return

    history.clear(user_id)
    await update.message.reply_text("🗑 对话历史已清除")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text(_DENIED)
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    async with typing_indicator(context.bot, update.effective_chat.id):
        try:
            token = set_active_user(user_id)
            try:
                reply, new_history, usage = await asyncio.to_thread(
                    chat, history.get(user_id), user_text
                )
            finally:
                reset_active_user(token)
            history.set(user_id, new_history)

            await send_html_with_fallback(update.message, reply)
            await _flush_pending_files(update, user_id)
            await _send_usage_footer(update, usage)

        except Exception as e:
            logger.exception("对话处理失败")
            await update.message.reply_text(
                f"❌ <b>出错了</b>\n<code>{e}</code>",
                parse_mode=ParseMode.HTML,
            )


async def _flush_pending_files(update: Update, user_id: int) -> None:
    for f in pop_pending_files(user_id):
        try:
            with open(f["path"], "rb") as fh:
                await update.message.reply_document(
                    document=fh,
                    filename=f["filename"],
                    caption=f["caption"],
                )
        finally:
            os.remove(f["path"])


async def _send_usage_footer(update: Update, usage: dict) -> None:
    cache_hit = usage.get("cache_read_tokens", 0)
    cache_hint = f" · 💾 {cache_hit:,} cached" if cache_hit else ""
    await update.message.reply_text(
        f"<i>📊 {usage['input_tokens']:,} in · {usage['output_tokens']:,} out"
        f"{cache_hint} · ${usage['cost_usd']:.4f}</i>",
        parse_mode=ParseMode.HTML,
    )
