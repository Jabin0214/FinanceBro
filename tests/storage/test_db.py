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


def test_connect_configures_sqlite_for_bot_workload(tmp_path, monkeypatch):
    db_path = tmp_path / "financebro.db"
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(db_path))

    with db.connect() as conn:
        journal_mode = conn.execute("pragma journal_mode").fetchone()[0]
        busy_timeout = conn.execute("pragma busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert busy_timeout >= 5000


def test_trigger_fires_table_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))

    from storage.db import connect

    conn = connect()
    cur = conn.execute(
        "select name from sqlite_master where type='table' and name='trigger_fires'"
    )
    assert cur.fetchone() is not None

    cols = {r[1] for r in conn.execute("pragma table_info(trigger_fires)").fetchall()}
    assert {"id", "trigger_name", "user_id", "fingerprint", "fired_at"}.issubset(cols)
    conn.close()
