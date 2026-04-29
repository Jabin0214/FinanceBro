import importlib
from datetime import time
from zoneinfo import ZoneInfo

import config


def _reload_config(monkeypatch, **env):
    keys = [
        "PROACTIVE_NEWS_ENABLED",
        "TELEGRAM_ALLOWED_USERS",
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
    assert cfg.PROACTIVE_NEWS_USER_ID == 42
    assert cfg.PROACTIVE_NEWS_INTERVAL_MINUTES == 180


def test_proactive_news_can_be_enabled_explicitly(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        TELEGRAM_ALLOWED_USERS="42",
        PROACTIVE_NEWS_ENABLED="true",
    )

    assert cfg.PROACTIVE_NEWS_ENABLED is True
