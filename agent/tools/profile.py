"""get_investor_profile tool — user investing rules and preferences."""

import json

from agent.tools._state import current_user_id
from storage.investor_profile_store import get_investor_profile

DEFINITION = {
    "name": "get_investor_profile",
    "description": (
        "读取用户的投资画像，包括风险偏好、投资期限、单一持仓上限、"
        "现金底线、偏好市场和个人备注。"
        "当用户询问建议、是否该行动、仓位纪律、组合是否适合自己时调用。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def execute(_tool_input: dict) -> str:
    return json.dumps(get_investor_profile(current_user_id()), ensure_ascii=False)
