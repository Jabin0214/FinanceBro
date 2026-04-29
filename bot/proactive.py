"""Phase 6 proactive portfolio pushes."""

from __future__ import annotations

import asyncio
import hashlib
import logging

from telegram.constants import ParseMode

from agent.risk_calculator import compute_metrics
from agent.tools.news import _get_news
from config import (
    PROACTIVE_ALERT_PNL_PCT,
    PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
    PROACTIVE_ALERT_USER_ID,
    PROACTIVE_BRIEF_USER_ID,
    PROACTIVE_NEWS_USER_ID,
)
from ibkr.flex_query import fetch_flex_report
from storage.portfolio_store import save_portfolio_report

logger = logging.getLogger(__name__)

_sent_alert_keys: set[str] = set()
_sent_news_keys: set[str] = set()


async def opening_brief_job(context) -> None:
    user_id = PROACTIVE_BRIEF_USER_ID
    if user_id is None:
        logger.error("opening brief skipped: missing PROACTIVE_BRIEF_USER_ID")
        return

    try:
        report = await asyncio.to_thread(_fetch_and_save, user_id)
        await _send(context, user_id, build_opening_brief(report))
    except Exception:
        logger.exception("opening brief failed")
        await _send(context, user_id, "❌ 开盘前简报生成失败，请稍后手动发送 /report 检查。")


async def threshold_alert_job(context) -> None:
    user_id = PROACTIVE_ALERT_USER_ID
    if user_id is None:
        logger.error("threshold alert skipped: missing PROACTIVE_ALERT_USER_ID")
        return

    try:
        report = await asyncio.to_thread(_fetch_and_save, user_id)
        alerts = build_threshold_alerts(
            report,
            pnl_threshold_pct=PROACTIVE_ALERT_PNL_PCT,
            position_weight_threshold_pct=PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
        )
        if not alerts:
            logger.info("threshold alert skipped: no triggered alerts")
            return

        key = _fingerprint(user_id, report.get("report_date", ""), "\n".join(alerts))
        if key in _sent_alert_keys:
            logger.info("threshold alert skipped: duplicate alert key")
            return
        _sent_alert_keys.add(key)

        await _send(
            context,
            user_id,
            "<b>持仓阈值预警</b>\n\n" + "\n".join(f"🔴 {alert}" for alert in alerts),
        )
    except Exception:
        logger.exception("threshold alert failed")
        await _send(context, user_id, "❌ 持仓阈值预警检查失败，请稍后手动发送 /report 检查。")


async def news_monitor_job(context) -> None:
    user_id = PROACTIVE_NEWS_USER_ID
    if user_id is None:
        logger.error("news monitor skipped: missing PROACTIVE_NEWS_USER_ID")
        return

    try:
        report = await asyncio.to_thread(_fetch_and_save, user_id)
        symbols = _top_symbols(report, limit=5)
        if not symbols:
            logger.info("news monitor skipped: no symbols")
            return

        query = " ".join(symbols) + " major news earnings next earnings date market moving"
        digest = await asyncio.to_thread(_get_news, query)
        key = _fingerprint(user_id, report.get("report_date", ""), digest[:500])
        if key in _sent_news_keys:
            logger.info("news monitor skipped: duplicate digest")
            return
        _sent_news_keys.add(key)

        await _send(
            context,
            user_id,
            "<b>重大新闻 / 财报提醒</b>\n\n" + digest,
        )
    except Exception:
        logger.exception("news monitor failed")
        await _send(context, user_id, "❌ 新闻与财报提醒检查失败。")


def build_opening_brief(report: dict) -> str:
    metrics = compute_metrics(report)
    if "error" in metrics:
        return f"<b>开盘前简报</b>\n\n⚪ 暂无有效持仓数据：{metrics['error']}"

    pnl = metrics["pnl_summary"]
    pnl_emoji = "🟢" if pnl["total_pnl_pct"] >= 0 else "🔴"
    top = metrics["concentration"][:5]
    top_lines = [
        f"{item['symbol']} {item['weight_pct']:.1f}%（浮动 {item['unrealized_pnl_pct']:.1f}%）"
        for item in top
    ]
    alerts = build_threshold_alerts(
        report,
        pnl_threshold_pct=PROACTIVE_ALERT_PNL_PCT,
        position_weight_threshold_pct=PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
    )
    alert_text = "\n".join(f"🔴 {alert}" for alert in alerts) if alerts else "🟢 未触发风险阈值"

    return (
        "<b>开盘前简报</b>\n\n"
        f"日期：{report.get('report_date', 'unknown')}\n"
        f"净值：${metrics['total_net_liquidation']:,.2f}\n"
        f"{pnl_emoji} 整体浮动：{pnl['total_pnl_pct']:.1f}%"
        f"（${pnl['total_unrealized_pnl']:,.2f}）\n"
        f"前五大持仓：{metrics['top5_concentration_pct']:.1f}% · HHI：{metrics['hhi']:,.0f}\n\n"
        "<b>主要持仓</b>\n"
        + "\n".join(top_lines)
        + "\n\n<b>今日重点</b>\n"
        + alert_text
    )


def build_threshold_alerts(
    report: dict,
    pnl_threshold_pct: float,
    position_weight_threshold_pct: float,
) -> list[str]:
    metrics = compute_metrics(report)
    if "error" in metrics:
        return []

    alerts: list[str] = []
    pnl_pct = metrics["pnl_summary"]["total_pnl_pct"]
    if pnl_pct <= pnl_threshold_pct:
        alerts.append(f"整体浮亏 {pnl_pct:.1f}% 已触发 {pnl_threshold_pct:.1f}% 阈值")

    for pos in metrics["concentration"]:
        if pos["weight_pct"] >= position_weight_threshold_pct:
            alerts.append(
                f"{pos['symbol']} 单一持仓占比 {pos['weight_pct']:.1f}% "
                f"已触发 {position_weight_threshold_pct:.1f}% 阈值"
            )

    return alerts


def _fetch_and_save(user_id: int) -> dict:
    report = fetch_flex_report()
    save_portfolio_report(user_id, report)
    return report


async def _send(context, user_id: int, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.HTML)
    except Exception:
        logger.info("proactive notification failed for user %s", user_id, exc_info=True)


def _top_symbols(report: dict, limit: int) -> list[str]:
    positions = []
    for account in report.get("accounts", []):
        positions.extend(account.get("positions", []))
    positions.sort(key=lambda p: abs(float(p.get("market_value_base", 0) or 0)), reverse=True)
    return [p.get("symbol", "") for p in positions[:limit] if p.get("symbol")]


def _fingerprint(user_id: int, report_date: str, text: str) -> str:
    payload = f"{user_id}|{report_date}|{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
