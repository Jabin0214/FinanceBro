from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from bot import scheduler


class FakeJobQueue:
    def __init__(self):
        self.calls = []

    def run_daily(self, callback, time, name):
        self.calls.append({"callback": callback, "time": time, "name": name})


def test_setup_jobs_skips_when_disabled(monkeypatch):
    job_queue = FakeJobQueue()
    app = SimpleNamespace(job_queue=job_queue)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_ENABLED", False)

    scheduler.setup_jobs(app)

    assert job_queue.calls == []


def test_setup_jobs_registers_daily_snapshot(monkeypatch):
    job_queue = FakeJobQueue()
    app = SimpleNamespace(job_queue=job_queue)
    run_at = time(7, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_ENABLED", True)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_USER_ID", 42)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_TIME", run_at)

    scheduler.setup_jobs(app)

    assert job_queue.calls == [
        {
            "callback": scheduler.daily_snapshot_job,
            "time": run_at,
            "name": "daily_portfolio_snapshot",
        }
    ]


def test_setup_jobs_requires_user_id_when_enabled(monkeypatch):
    app = SimpleNamespace(job_queue=FakeJobQueue())
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_ENABLED", True)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_USER_ID", None)

    with pytest.raises(RuntimeError, match="DAILY_SNAPSHOT_USER_ID"):
        scheduler.setup_jobs(app)


@pytest.mark.anyio
async def test_daily_snapshot_job_fetches_and_saves(monkeypatch):
    report = {"report_date": "2026-04-28", "accounts": []}
    saved = []
    messages = []
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_USER_ID", 42)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_NOTIFY", True)
    monkeypatch.setattr(scheduler, "fetch_flex_report", lambda: report)
    monkeypatch.setattr(
        scheduler,
        "save_portfolio_report",
        lambda user_id, data: saved.append((user_id, data)) or [7],
    )

    async def send_message(chat_id, text, parse_mode=None):
        messages.append((chat_id, text, parse_mode))

    context = SimpleNamespace(bot=SimpleNamespace(send_message=send_message))

    await scheduler.daily_snapshot_job(context)

    assert saved == [(42, report)]
    assert messages == [(42, "✅ 每日 IBKR 持仓快照已保存：2026-04-28（1 个账户）", None)]


@pytest.mark.anyio
async def test_daily_snapshot_job_runs_fetch_and_save_in_thread(monkeypatch):
    calls = []
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_USER_ID", 42)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_NOTIFY", False)

    async def fake_to_thread(func, *args):
        calls.append((func, args))
        return {"report_date": "2026-04-28"}, [7]

    monkeypatch.setattr(scheduler.asyncio, "to_thread", fake_to_thread)
    context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))

    await scheduler.daily_snapshot_job(context)

    assert calls == [(scheduler._fetch_and_save_snapshot, (42,))]


@pytest.mark.anyio
async def test_daily_snapshot_success_notification_failure_is_best_effort(monkeypatch):
    saved = []
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_USER_ID", 42)
    monkeypatch.setattr(scheduler, "DAILY_SNAPSHOT_NOTIFY", True)
    monkeypatch.setattr(
        scheduler,
        "_fetch_and_save_snapshot",
        lambda user_id: ({"report_date": "2026-04-28"}, saved.append(user_id) or [7]),
    )

    async def failing_send_message(chat_id, text):
        raise RuntimeError("telegram unavailable")

    context = SimpleNamespace(bot=SimpleNamespace(send_message=failing_send_message))

    await scheduler.daily_snapshot_job(context)

    assert saved == [42]


@pytest.fixture
def anyio_backend():
    return "asyncio"
