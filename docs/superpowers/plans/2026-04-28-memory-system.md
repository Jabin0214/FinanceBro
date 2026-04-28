# Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build durable SQLite memory for Telegram chat history and daily IBKR portfolio snapshots.

**Architecture:** Add a `storage/` package for SQLite initialization, chat message persistence, and portfolio snapshot persistence. Keep existing bot/orchestrator interfaces stable by making `bot/history.py` delegate to SQLite. Mount `/app/data` through Docker Compose so the database survives rebuilds.

**Tech Stack:** Python standard library `sqlite3`, `json`, `pathlib`; pytest for behavior tests; Docker Compose bind mount for persistence.

---

## File Structure

- Create `storage/__init__.py`: package marker.
- Create `storage/db.py`: SQLite path resolution, schema initialization, connection and transaction helpers.
- Create `storage/memory.py`: per-user conversation history persistence.
- Create `storage/portfolio_store.py`: raw IBKR report and daily portfolio snapshot persistence.
- Modify `bot/history.py`: keep public `get`, `set`, `clear` API and delegate to `storage.memory`.
- Modify `bot/handlers.py`: save portfolio snapshot after `/report` fetch succeeds.
- Modify `docker-compose.yml`: mount `./data:/app/data`.
- Add `.gitignore`: ignore local database files and worktree data.
- Add tests under `tests/storage/` and `tests/bot/`.

### Task 1: SQLite Foundation

**Files:**
- Create: `storage/__init__.py`
- Create: `storage/db.py`
- Test: `tests/storage/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
import sqlite3

from storage import db


def test_connect_initializes_schema(tmp_path, monkeypatch):
    db_path = tmp_path / "financebro.db"
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(db_path))

    with db.connect() as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }

    assert db_path.exists()
    assert {
        "chat_messages",
        "raw_reports",
        "portfolio_snapshots",
        "position_snapshots",
        "cash_snapshots",
    }.issubset(tables)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/storage/test_db.py -v`
Expected: FAIL because `storage` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `storage/db.py` with `get_db_path()`, `connect()`, `transaction()`, and schema creation.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/storage/test_db.py -v`
Expected: PASS.

### Task 2: Conversation Memory

**Files:**
- Create: `storage/memory.py`
- Modify: `bot/history.py`
- Test: `tests/storage/test_memory.py`

- [ ] **Step 1: Write failing tests**

```python
from bot import history


def test_history_round_trips_complex_message_content(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]

    history.set(42, messages)

    assert history.get(42) == messages


def test_history_set_replaces_existing_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    history.set(42, [{"role": "user", "content": "old"}])

    history.set(42, [{"role": "user", "content": "new"}])

    assert history.get(42) == [{"role": "user", "content": "new"}]


def test_history_clear_deletes_user_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    history.set(42, [{"role": "user", "content": "keep?"}])

    history.clear(42)

    assert history.get(42) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/storage/test_memory.py -v`
Expected: FAIL because `bot.history` still uses in-memory storage.

- [ ] **Step 3: Write minimal implementation**

Implement `storage.memory.get_history`, `set_history`, `clear_history`, and delegate `bot/history.py` to those functions.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/storage/test_memory.py -v`
Expected: PASS.

### Task 3: Portfolio Snapshot Store

**Files:**
- Create: `storage/portfolio_store.py`
- Test: `tests/storage/test_portfolio_store.py`

- [ ] **Step 1: Write failing tests**

Use a small structured report containing one account, one position, and one cash balance. Assert raw report, account snapshot, position, and cash rows are written.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/storage/test_portfolio_store.py -v`
Expected: FAIL because `storage.portfolio_store` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `save_portfolio_report(user_id, report)` with transactionally replaced daily snapshots.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/storage/test_portfolio_store.py -v`
Expected: PASS.

### Task 4: Wire Report Handler and Persistence Config

**Files:**
- Modify: `bot/handlers.py`
- Modify: `docker-compose.yml`
- Add or modify: `.gitignore`
- Test: `tests/bot/test_report_persistence.py`

- [ ] **Step 1: Write failing test**

Patch `bot.handlers.fetch_flex_report`, `bot.handlers.build_html_file`, and `bot.handlers.save_portfolio_report`. Call `cmd_report` with a fake Telegram update and assert `save_portfolio_report(user_id, data)` is called.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bot/test_report_persistence.py -v`
Expected: FAIL because handler does not call `save_portfolio_report`.

- [ ] **Step 3: Write minimal implementation**

Import and call `save_portfolio_report(user_id, data)` immediately after `fetch_flex_report()` succeeds. Add the Docker volume and gitignore entries.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/storage tests/bot -v`
Expected: PASS.

### Task 5: Full Verification

**Files:**
- All files changed above.

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest -v`
Expected: all collected tests pass.

- [ ] **Step 2: Inspect git diff**

Run: `git diff --stat && git diff --check`
Expected: no whitespace errors and changes limited to memory system files.
