"""get_portfolio tool + shared portfolio cache.

The cache is exposed via `get_cached_portfolio()` so that `generate_report`
and `get_risk_analysis` can avoid re-fetching the same Flex Query within
the TTL window.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

CACHE_TTL = 600  # 10 minutes
_cache: dict | None = None
_cache_ts: float = 0.0

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
    global _cache, _cache_ts
    from ibkr.flex_query import fetch_flex_report

    now = time.time()
    if _cache and now - _cache_ts < CACHE_TTL:
        logger.info("portfolio cache hit (%.0fs left)", CACHE_TTL - (now - _cache_ts))
        return _cache

    logger.info("portfolio cache miss — fetching from IBKR")
    _cache = fetch_flex_report()
    _cache_ts = time.time()
    return _cache


def execute(_tool_input: dict) -> str:
    return json.dumps(get_cached_portfolio(), ensure_ascii=False)
