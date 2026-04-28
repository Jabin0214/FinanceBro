import importlib
from datetime import time
from zoneinfo import ZoneInfo

import config


def _reload_config(monkeypatch, **env):
    keys = [
        "DAILY_SNAPSHOT_ENABLED",
        "DAILY_SNAPSHOT_USER_ID",
        "DAILY_SNAPSHOT_TIME",
        "DAILY_SNAPSHOT_TIMEZONE",
        "DAILY_SNAPSHOT_NOTIFY",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(config)


def test_daily_snapshot_defaults_to_disabled(monkeypatch):
    cfg = _reload_config(monkeypatch)

    assert cfg.DAILY_SNAPSHOT_ENABLED is False
    assert cfg.DAILY_SNAPSHOT_USER_ID is None
    assert cfg.DAILY_SNAPSHOT_TIME == time(7, 0, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert cfg.DAILY_SNAPSHOT_NOTIFY is True


def test_daily_snapshot_defaults_to_first_allowed_user(monkeypatch):
    cfg = _reload_config(monkeypatch, TELEGRAM_ALLOWED_USERS="42,99")

    assert cfg.DAILY_SNAPSHOT_ENABLED is True
    assert cfg.DAILY_SNAPSHOT_USER_ID == 42


def test_daily_snapshot_parses_enabled_settings(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        DAILY_SNAPSHOT_ENABLED="true",
        DAILY_SNAPSHOT_USER_ID="42",
        DAILY_SNAPSHOT_TIME="18:30",
        DAILY_SNAPSHOT_TIMEZONE="UTC",
        DAILY_SNAPSHOT_NOTIFY="false",
    )

    assert cfg.DAILY_SNAPSHOT_ENABLED is True
    assert cfg.DAILY_SNAPSHOT_USER_ID == 42
    assert cfg.DAILY_SNAPSHOT_TIME == time(18, 30, tzinfo=ZoneInfo("UTC"))
    assert cfg.DAILY_SNAPSHOT_NOTIFY is False


def test_daily_snapshot_invalid_time_fails_fast(monkeypatch):
    try:
        _reload_config(monkeypatch, DAILY_SNAPSHOT_TIME="7am")
    except ValueError as e:
        assert "DAILY_SNAPSHOT_TIME" in str(e)
    else:
        raise AssertionError("expected invalid time to raise")
