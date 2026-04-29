from pathlib import Path


def test_dockerignore_excludes_persistent_data_and_sqlite_files():
    patterns = Path(".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "data/" in patterns
    assert "*.db" in patterns
    assert "*.sqlite" in patterns
    assert "*.sqlite3" in patterns
