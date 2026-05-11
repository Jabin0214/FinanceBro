from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "test.db"))


def test_trigger_fires_once_then_cooldown_blocks():
    from bot.triggers import Trigger, should_fire, record_fire

    t = Trigger(name="alert.threshold", cooldown_seconds=3600, max_fires_per_day=5)
    fp = "abc"

    assert should_fire(t, user_id=1, fingerprint=fp) is True
    record_fire(t, user_id=1, fingerprint=fp)
    assert should_fire(t, user_id=1, fingerprint=fp) is False


def test_trigger_distinguishes_fingerprints():
    from bot.triggers import Trigger, should_fire, record_fire

    t = Trigger(name="alert.threshold", cooldown_seconds=3600, max_fires_per_day=5)
    record_fire(t, user_id=1, fingerprint="abc")
    assert should_fire(t, user_id=1, fingerprint="def") is True


def test_trigger_daily_cap_blocks_unique_fingerprints():
    from bot.triggers import Trigger, should_fire, record_fire

    t = Trigger(name="alert.threshold", cooldown_seconds=0, max_fires_per_day=2)
    record_fire(t, user_id=1, fingerprint="a")
    record_fire(t, user_id=1, fingerprint="b")
    assert should_fire(t, user_id=1, fingerprint="c") is False


def test_trigger_cooldown_expires(monkeypatch):
    from bot.triggers import Trigger, should_fire, record_fire
    import bot.triggers as triggers_mod

    t = Trigger(name="alert.threshold", cooldown_seconds=10, max_fires_per_day=99)
    record_fire(t, user_id=1, fingerprint="same")

    future = datetime.now(timezone.utc) + timedelta(seconds=20)
    monkeypatch.setattr(triggers_mod, "_utcnow", lambda: future)
    assert should_fire(t, user_id=1, fingerprint="same") is True
