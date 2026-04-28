# Daily Snapshot Design

## Goal

Automatically fetch the IBKR Flex report once per day and store it in SQLite, then expose small read helpers for future history-aware agent tools.

## Scope

This change adds a scheduled background job inside the Telegram bot process. It does not add AI access to historical data yet, and it does not add proactive daily analysis messages beyond a small operational success/failure notification.

## Configuration

The scheduler is controlled by environment variables:

- `DAILY_SNAPSHOT_ENABLED`: defaults to `false`; accepts `1`, `true`, `yes`, or `on`.
- `DAILY_SNAPSHOT_USER_ID`: required when enabled; identifies the user id used for saved snapshots and Telegram notifications.
- `DAILY_SNAPSHOT_TIME`: defaults to `07:00`; uses 24-hour `HH:MM`.
- `DAILY_SNAPSHOT_TIMEZONE`: defaults to `Pacific/Auckland`.
- `DAILY_SNAPSHOT_NOTIFY`: defaults to `true`; sends success/failure messages to the configured user.

## Architecture

Add `bot/scheduler.py` to own scheduled snapshot registration and execution. `bot/telegram_bot.py` calls `setup_jobs(app)` after registering handlers. The scheduled callback calls `fetch_flex_report()` and `save_portfolio_report(user_id, data)`.

Add query helpers to `storage/portfolio_store.py`:

- `get_latest_snapshot(user_id)`
- `get_snapshot_dates(user_id, limit=30)`
- `get_position_history(user_id, symbol, limit=30)`

These helpers keep SQL close to the persistence layer and give the future agent tool a clean interface.

## Error Handling

If scheduling is disabled or missing `DAILY_SNAPSHOT_USER_ID`, no job is scheduled. Invalid time strings raise a configuration error during startup so the deployment fails clearly.

The job logs success and failure. On failure, it sends a short Telegram message when notifications are enabled, then re-raises nothing so polling continues.

## Testing

Tests cover configuration parsing, job registration, job execution, and history query helpers using temporary SQLite databases and monkeypatched fetch/save calls.
