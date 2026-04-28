import importlib

from bot import history


def test_history_round_trips_complex_message_content(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
    ]

    history.set(42, messages)
    reloaded_history = importlib.reload(history)

    assert reloaded_history.get(42) == messages


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
