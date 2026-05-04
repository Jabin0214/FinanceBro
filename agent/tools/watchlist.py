"""run_watchlist_scout tool — Watchlist Scout Specialist Agent."""

import logging

from agent.scout import analyze_watchlist
from agent.tools._state import current_user_id
from agent.tools.portfolio import get_cached_portfolio
from storage.watchlist_store import list_watchlist_items

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "run_watchlist_scout",
    "description": (
        "运行 Watchlist Scout Agent，分析用户观察列表中的标的，结合当前持仓、"
        "实时新闻和市场讨论，生成候选观察、近期催化和下一步研究重点。"
        "当用户询问观察列表、watchlist、候选股、机会侦察、哪些标的值得跟踪时调用。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def execute(_tool_input: dict) -> str:
    user_id = current_user_id()
    logger.info("run_watchlist_scout — user=%s", user_id)
    return analyze_watchlist(list_watchlist_items(user_id), get_cached_portfolio())
