from agent.tools import portfolio
from agent.tools._state import reset_active_user, set_active_user


def test_portfolio_cache_is_scoped_per_user(monkeypatch):
    calls = []

    def fake_fetch():
        calls.append(len(calls) + 1)
        return {"report_date": "2026-04-28", "accounts": [{"account_id": f"U{calls[-1]}"}]}

    monkeypatch.setattr(portfolio, "_cache", {})
    monkeypatch.setattr("ibkr.flex_query.fetch_flex_report", fake_fetch)

    token = set_active_user(1)
    try:
        first = portfolio.get_cached_portfolio()
        again = portfolio.get_cached_portfolio()
    finally:
        reset_active_user(token)

    token = set_active_user(2)
    try:
        second_user = portfolio.get_cached_portfolio()
    finally:
        reset_active_user(token)

    assert first is again
    assert first != second_user
    assert len(calls) == 2
