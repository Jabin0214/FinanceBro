"""get_portfolio tool + shared portfolio cache.

The cache is exposed via `get_cached_portfolio()` so that `generate_report`
and `get_risk_analysis` can avoid re-fetching the same Flex Query within
the TTL window.
"""

import json
import logging
import time

from agent.tools._state import current_user_id

logger = logging.getLogger(__name__)

CACHE_TTL = 600  # 10 minutes
_cache: dict[int, tuple[dict, float]] = {}

DEFINITION = {
    "name": "get_portfolio",
    "description": (
        "获取 IBKR 账户的最新实时持仓数据，包括账户净值、现金余额、"
        "各持仓的市值、成本、浮动盈亏等信息。"
        "用于回答用户关于持仓、盈亏、账户状况等问题，以文字形式分析和回复。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def get_cached_portfolio() -> dict:
    """Return portfolio data, hitting the IBKR API at most once per TTL window."""
    from ibkr.flex_query import fetch_flex_report

    user_id = current_user_id()
    now = time.time()
    if user_id in _cache:
        data, ts = _cache[user_id]
        if now - ts < CACHE_TTL:
            logger.info("portfolio cache hit for user %s (%.0fs left)", user_id, CACHE_TTL - (now - ts))
            return data

    logger.info("portfolio cache miss for user %s — fetching from IBKR", user_id)
    data = fetch_flex_report()
    _cache[user_id] = (data, time.time())
    return data


def execute(_tool_input: dict) -> str:
    return json.dumps(get_cached_portfolio(), ensure_ascii=False)
