"""Scheduled background jobs for FinanceBro."""

from __future__ import annotations

import asyncio
import logging

from config import (
    DAILY_SNAPSHOT_ENABLED,
    DAILY_SNAPSHOT_NOTIFY,
    DAILY_SNAPSHOT_TIME,
    DAILY_SNAPSHOT_USER_ID,
)
from ibkr.flex_query import fetch_flex_report
from storage.portfolio_store import save_portfolio_report

logger = logging.getLogger(__name__)


def setup_jobs(app) -> None:
    if not DAILY_SNAPSHOT_ENABLED:
        logger.info("daily portfolio snapshot disabled")
        return

    if DAILY_SNAPSHOT_USER_ID is None:
        raise RuntimeError("DAILY_SNAPSHOT_USER_ID is required when daily snapshots are enabled")
    if app.job_queue is None:
        raise RuntimeError("JobQueue is unavailable; install python-telegram-bot[job-queue]")

    app.job_queue.run_daily(
        daily_snapshot_job,
        time=DAILY_SNAPSHOT_TIME,
        name="daily_portfolio_snapshot",
    )
    logger.info("daily portfolio snapshot scheduled at %s", DAILY_SNAPSHOT_TIME)


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
