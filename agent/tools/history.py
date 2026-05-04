"""get_portfolio_history tool — Portfolio Historian Specialist Agent."""

import logging

from agent.historian import analyze_history
from agent.tools._state import current_user_id
from storage.portfolio_store import get_portfolio_history_summary

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "get_portfolio_history",
    "description": (
        "读取已保存的历史持仓快照，分析过去 7、30 或 90 天组合变化。"
        "当用户询问历史表现、过去一段时间变化、周报、月报、复盘、"
        "加仓减仓、持仓漂移、现金变化或主要盈亏贡献时调用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "enum": [7, 30, 90],
                "description": "历史分析窗口，支持 7、30、90 天；省略时默认 30 天。",
            }
        },
        "required": [],
    },
}


def execute(tool_input: dict) -> str:
    days = tool_input.get("days", 30)
    if days not in {7, 30, 90}:
        days = 30

    user_id = current_user_id()
    logger.info("get_portfolio_history — user=%s days=%s", user_id, days)
    return analyze_history(get_portfolio_history_summary(user_id, days))
