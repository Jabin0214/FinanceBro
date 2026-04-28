# FinanceBro Memory System Design

## Goal

Add durable memory to FinanceBro using SQLite so Telegram conversation history and daily IBKR portfolio snapshots survive Docker rebuilds and cloud redeployments.

## Scope

This version stores two kinds of memory:

- Conversation memory: per-user Anthropic message history currently kept only in `bot/history.py`.
- Portfolio memory: daily structured IBKR report snapshots, including account summaries, positions, cash balances, and the raw structured report payload.

Semantic embedding search, scheduled daily pulls, and proactive push notifications are outside this change.

## Architecture

Add a focused `storage/` package:

- `storage/db.py` owns the SQLite path, connection setup, schema creation, and transaction helper.
- `storage/memory.py` persists per-user chat history as JSON messages.
- `storage/portfolio_store.py` saves one portfolio snapshot per `(user_id, account_id, report_date)` and replaces the same day's positions/cash rows on repeated pulls.

The database file lives at `FINANCEBRO_DB_PATH` when set, otherwise `/app/data/financebro.db`. Docker Compose mounts `./data:/app/data`, so the cloud VM keeps the database at `/opt/financebro/data/financebro.db` across container rebuilds.

## Data Flow

On normal Telegram messages, handlers load history through `bot.history.get(user_id)`, call the orchestrator, then persist the updated history through `bot.history.set(user_id, history)`.

On `/clear`, handlers delete the user's conversation messages from SQLite.

On `/report`, after `fetch_flex_report()` succeeds, the handler calls `save_portfolio_report(user_id, data)`. The raw structured report is saved once per user/date, and each account snapshot is upserted by user, account, and report date. Re-running `/report` for the same day replaces the rows for that snapshot instead of creating duplicates.

The `get_portfolio` tool continues to fetch current IBKR data without writing snapshots, because tool calls can happen repeatedly during chat and should not unexpectedly mutate daily history.

## Tables

- `chat_messages`: `user_id`, sequential `idx`, `role`, JSON `content`, and `created_at`.
- `raw_reports`: `user_id`, `report_date`, source name, JSON payload, and `created_at`.
- `portfolio_snapshots`: one row per user/account/report date with account summary fields.
- `position_snapshots`: one row per position inside a portfolio snapshot.
- `cash_snapshots`: one row per cash balance inside a portfolio snapshot.

## Error Handling

SQLite schema initialization runs before every connection. Parent directories are created automatically.

History reads return an empty list if no rows exist. Invalid JSON is not expected because writes always serialize through `json.dumps`.

Portfolio saves run inside a transaction. If any row fails, the transaction rolls back and the Telegram handler reports the original `/report` failure path.

## Testing

Add pytest coverage using temporary database files via `FINANCEBRO_DB_PATH`:

- Database initialization creates schema in an empty temp path.
- Conversation history can be saved, loaded, replaced, and cleared.
- Portfolio report saving creates raw report, account snapshot, positions, and cash rows.
- Saving the same user/account/date twice replaces snapshot child rows instead of duplicating them.
