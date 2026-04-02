"""
Telegram Bot — Phase 2

命令：
  /start   — 显示帮助
  /report  — 直接获取 IBKR 持仓 HTML 报告（不走 AI，省 token）
  /clear   — 清除当前对话历史

普通消息：
  直接发送任意文字 → 与 Claude Sonnet 对话，按需自动调取持仓数据
"""

import asyncio
import logging
import tempfile
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS
from ibkr.flex_query import fetch_flex_report
from report.html_report import build_html_file
from agent.orchestrator import chat
from agent.tools import pop_pending_files

logger = logging.getLogger(__name__)

# 每个用户的对话历史，key 为 user_id，重启后清空
_histories: dict[int, list[dict]] = {}


def _is_allowed(user_id: int) -> bool:
    """白名单校验，空列表表示不限制。"""
    return not TELEGRAM_ALLOWED_USERS or user_id in TELEGRAM_ALLOWED_USERS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_allowed(update.effective_user.id):
        await update.message.reply_text("⛔ 未授权")
        return

    await update.message.reply_text(
        "👋 <b>FinanceBro</b> 已就绪\n\n"
        "💬 <b>直接发消息</b>即可与 AI 对话，可询问持仓、盈亏分析等\n\n"
        "📋 <b>命令</b>\n"
        "/report — 直接获取持仓 HTML 报告\n"
        "/clear  — 清除对话历史",
        parse_mode=ParseMode.HTML,
    )


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ 未授权")
        return

    status_msg = await update.message.reply_text("⏳ 正在从 IBKR 获取报告，请稍候...")

    try:
        raw_data = fetch_flex_report()
        report_date = raw_data.get("report_date", "report").replace("-", "")
        tmp_path = os.path.join(tempfile.gettempdir(), f"ibkr_report_{report_date}.html")
        build_html_file(raw_data, tmp_path)

        await status_msg.delete()
        try:
            with open(tmp_path, "rb") as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"ibkr_report_{report_date}.html",
                    caption=f"📊 IBKR 持仓报告 {raw_data.get('report_date', '')}",
                )
        finally:
            os.remove(tmp_path)

    except Exception as e:
        logger.exception(f"获取报告失败：{e}")
        await status_msg.edit_text(
            f"❌ <b>获取报告失败</b>\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ 未授权")
        return

    _histories.pop(user_id, None)
    await update.message.reply_text("🗑 对话历史已清除")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if not _is_allowed(user_id):
        await update.message.reply_text("⛔ 未授权")
        return

    user_text = update.message.text.strip()
    if not user_text:
        return

    history = _histories.get(user_id, [])

    # 持续发送 typing 状态（每 4s 刷新，直到 AI 回复完成）
    stop_typing = asyncio.Event()
    async def _keep_typing():
        while not stop_typing.is_set():
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(4)
    typing_task = asyncio.create_task(_keep_typing())

    try:
        reply, history, usage = await asyncio.to_thread(chat, history, user_text)
        _histories[user_id] = history

        # 超长消息分段发送，HTML 解析失败时降级为纯文本
        for chunk in _split(reply):
            try:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)
            except BadRequest:
                await update.message.reply_text(chunk)

        # 发送工具生成的文件（如 HTML 报表）
        for f in pop_pending_files():
            try:
                with open(f["path"], "rb") as fh:
                    await update.message.reply_document(
                        document=fh,
                        filename=f["filename"],
                        caption=f["caption"],
                    )
            finally:
                os.remove(f["path"])

        cache_hit = usage.get("cache_read_tokens", 0)
        cache_hint = f" · 💾 {cache_hit:,} cached" if cache_hit else ""
        await update.message.reply_text(
            f"<i>📊 {usage['input_tokens']:,} in · {usage['output_tokens']:,} out"
            f"{cache_hint} · ${usage['cost_usd']:.4f}</i>",
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.exception(f"对话处理失败：{e}")
        await update.message.reply_text(
            f"❌ <b>出错了</b>\n<code>{str(e)}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        stop_typing.set()
        typing_task.cancel()


def _split(text: str, limit: int = 4000) -> list[str]:
    """超长消息按段落切分。"""
    if len(text) <= limit:
        return [text]

    parts, current = [], ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 <= limit:
            current = current + ("\n\n" if current else "") + para
        else:
            if current:
                parts.append(current)
            current = para
    if current:
        parts.append(current)
    return parts


def build_app() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
