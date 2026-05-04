"""Telegram command and message handlers."""

import asyncio
import logging
import os
import tempfile
from html import escape
from uuid import uuid4

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from agent.historian import analyze_history
from agent.orchestrator import chat
from agent.tools import risk as risk_tool
from agent.tools import watchlist as watchlist_tool
from agent.tools import pop_pending_files, reset_active_user, set_active_user
from agent.tools.news import _get_news
from bot import history
from bot import proactive
from bot.auth import is_allowed, is_private_chat
from bot.messaging import send_html_with_fallback, typing_indicator
from ibkr.flex_query import fetch_flex_report
from report.html_report import build_html_file
from storage.portfolio_store import get_portfolio_history_summary, save_portfolio_report
from storage.investor_profile_store import get_investor_profile, update_investor_profile
from storage.watchlist_store import (
    add_watchlist_item,
    list_watchlist_items,
    remove_watchlist_item,
    update_watchlist_research,
)

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
        "/profile — 查看或设置投资画像\n"
        "/alerts — 立即检查持仓阈值预警\n"
        "/history — 查看最近 30 天组合复盘\n"
        "/watchlist — 管理观察列表\n"
        "/scout  — 运行观察列表 Scout Agent\n"
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
            profile = await asyncio.to_thread(get_investor_profile, user_id)
            await send_html_with_fallback(update.message, proactive.build_opening_brief(report, profile))
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
        await send_html_with_fallback(update.message, await asyncio.to_thread(analyze_history, summary))
    except Exception:
        logger.exception("历史快照命令失败")
        await update.message.reply_text(
            f"❌ <b>历史快照查询失败</b>\n<code>{_user_error_text()}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    args = context.args or []
    try:
        if args and args[0].lower() == "set":
            fields = _parse_profile_fields(args[1:])
            if not fields:
                await update.message.reply_text(
                    "用法：/profile set risk balanced max 35 cash 5 horizon medium markets US notes 说明"
                )
                return
            await asyncio.to_thread(update_investor_profile, user_id, **fields)
            await update.message.reply_text("投资画像已更新。")
            return

        profile = await asyncio.to_thread(get_investor_profile, user_id)
        await send_html_with_fallback(update.message, _format_profile(profile))
    except Exception:
        logger.exception("投资画像命令失败")
        await update.message.reply_text(
            f"❌ <b>投资画像操作失败</b>\n<code>{_user_error_text()}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    args = context.args or []
    action = args[0].lower() if args else "list"

    try:
        if action == "add" and len(args) >= 2:
            symbol = args[1]
            note = " ".join(args[2:]).strip()
            await asyncio.to_thread(add_watchlist_item, user_id, symbol, note)
            await update.message.reply_text(f"已加入观察列表：{symbol.upper()}")
            return

        if action in {"remove", "rm", "delete"} and len(args) >= 2:
            symbol = args[1]
            removed = await asyncio.to_thread(remove_watchlist_item, user_id, symbol)
            text = f"已移出观察列表：{symbol.upper()}" if removed else f"观察列表里没有 {symbol.upper()}"
            await update.message.reply_text(text)
            return

        if action == "scout":
            await cmd_scout(update, context)
            return

        if action == "set" and len(args) >= 2:
            fields = _parse_watchlist_fields(args[2:])
            if not fields:
                await update.message.reply_text(
                    "用法：/watchlist set AAPL status waiting trigger 175 thesis 逻辑 risk 风险点"
                )
                return
            await asyncio.to_thread(update_watchlist_research, user_id, args[1], **fields)
            await update.message.reply_text(f"已更新观察研究字段：{args[1].upper()}")
            return

        if action != "list":
            await update.message.reply_text(
                "用法：/watchlist add AAPL 备注，/watchlist set AAPL status waiting trigger 175，/watchlist remove AAPL，/watchlist"
            )
            return

        items = await asyncio.to_thread(list_watchlist_items, user_id)
        await send_html_with_fallback(update.message, _format_watchlist(items))
    except Exception:
        logger.exception("观察列表命令失败")
        await update.message.reply_text(
            f"❌ <b>观察列表操作失败</b>\n<code>{_user_error_text()}</code>",
            parse_mode=ParseMode.HTML,
        )


async def cmd_scout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized_private(update):
        await update.message.reply_text(_DENIED)
        return

    user_id = update.effective_user.id
    async with typing_indicator(context.bot, update.effective_chat.id):
        try:
            token = set_active_user(user_id)
            try:
                result = await asyncio.to_thread(watchlist_tool.execute, {})
            finally:
                reset_active_user(token)
            await send_html_with_fallback(update.message, result)
        except Exception:
            logger.exception("Watchlist Scout 命令失败")
            await update.message.reply_text(
                f"❌ <b>Watchlist Scout 失败</b>\n<code>{_user_error_text()}</code>",
                parse_mode=ParseMode.HTML,
            )


def _format_watchlist(items: list[dict]) -> str:
    if not items:
        return "观察列表为空。发送 /watchlist add AAPL 备注 来添加标的。"
    lines = ["<b>观察列表</b>", ""]
    for item in items:
        note = item.get("note", "")
        status = item.get("status") or "watching"
        head = f"{escape(item['symbol'])} — {escape(status)}"
        if note:
            head += f" — {escape(note)}"
        lines.append(head)
        if item.get("thesis"):
            lines.append(f"  关注逻辑：{escape(item['thesis'])}")
        if item.get("trigger_price") is not None:
            lines.append(f"  买入/跟踪触发：{item['trigger_price']}")
        if item.get("risk_note"):
            lines.append(f"  风险点：{escape(item['risk_note'])}")
    return "\n".join(lines)


def _format_profile(profile: dict) -> str:
    markets = profile.get("preferred_markets") or "未设置"
    notes = profile.get("notes") or "未设置"
    return (
        "<b>投资画像</b>\n\n"
        f"风险偏好：{escape(str(profile.get('risk_level', 'balanced')))}\n"
        f"投资期限：{escape(str(profile.get('time_horizon', 'medium')))}\n"
        f"单一持仓上限：{float(profile.get('max_position_weight_pct', 35.0)):.1f}%\n"
        f"现金底线：{float(profile.get('cash_floor_pct', 5.0)):.1f}%\n"
        f"偏好市场：{escape(str(markets))}\n"
        f"备注：{escape(str(notes))}"
    )


def _parse_profile_fields(args: list[str]) -> dict:
    key_map = {
        "risk": "risk_level",
        "horizon": "time_horizon",
        "max": "max_position_weight_pct",
        "cash": "cash_floor_pct",
        "markets": "preferred_markets",
        "notes": "notes",
    }
    numeric = {"max_position_weight_pct", "cash_floor_pct"}
    return _parse_key_value_fields(args, key_map, numeric)


def _parse_watchlist_fields(args: list[str]) -> dict:
    key_map = {
        "status": "status",
        "thesis": "thesis",
        "trigger": "trigger_price",
        "risk": "risk_note",
    }
    return _parse_key_value_fields(args, key_map, {"trigger_price"})


def _parse_key_value_fields(args: list[str], key_map: dict[str, str], numeric: set[str]) -> dict:
    fields = {}
    i = 0
    while i < len(args):
        key = args[i].lower()
        field = key_map.get(key)
        if field is None:
            i += 1
            continue
        i += 1
        values = []
        while i < len(args) and args[i].lower() not in key_map:
            values.append(args[i])
            i += 1
        if not values:
            continue
        value = " ".join(values).strip()
        if field in numeric:
            try:
                fields[field] = float(value)
            except ValueError:
                continue
        else:
            fields[field] = value
    return fields


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
