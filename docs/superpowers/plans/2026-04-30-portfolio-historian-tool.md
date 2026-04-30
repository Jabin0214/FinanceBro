# Portfolio Historian Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Portfolio Historian tool that lets the Orchestrator answer historical portfolio-change and review questions from stored SQLite snapshots.

**Architecture:** Keep deterministic history math in `storage/portfolio_store.py`, expose it through a focused `agent/tools/history.py` tool, and register that tool with the existing Anthropic tool registry. The Orchestrator prompt will steer historical questions toward this tool while current-account questions continue using `get_portfolio`.

**Tech Stack:** Python, SQLite, pytest, Anthropic tool definitions.

---

### Task 1: Historical Summary Query

**Files:**
- Modify: `storage/portfolio_store.py`
- Test: `tests/storage/test_portfolio_queries.py`

- [ ] Add a failing test that saves multiple snapshots and asserts a new `get_portfolio_history_summary(user_id, days)` helper returns newest/oldest portfolio totals, deltas, position changes, and top PnL contributors.
- [ ] Run `python -m pytest tests/storage/test_portfolio_queries.py -v` and verify the new import/function failure.
- [ ] Implement the helper using existing snapshot tables, with sane empty-history output.
- [ ] Re-run the storage query tests and verify they pass.

### Task 2: Tool Module and Registry

**Files:**
- Create: `agent/tools/history.py`
- Modify: `agent/tools/__init__.py`
- Test: `tests/agent/tools/test_history.py`

- [ ] Add failing tests for `get_portfolio_history` output and registry availability.
- [ ] Run focused tests and verify failure before implementation.
- [ ] Implement `agent/tools/history.py` with a `days` input defaulting to 30 and allowed values of 7, 30, or 90.
- [ ] Register the tool in `agent/tools/__init__.py`.
- [ ] Re-run focused tests and verify they pass.

### Task 3: Orchestrator Prompt

**Files:**
- Modify: `agent/orchestrator.py`

- [ ] Update the system prompt so questions about historical change, review, weekly/monthly summaries,加仓/减仓, and theme drift call `get_portfolio_history`.
- [ ] Run orchestrator/tool tests to verify existing behavior remains intact.

### Task 4: Verification

**Files:**
- All changed files

- [ ] Run `python -m pytest tests/storage/test_portfolio_queries.py tests/agent/tools/test_history.py tests/agent/test_orchestrator.py -v`.
- [ ] Run `python -m pytest -v`.
- [ ] Review `git diff` for scope and accidental README changes.
