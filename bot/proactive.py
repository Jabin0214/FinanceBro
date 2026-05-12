"""Phase 6 proactive portfolio pushes."""

from __future__ import annotations

import asyncio
import hashlib
import logging

from telegram.constants import ParseMode

from agent.news_impact import rank_news_by_impact
from agent.risk_calculator import compute_metrics
from agent.tools.news import _get_news
from config import (
    DRIFT_ALERT_THRESHOLD_PCT,
    DRIFT_ALERT_USER_ID,
    PROACTIVE_ALERT_PNL_PCT,
    PROACTIVE_ALERT_POSITION_WEIGHT_PCT,
    PROACTIVE_ALERT_USER_ID,
    PROACTIVE_BRIEF_USER_ID,
    PROACTIVE_NEWS_USER_ID,
)
from bot.triggers import Trigger, record_fire, should_fire
from agent.rebalancing import compute_rebalancing
from storage.allocation_store import get_targets
from ibkr.flex_query import fetch_flex_report
from storage.portfolio_store import get_latest_portfolio_report, get_net_liquidation_series, save_portfolio_report

logger = logging.getLogger(__name__)

_THRESHOLD_ALERT_TRIGGER = Trigger(
    name="alert.threshold",
    cooldown_seconds=12 * 3600,
    max_fires_per_day=3,
)

_NEWS_MONITOR_TRIGGER = Trigger(
    name="news.monitor",
    cooldown_seconds=4 * 3600,
    max_fires_per_day=4,
)

_DRIFT_ALERT_TRIGGER = Trigger(
    name="drift.alert",
    cooldown_seconds=12 * 3600,
    max_fires_per_day=2,
)


async def opening_brief_job(context) -> None:
    user_id = PROACTIVE_BRIEF_USER_ID
    if user_id is None:
        logger.error("opening brief skipped: missing PROACTIVE_BRIEF_USER_ID")
        return

    try:
        report = await asyncio.to_thread(_fetch_and_save, user_id)
        nlv_series = await asyncio.to_thread(get_net_liquidation_series, user_id, 2)
        await _send(context, user_id, build_opening_brief(report, nlv_series=nlv_series))
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
        if not should_fire(_THRESHOLD_ALERT_TRIGGER, user_id=user_id, fingerprint=key):
            logger.info("threshold alert skipped: trigger dedup")
            return

        await _send(
            context,
            user_id,
            "<b>持仓阈值预警</b>\n\n" + "\n".join(f"🔴 {alert}" for alert in alerts),
        )
        record_fire(_THRESHOLD_ALERT_TRIGGER, user_id=user_id, fingerprint=key)
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
        weights = _position_weights(report)
        impact_summary = ""
        if weights:
            lines = [line.strip() for line in digest.splitlines() if line.strip()]
            ranked = rank_news_by_impact(lines, weights=weights)
            top = [r for r in ranked if r["impact"] != 0][:3]
            if top:
                impact_summary = "<b>影响排序（前 3 条）</b>\n" + "\n".join(
                    f"{'🟢' if r['impact'] > 0 else '🔴'} {', '.join(r['symbols']) or '—'}"
                    f"（影响分 {r['impact']:.1f}）：{r['headline']}"
                    for r in top
                ) + "\n\n"
        key = _fingerprint(user_id, report.get("report_date", ""), digest[:500])
        if not should_fire(_NEWS_MONITOR_TRIGGER, user_id=user_id, fingerprint=key):
            logger.info("news monitor skipped: trigger dedup")
            return

        await _send(
            context,
            user_id,
            "<b>重大新闻 / 财报提醒</b>\n\n" + impact_summary + digest,
        )
        record_fire(_NEWS_MONITOR_TRIGGER, user_id=user_id, fingerprint=key)
    except Exception:
        logger.exception("news monitor failed")
        await _send(context, user_id, "❌ 新闻与财报提醒检查失败。")


async def drift_alert_job(context) -> None:
    user_id = DRIFT_ALERT_USER_ID
    if user_id is None:
        logger.error("drift alert skipped: missing DRIFT_ALERT_USER_ID")
        return

    try:
        report = await asyncio.to_thread(get_latest_portfolio_report, user_id)
        if not report:
            logger.info("drift alert skipped: no saved portfolio")
            return

        targets = get_targets(user_id)
        if not targets:
            logger.info("drift alert skipped: no targets set")
            return

        metrics = compute_metrics(report)
        if "error" in metrics:
            logger.info("drift alert skipped: %s", metrics["error"])
            return

        total_nlv = metrics["total_net_liquidation"]
        # Build current_weights using net_liquidation as denominator so that
        # drift reflects how each position sits within the total portfolio value
        # (including cash), matching the semantics of user-defined target allocations.
        nlv_weights = [
            {
                "symbol": pos["symbol"],
                "weight_pct": round(pos["market_value_base"] / total_nlv * 100, 2)
                if total_nlv > 0 else 0.0,
                "market_value_base": pos["market_value_base"],
            }
            for pos in metrics["concentration"]
        ]

        drift_result = compute_rebalancing(
            current_weights=nlv_weights,
            targets=targets,
            total_portfolio_value=total_nlv,
        )
        if "error" in drift_result:
            logger.info("drift alert skipped: %s", drift_result["error"])
            return

        if drift_result["max_drift_abs_pct"] < DRIFT_ALERT_THRESHOLD_PCT:
            logger.info(
                "drift alert skipped: max drift %.1f%% below threshold %.1f%%",
                drift_result["max_drift_abs_pct"],
                DRIFT_ALERT_THRESHOLD_PCT,
            )
            return

        top_drifts = sorted(
            drift_result["drift"], key=lambda r: abs(r["drift_pct"]), reverse=True
        )[:3]
        key = _fingerprint(user_id, report.get("report_date", ""), str(top_drifts))

        if not should_fire(_DRIFT_ALERT_TRIGGER, user_id=user_id, fingerprint=key):
            logger.info("drift alert skipped: trigger dedup")
            return

        lines = []
        for row in drift_result["drift"]:
            if row["drift_pct"] > 0:
                emoji, direction, trade_dir = "🔴", "超配", "卖出"
            else:
                emoji, direction, trade_dir = "🟡", "低配", "买入"
            trade_abs = abs(row["suggested_trade_base"])
            lines.append(
                f"{emoji} {row['symbol']}：{direction} {abs(row['drift_pct']):.1f}%"
                f"（建议{trade_dir} ${trade_abs:,.0f}）"
            )

        await _send(
            context,
            user_id,
            "<b>仓位偏离预警</b>\n\n"
            + "\n".join(lines)
            + f"\n\n最大偏离：{drift_result['max_drift_symbol']} "
            + f"{drift_result['max_drift_abs_pct']:.1f}%（阈值 {DRIFT_ALERT_THRESHOLD_PCT:.0f}%）",
        )
        record_fire(_DRIFT_ALERT_TRIGGER, user_id=user_id, fingerprint=key)
    except Exception:
        logger.exception("drift alert job failed")


def build_opening_brief(
    report: dict,
    nlv_series: list[tuple[str, float]] | None = None,
) -> str:
    metrics = compute_metrics(report)
    if "error" in metrics:
        return f"<b>开盘前简报</b>\n\n⚪ 暂无有效持仓数据：{metrics['error']}"

    pnl = metrics["pnl_summary"]
    pnl_emoji = "🟢" if pnl["total_pnl_pct"] >= 0 else "🔴"

    # NLV trend vs yesterday
    nlv_trend = ""
    if nlv_series and len(nlv_series) >= 2:
        prev_nlv = nlv_series[-2][1]
        curr_nlv = nlv_series[-1][1]
        if prev_nlv:
            delta = curr_nlv - prev_nlv
            delta_pct = delta / prev_nlv * 100
            trend_emoji = "📈" if delta >= 0 else "📉"
            sign = "+" if delta >= 0 else ""
            nlv_trend = (
                f"{trend_emoji} 净值变动：{sign}{delta:,.2f}"
                f"（{delta_pct:+.1f}%）vs 昨日\n"
            )

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
        f"{nlv_trend}"
        f"{pnl_emoji} 整体浮动：{pnl['total_pnl_pct']:.1f}%"
        f"（${pnl['total_unrealized_pnl']:,.2f}）\n"
        f"前五大持仓：{metrics['top5_concentration_pct']:.1f}% · HHI：{metrics['hhi']:,.0f}\n\n"
        "<b>主要持仓</b>\n"
        + "\n".join(top_lines)
        + "\n\n<b>风险提醒</b>\n"
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


def _position_weights(report: dict) -> dict[str, float]:
    """Return {symbol: weight_pct} from compute_metrics output."""
    metrics = compute_metrics(report)
    if "error" in metrics:
        return {}
    return {item["symbol"]: item["weight_pct"] for item in metrics.get("concentration", [])}


def _top_symbols(report: dict, limit: int) -> list[str]:
    positions = []
    for account in report.get("accounts", []):
        positions.extend(account.get("positions", []))
    positions.sort(key=lambda p: abs(float(p.get("market_value_base", 0) or 0)), reverse=True)
    return [p.get("symbol", "") for p in positions[:limit] if p.get("symbol")]


def _fingerprint(user_id: int, report_date: str, text: str) -> str:
    payload = f"{user_id}|{report_date}|{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
