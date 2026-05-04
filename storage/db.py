"""SQLite connection and schema management."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Iterator

DEFAULT_DB_PATH = "/app/data/financebro.db"


def get_db_path() -> Path:
    return Path(os.getenv("FINANCEBRO_DB_PATH", DEFAULT_DB_PATH))


def connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma busy_timeout = 5000")
    conn.execute("pragma journal_mode = wal")
    _init_schema(conn)
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists chat_messages (
            user_id integer not null,
            idx integer not null,
            role text not null,
            content_json text not null,
            created_at text not null default current_timestamp,
            primary key (user_id, idx)
        );

        create table if not exists raw_reports (
            id integer primary key autoincrement,
            user_id integer not null,
            report_date text not null,
            source text not null,
            payload_json text not null,
            created_at text not null default current_timestamp,
            unique (user_id, report_date, source)
        );

        create table if not exists portfolio_snapshots (
            id integer primary key autoincrement,
            user_id integer not null,
            account_id text not null,
            report_date text not null,
            alias text not null default '',
            base_currency text not null default '',
            net_liquidation real not null default 0,
            stock_value_base real not null default 0,
            cash_base real not null default 0,
            total_unrealized_pnl_base real not null default 0,
            total_cost_base real not null default 0,
            total_unrealized_pnl_pct real not null default 0,
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp,
            unique (user_id, account_id, report_date)
        );

        create table if not exists position_snapshots (
            id integer primary key autoincrement,
            snapshot_id integer not null references portfolio_snapshots(id) on delete cascade,
            symbol text not null,
            description text not null default '',
            currency text not null default '',
            asset_category text not null default '',
            quantity real not null default 0,
            cost_price real not null default 0,
            mark_price real not null default 0,
            market_value real not null default 0,
            market_value_base real not null default 0,
            cost_basis real not null default 0,
            cost_basis_base real not null default 0,
            unrealized_pnl real not null default 0,
            unrealized_pnl_base real not null default 0,
            unrealized_pnl_pct real not null default 0,
            fx_rate real not null default 1
        );

        create table if not exists cash_snapshots (
            id integer primary key autoincrement,
            snapshot_id integer not null references portfolio_snapshots(id) on delete cascade,
            currency text not null,
            ending_cash real not null default 0,
            ending_cash_base real not null default 0
        );

        create table if not exists watchlist_items (
            user_id integer not null,
            symbol text not null,
            note text not null default '',
            status text not null default 'watching',
            thesis text not null default '',
            trigger_price real,
            risk_note text not null default '',
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp,
            primary key (user_id, symbol)
        );

        create table if not exists investor_profiles (
            user_id integer primary key,
            risk_level text not null default 'balanced',
            time_horizon text not null default 'medium',
            max_position_weight_pct real not null default 35,
            cash_floor_pct real not null default 5,
            preferred_markets text not null default '',
            notes text not null default '',
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        );
        """
    )
    _ensure_column(conn, "watchlist_items", "status", "text not null default 'watching'")
    _ensure_column(conn, "watchlist_items", "thesis", "text not null default ''")
    _ensure_column(conn, "watchlist_items", "trigger_price", "real")
    _ensure_column(conn, "watchlist_items", "risk_note", "text not null default ''")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"pragma table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"alter table {table} add column {column} {definition}")
