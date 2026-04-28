from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot import handlers


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_cmd_report_saves_portfolio_snapshot(monkeypatch, tmp_path):
    report = {"report_date": "2026-04-28", "accounts": []}
    saved = []

    def fake_build_html_file(_data, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("<html></html>")

    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers, "fetch_flex_report", lambda: report)
    monkeypatch.setattr(handlers, "build_html_file", fake_build_html_file)
    monkeypatch.setattr(
        handlers,
        "save_portfolio_report",
        lambda user_id, data: saved.append((user_id, data)),
        raising=False,
    )

    status_msg = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
    message = SimpleNamespace(
        reply_text=AsyncMock(return_value=status_msg),
        reply_document=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
    )

    await handlers.cmd_report(update, None)

    assert saved == [(42, report)]
    message.reply_document.assert_awaited_once()


@pytest.mark.anyio
async def test_cmd_report_runs_blocking_work_in_thread(monkeypatch, tmp_path):
    calls = []
    report_path = tmp_path / "report.html"
    report_path.write_text("<html></html>", encoding="utf-8")

    async def fake_to_thread(func, *args):
        calls.append((func, args))
        return {"report_date": "2026-04-28"}, "20260428", str(report_path)

    monkeypatch.setattr(handlers, "is_allowed", lambda _user_id: True)
    monkeypatch.setattr(handlers.asyncio, "to_thread", fake_to_thread)

    status_msg = SimpleNamespace(delete=AsyncMock(), edit_text=AsyncMock())
    message = SimpleNamespace(
        reply_text=AsyncMock(return_value=status_msg),
        reply_document=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=42),
        message=message,
    )

    await handlers.cmd_report(update, None)

    assert calls == [(handlers._prepare_report_file, (42,))]
