from storage.watchlist_store import (
    add_watchlist_item,
    list_watchlist_items,
    remove_watchlist_item,
    update_watchlist_research,
)


def test_watchlist_items_are_scoped_by_user_and_upserted(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))

    add_watchlist_item(42, "aapl", "AI pullback")
    add_watchlist_item(42, "MSFT", "")
    add_watchlist_item(7, "TSLA", "other user")
    add_watchlist_item(42, "AAPL", "updated note")

    items = list_watchlist_items(42)

    assert items == [
        {
            "symbol": "AAPL",
            "note": "updated note",
            "status": "watching",
            "thesis": "",
            "trigger_price": None,
            "risk_note": "",
        },
        {
            "symbol": "MSFT",
            "note": "",
            "status": "watching",
            "thesis": "",
            "trigger_price": None,
            "risk_note": "",
        },
    ]


def test_remove_watchlist_item_returns_whether_row_existed(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    add_watchlist_item(42, "AAPL", "")

    assert remove_watchlist_item(42, "aapl") is True
    assert remove_watchlist_item(42, "aapl") is False
    assert list_watchlist_items(42) == []


def test_update_watchlist_research_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))
    add_watchlist_item(42, "AAPL", "pullback")

    update_watchlist_research(
        42,
        "aapl",
        status="waiting",
        thesis="AI device cycle",
        trigger_price=175.5,
        risk_note="China demand",
    )

    assert list_watchlist_items(42) == [
        {
            "symbol": "AAPL",
            "note": "pullback",
            "status": "waiting",
            "thesis": "AI device cycle",
            "trigger_price": 175.5,
            "risk_note": "China demand",
        }
    ]
