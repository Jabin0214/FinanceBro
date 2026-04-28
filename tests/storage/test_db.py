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
