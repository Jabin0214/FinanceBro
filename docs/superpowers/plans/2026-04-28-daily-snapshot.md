# Daily Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily IBKR snapshot scheduler and basic SQLite history query helpers.

**Architecture:** Extend config with typed daily snapshot settings. Add `bot/scheduler.py` to register and run a daily Telegram JobQueue task. Extend `storage/portfolio_store.py` with read helpers for latest snapshots, dates, and symbol history.

**Tech Stack:** Python standard library `datetime`, `zoneinfo`; `python-telegram-bot` JobQueue API; SQLite via existing storage layer; pytest.

---

### Task 1: Configuration

**Files:**
- Modify: `config.py`
- Test: `tests/test_config.py`

- [ ] Write tests for enabled flag, user id, time parsing, timezone default, and notification default.
- [ ] Run tests and confirm they fail because settings do not exist.
- [ ] Implement small config helpers and constants.
- [ ] Run focused config tests.

### Task 2: Scheduler

**Files:**
- Create: `bot/scheduler.py`
- Modify: `bot/telegram_bot.py`
- Test: `tests/scheduler/test_scheduler.py`

- [ ] Write tests for disabled scheduler, enabled scheduler registration, and callback execution.
- [ ] Run tests and confirm they fail because scheduler module does not exist.
- [ ] Implement scheduler registration and callback.
- [ ] Wire `setup_jobs(app)` into `build_app()`.
- [ ] Run focused scheduler tests.

### Task 3: History Query Helpers

**Files:**
- Modify: `storage/portfolio_store.py`
- Test: `tests/storage/test_portfolio_queries.py`

- [ ] Write tests for latest snapshot, snapshot dates, and position history.
- [ ] Run tests and confirm they fail because helpers do not exist.
- [ ] Implement read helpers.
- [ ] Run focused storage tests.

### Task 4: Verification and Docs

**Files:**
- Modify: `README.md`

- [ ] Document daily snapshot env vars.
- [ ] Run `python -m pytest -v`.
- [ ] Run `git diff --check`.
- [ ] Commit changes.
