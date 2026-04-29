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
        "PROACTIVE_BRIEF_ENABLED",
        "PROACTIVE_BRIEF_USER_ID",
        "PROACTIVE_BRIEF_TIME",
        "PROACTIVE_BRIEF_TIMEZONE",
        "PROACTIVE_ALERT_ENABLED",
        "PROACTIVE_ALERT_TIME",
        "PROACTIVE_ALERT_TIMEZONE",
        "PROACTIVE_ALERT_PNL_PCT",
        "PROACTIVE_ALERT_POSITION_WEIGHT_PCT",
        "PROACTIVE_NEWS_ENABLED",
        "PROACTIVE_NEWS_INTERVAL_MINUTES",
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


def test_proactive_push_defaults_follow_snapshot_user(monkeypatch):
    cfg = _reload_config(monkeypatch, TELEGRAM_ALLOWED_USERS="42,99")

    assert cfg.PROACTIVE_BRIEF_ENABLED is True
    assert cfg.PROACTIVE_BRIEF_USER_ID == 42
    assert cfg.PROACTIVE_BRIEF_TIME == time(8, 30, tzinfo=ZoneInfo("Pacific/Auckland"))
    assert cfg.PROACTIVE_ALERT_ENABLED is True
    assert cfg.PROACTIVE_ALERT_USER_ID == 42
    assert cfg.PROACTIVE_ALERT_PNL_PCT == -5.0
    assert cfg.PROACTIVE_ALERT_POSITION_WEIGHT_PCT == 35.0
    assert cfg.PROACTIVE_NEWS_ENABLED is False


def test_proactive_push_parses_settings(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        TELEGRAM_ALLOWED_USERS="42",
        PROACTIVE_BRIEF_ENABLED="false",
        PROACTIVE_BRIEF_USER_ID="99",
        PROACTIVE_BRIEF_TIME="09:15",
        PROACTIVE_BRIEF_TIMEZONE="UTC",
        PROACTIVE_ALERT_ENABLED="true",
        PROACTIVE_ALERT_TIME="10:05",
        PROACTIVE_ALERT_TIMEZONE="UTC",
        PROACTIVE_ALERT_PNL_PCT="-8.5",
        PROACTIVE_ALERT_POSITION_WEIGHT_PCT="40",
        PROACTIVE_NEWS_ENABLED="true",
        PROACTIVE_NEWS_INTERVAL_MINUTES="120",
    )

    assert cfg.PROACTIVE_BRIEF_ENABLED is False
    assert cfg.PROACTIVE_BRIEF_USER_ID == 99
    assert cfg.PROACTIVE_BRIEF_TIME == time(9, 15, tzinfo=ZoneInfo("UTC"))
    assert cfg.PROACTIVE_ALERT_ENABLED is True
    assert cfg.PROACTIVE_ALERT_TIME == time(10, 5, tzinfo=ZoneInfo("UTC"))
    assert cfg.PROACTIVE_ALERT_PNL_PCT == -8.5
    assert cfg.PROACTIVE_ALERT_POSITION_WEIGHT_PCT == 40.0
    assert cfg.PROACTIVE_NEWS_ENABLED is True
    assert cfg.PROACTIVE_NEWS_INTERVAL_MINUTES == 120
