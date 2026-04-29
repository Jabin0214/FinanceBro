import importlib

import bot.auth as auth
import config


def _reload_auth(monkeypatch, **env):
    keys = ["TELEGRAM_ALLOWED_USERS", "TELEGRAM_ALLOW_ALL"]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(config)
    return importlib.reload(auth)


def test_empty_whitelist_denies_by_default(monkeypatch):
    reloaded_auth = _reload_auth(monkeypatch)

    assert reloaded_auth.is_allowed(42) is False


def test_allow_all_requires_explicit_escape_hatch(monkeypatch):
    reloaded_auth = _reload_auth(monkeypatch, TELEGRAM_ALLOW_ALL="true")

    assert reloaded_auth.is_allowed(42) is True


def test_whitelist_allows_only_listed_users(monkeypatch):
    reloaded_auth = _reload_auth(monkeypatch, TELEGRAM_ALLOWED_USERS="42")

    assert reloaded_auth.is_allowed(42) is True
    assert reloaded_auth.is_allowed(99) is False


def test_private_chat_is_required():
    assert auth.is_private_chat("private") is True
    assert auth.is_private_chat("group") is False
    assert auth.is_private_chat("supergroup") is False
    assert auth.is_private_chat("channel") is False
