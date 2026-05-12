import pytest
from storage.allocation_store import get_targets, set_targets


def test_set_and_get_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    set_targets(42, {"AAPL": 30.0, "MSFT": 20.0})
    result = get_targets(42)
    assert result == {"AAPL": 30.0, "MSFT": 20.0}


def test_set_targets_replaces_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    set_targets(42, {"AAPL": 30.0})
    set_targets(42, {"MSFT": 40.0, "GOOGL": 25.0})
    result = get_targets(42)
    assert result == {"MSFT": 40.0, "GOOGL": 25.0}
    assert "AAPL" not in result


def test_get_targets_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    result = get_targets(999)
    assert result == {}


def test_set_targets_upcases_symbols(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    set_targets(42, {"aapl": 30.0, "msft": 20.0})
    result = get_targets(42)
    assert "AAPL" in result
    assert "MSFT" in result
    assert "aapl" not in result
