"""Scheduled background jobs for FinanceBro."""

from __future__ import annotations

import asyncio
import logging

from config import (
    DAILY_SNAPSHOT_ENABLED,
    DAILY_SNAPSHOT_NOTIFY,
    DAILY_SNAPSHOT_TIME,
    DAILY_SNAPSHOT_USER_ID,
    PROACTIVE_ALERT_ENABLED,
    PROACTIVE_ALERT_TIME,
    PROACTIVE_ALERT_USER_ID,
    PROACTIVE_BRIEF_ENABLED,
    PROACTIVE_BRIEF_TIME,
    PROACTIVE_BRIEF_USER_ID,
    PROACTIVE_NEWS_ENABLED,
    PROACTIVE_NEWS_INTERVAL_MINUTES,
    PROACTIVE_NEWS_USER_ID,
)
from bot.proactive import news_monitor_job, opening_brief_job, threshold_alert_job
from ibkr.flex_query import fetch_flex_report
from storage.portfolio_store import save_portfolio_report

logger = logging.getLogger(__name__)


def setup_jobs(app) -> None:
    if not any([DAILY_SNAPSHOT_ENABLED, PROACTIVE_BRIEF_ENABLED, PROACTIVE_ALERT_ENABLED, PROACTIVE_NEWS_ENABLED]):
        logger.info("scheduled jobs disabled")
        return

    if app.job_queue is None:
        raise RuntimeError("JobQueue is unavailable; install python-telegram-bot[job-queue]")

    if DAILY_SNAPSHOT_ENABLED:
        if DAILY_SNAPSHOT_USER_ID is None:
            raise RuntimeError("DAILY_SNAPSHOT_USER_ID is required when daily snapshots are enabled")
        app.job_queue.run_daily(
            daily_snapshot_job,
            time=DAILY_SNAPSHOT_TIME,
            name="daily_portfolio_snapshot",
        )
        app.job_queue.run_once(
            daily_snapshot_job,
            when=10,
            name="startup_portfolio_snapshot",
        )
        logger.info("daily portfolio snapshot scheduled at %s with startup catch-up", DAILY_SNAPSHOT_TIME)

    if PROACTIVE_BRIEF_ENABLED:
        if PROACTIVE_BRIEF_USER_ID is None:
            raise RuntimeError("PROACTIVE_BRIEF_USER_ID is required when opening brief is enabled")
        app.job_queue.run_daily(opening_brief_job, time=PROACTIVE_BRIEF_TIME, name="opening_brief")
        logger.info("opening brief scheduled at %s", PROACTIVE_BRIEF_TIME)

    if PROACTIVE_ALERT_ENABLED:
        if PROACTIVE_ALERT_USER_ID is None:
            raise RuntimeError("PROACTIVE_ALERT_USER_ID is required when threshold alerts are enabled")
        app.job_queue.run_daily(
            threshold_alert_job,
            time=PROACTIVE_ALERT_TIME,
            name="portfolio_threshold_alert",
        )
        logger.info("portfolio threshold alert scheduled at %s", PROACTIVE_ALERT_TIME)

    if PROACTIVE_NEWS_ENABLED:
        if PROACTIVE_NEWS_USER_ID is None:
            raise RuntimeError("PROACTIVE_NEWS_USER_ID is required when news monitor is enabled")
        interval_seconds = PROACTIVE_NEWS_INTERVAL_MINUTES * 60
        app.job_queue.run_repeating(
            news_monitor_job,
            interval=interval_seconds,
            first=60,
            name="news_and_earnings_monitor",
        )
        logger.info("news and earnings monitor scheduled every %s minutes", PROACTIVE_NEWS_INTERVAL_MINUTES)


async def daily_snapshot_job(context) -> None:
    user_id = DAILY_SNAPSHOT_USER_ID
    if user_id is None:
        logger.error("daily snapshot skipped: missing DAILY_SNAPSHOT_USER_ID")
        return

    try:
        data, snapshot_ids = await asyncio.to_thread(_fetch_and_save_snapshot, user_id)
    except Exception as e:
        logger.exception("daily IBKR snapshot failed")
        await _notify(
            context,
            user_id,
            f"❌ 每日 IBKR 持仓快照失败：{e}",
        )
        return

    report_date = data.get("report_date", "unknown")
    logger.info(
        "daily IBKR snapshot saved for user %s report_date=%s accounts=%s",
        user_id,
        report_date,
        len(snapshot_ids),
    )
    await _notify(
        context,
        user_id,
        f"✅ 每日 IBKR 持仓快照已保存：{report_date}（{len(snapshot_ids)} 个账户）",
    )


def _fetch_and_save_snapshot(user_id: int) -> tuple[dict, list[int]]:
    data = fetch_flex_report()
    snapshot_ids = save_portfolio_report(user_id, data)
    return data, snapshot_ids


async def _notify(context, user_id: int, text: str) -> None:
    if not DAILY_SNAPSHOT_NOTIFY:
        return

    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.info(
            "daily snapshot notification failed for user %s",
            user_id,
            exc_info=True,
        )
