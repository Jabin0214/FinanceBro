from agent.tools import TOOL_DEFINITIONS, execute_tool
from agent.tools._state import reset_active_user, set_active_user


def test_profile_tool_uses_active_user(monkeypatch):
    import agent.tools.profile as profile_tool

    monkeypatch.setattr(
        profile_tool,
        "get_investor_profile",
        lambda user_id: {
            "risk_level": "balanced",
            "time_horizon": "medium",
            "max_position_weight_pct": 35.0,
            "cash_floor_pct": 5.0,
            "preferred_markets": "US",
            "notes": "explain plainly",
        },
    )

    token = set_active_user(42)
    try:
        result = execute_tool("get_investor_profile", {})
    finally:
        reset_active_user(token)

    assert '"risk_level": "balanced"' in result
    assert '"preferred_markets": "US"' in result


def test_profile_tool_is_registered():
    names = {definition["name"] for definition in TOOL_DEFINITIONS}

    assert "get_investor_profile" in names
