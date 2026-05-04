from storage.investor_profile_store import get_investor_profile, update_investor_profile


def test_investor_profile_defaults_and_updates_are_scoped_by_user(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCEBRO_DB_PATH", str(tmp_path / "financebro.db"))

    assert get_investor_profile(42) == {
        "risk_level": "balanced",
        "time_horizon": "medium",
        "max_position_weight_pct": 35.0,
        "cash_floor_pct": 5.0,
        "preferred_markets": "",
        "notes": "",
    }

    update_investor_profile(
        42,
        risk_level="conservative",
        max_position_weight_pct=25,
        cash_floor_pct=12.5,
        preferred_markets="US, HK",
        notes="Prefer simple explanations",
    )

    assert get_investor_profile(42) == {
        "risk_level": "conservative",
        "time_horizon": "medium",
        "max_position_weight_pct": 25.0,
        "cash_floor_pct": 12.5,
        "preferred_markets": "US, HK",
        "notes": "Prefer simple explanations",
    }
    assert get_investor_profile(7)["risk_level"] == "balanced"
