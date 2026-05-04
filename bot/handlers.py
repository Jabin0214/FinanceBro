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
from storage.portfolio_store import get_portfolio_history_summary, save_portfolio_report

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
        "/history — 查看最近 30 天组合复盘\n"
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
        summary = await asyncio.to_thread(get_portfolio_history_summary, user_id, 30)
        if summary.get("snapshot_count", 0) == 0:
            await send_html_with_fallback(update.message, "暂无历史快照。先发送 /report 或等待每日自动快照。")
            return
        await send_html_with_fallback(update.message, _format_history_recap(summary))
    except Exception:
        logger.exception("历史快照命令失败")
        await update.message.reply_text(
            f"❌ <b>历史快照查询失败</b>\n<code>{_user_error_text()}</code>",
            parse_mode=ParseMode.HTML,
        )


def _format_history_recap(summary: dict) -> str:
    days = summary.get("period_days", 30)
    start_date = summary.get("start_date", "unknown")
    end_date = summary.get("end_date", "unknown")
    totals = summary.get("totals", {})

    lines = [
        "<b>组合复盘</b>",
        "",
        f"周期：过去 {days} 天（{start_date} 至 {end_date}）",
        f"快照：{summary.get('snapshot_count', 0)} 个交易日",
    ]

    metric_lines = [
        _format_change_line("净值", totals.get("net_liquidation")),
        _format_change_line("现金", totals.get("cash_base")),
        _format_change_line("浮盈亏", totals.get("total_unrealized_pnl_base")),
    ]
    lines.extend(line for line in metric_lines if line)

    position_lines = _format_position_changes(summary.get("position_changes", []))
    if position_lines:
        lines.extend(["", "<b>主要持仓变化</b>", *position_lines])

    contributor_lines = _format_pnl_contributors(summary.get("top_unrealized_pnl_contributors", []))
    if contributor_lines:
        lines.extend(["", "<b>主要浮盈亏贡献</b>", *contributor_lines])

    return "\n".join(lines)


def _format_change_line(label: str, change: dict | None) -> str:
    if not change:
        return ""
    start = float(change.get("start") or 0)
    end = float(change.get("end") or 0)
    delta = float(change.get("change") or 0)
    pct = change.get("change_pct")
    pct_text = "n/a" if pct is None else f"{float(pct):+.1f}%"
    return f"{label}：${start:,.2f} -> ${end:,.2f}（{delta:+,.2f}，{pct_text}）"


def _format_position_changes(changes: list[dict]) -> list[str]:
    status_labels = {
        "opened": "开仓",
        "closed": "清仓",
        "increased": "加仓",
        "decreased": "减仓",
        "unchanged": "持仓不变",
    }
    lines = []
    for item in changes[:5]:
        symbol = item.get("symbol", "")
        if not symbol:
            continue
        status = status_labels.get(item.get("status"), item.get("status", "变化"))
        quantity = abs(float(item.get("quantity_change") or 0))
        market_value_change = float(item.get("market_value_change_base") or 0)
        lines.append(
            f"{symbol} {status} {quantity:,.2f} 股"
            f"（市值变化 {market_value_change:+,.2f}）"
        )
    return lines


def _format_pnl_contributors(contributors: list[dict]) -> list[str]:
    lines = []
    for item in contributors[:3]:
        symbol = item.get("symbol", "")
        if not symbol:
            continue
        pnl = float(item.get("unrealized_pnl_base") or 0)
        lines.append(f"{symbol}：{pnl:+,.2f}")
    return lines


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
