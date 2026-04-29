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
from agent.tools import risk as risk_tool
from agent.tools import pop_pending_files, reset_active_user, set_active_user
from agent.tools.news import _get_news
from bot import history
from bot import proactive
from bot.auth import is_allowed, is_private_chat
from bot.messaging import send_html_with_fallback, typing_indicator
from ibkr.flex_query import fetch_flex_report
from report.html_report import build_html_file
from storage.portfolio_store import get_snapshot_dates, save_portfolio_report

logger = logging.getLogger(__name__)

_DENIED = "⛔ 未授权"


def _is_authorized_private(update: Update) -> bool:
    return (
        update.effective_user is not None
        and update.effective_chat is not None
        and is_private_chat(update.effective_chat.type)
        and is_allowed(update.effective_user.id)
    )


def _user_error_text() -> str:
    return "请稍后重试；详细错误已写入服务日志。"


async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    await update.message.reply_text(
        "👋 <b>FinanceBro</b> 已就绪\n\n"
        "💬 <b>直接发消息</b>即可与 AI 对话，可询问持仓、盈亏分析等\n\n"
        "📋 <b>命令</b>\n"
        "/report — 直接获取持仓 HTML 报告\n"
        "/risk   — 立即运行风险分析 Agent\n"
        "/news AAPL — 搜索新闻 / 财报 / 市场动态\n"
        "/brief  — 立即生成开盘前简报\n"
        "/alerts — 立即检查持仓阈值预警\n"
        "/history — 查看最近快照日期\n"
        "/clear  — 清除对话历史",
        parse_mode=ParseMode.HTML,
    )


async def cmd_report(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    status_msg = await update.message.reply_text("⏳ 正在从 IBKR 获取报告，请稍候...")
    try:
        data, report_date, tmp_path = await asyncio.to_thread(_prepare_report_file, user_id)

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
    except Exception:
        logger.exception("获取报告失败")
        await status_msg.edit_text(
            f"❌ <b>获取报告失败</b>\n<code>{_user_error_text()}</code>",
            parse_mode=ParseMode.HTML,
        )


def _prepare_report_file(user_id: int) -> tuple[dict, str, str]:
    data = fetch_flex_report()
    save_portfolio_report(user_id, data)
    report_date = data.get("report_date", "report").replace("-", "")
    tmp_path = os.path.join(
        tempfile.gettempdir(),
        f"ibkr_report_{report_date}_{user_id}_{uuid4().hex[:8]}.html",
    )
    build_html_file(data, tmp_path)
    return data, report_date, tmp_path


async def cmd_clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    history.clear(user_id)
    await update.message.reply_text("🗑 对话历史已清除")


async def cmd_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    async with typing_indicator(context.bot, update.effective_chat.id):
        try:
            token = set_active_user(user_id)
            try:
                result = await asyncio.to_thread(risk_tool.execute, {})
            finally:
                reset_active_user(token)
            await send_html_with_fallback(update.message, result)
        except Exception:
            logger.exception("风险分析命令失败")
            await update.message.reply_text(
                f"❌ <b>风险分析失败</b>\n<code>{_user_error_text()}</code>",
                parse_mode=ParseMode.HTML,
            )


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    query = " ".join(context.args or []).strip()
    if not query:
        await update.message.reply_text("用法：/news AAPL earnings")
        return

    async with typing_indicator(context.bot, update.effective_chat.id):
        try:
            result = await asyncio.to_thread(_get_news, query)
            await send_html_with_fallback(update.message, result)
        except Exception:
            logger.exception("新闻命令失败")
            await update.message.reply_text(
                f"❌ <b>新闻搜索失败</b>\n<code>{_user_error_text()}</code>",
                parse_mode=ParseMode.HTML,
            )


async def cmd_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    async with typing_indicator(context.bot, update.effective_chat.id):
        try:
            report = await asyncio.to_thread(proactive._fetch_and_save, user_id)
            await send_html_with_fallback(update.message, proactive.build_opening_brief(report))
        except Exception:
            logger.exception("开盘简报命令失败")
            await update.message.reply_text(
                f"❌ <b>开盘简报生成失败</b>\n<code>{_user_error_text()}</code>",
                parse_mode=ParseMode.HTML,
            )


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    async with typing_indicator(context.bot, update.effective_chat.id):
        try:
            report = await asyncio.to_thread(proactive._fetch_and_save, user_id)
            alerts = proactive.build_threshold_alerts(
                report,
                pnl_threshold_pct=proactive.PROACTIVE_ALERT_PNL_PCT,
                position_weight_threshold_pct=proactive.PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
            )
            text = (
                "<b>持仓阈值预警</b>\n\n" + "\n".join(f"🔴 {alert}" for alert in alerts)
                if alerts
                else "🟢 当前未触发持仓阈值预警。"
            )
            await send_html_with_fallback(update.message, text)
        except Exception:
            logger.exception("阈值预警命令失败")
            await update.message.reply_text(
                f"❌ <b>阈值预警检查失败</b>\n<code>{_user_error_text()}</code>",
                parse_mode=ParseMode.HTML,
            )


async def cmd_history(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    try:
        dates = await asyncio.to_thread(get_snapshot_dates, user_id, 10)
        if not dates:
            await send_html_with_fallback(update.message, "暂无历史快照。先发送 /report 或等待每日自动快照。")
            return
        text = "<b>最近持仓快照</b>\n\n" + "\n".join(f"• {date}" for date in dates)
        await send_html_with_fallback(update.message, text)
    except Exception:
        logger.exception("历史快照命令失败")
        await update.message.reply_text(
            f"❌ <b>历史快照查询失败</b>\n<code>{_user_error_text()}</code>",
            parse_mode=ParseMode.HTML,
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
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

        except Exception:
            logger.exception("对话处理失败")
            await update.message.reply_text(
                f"❌ <b>出错了</b>\n<code>{_user_error_text()}</code>",
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
