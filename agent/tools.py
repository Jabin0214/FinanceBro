"""
工具注册表 — Claude tool use

每个工具包含两部分：
  1. TOOL_DEFINITIONS 里的 schema（告诉 Claude 工具的用途和参数）
  2. execute_tool() 里的执行逻辑（实际调用 Python 函数）

新增工具时只需：
  - 在 TOOL_DEFINITIONS 追加一条 schema
  - 在 execute_tool() 追加对应的 elif 分支
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

# 持仓数据本地缓存
_portfolio_cache: dict | None = None
_portfolio_cache_ts: float = 0.0
_PORTFOLIO_CACHE_TTL = 600  # 10 分钟

# ── 工具 Schema（发给 Claude） ─────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_portfolio",
        "description": (
            "获取 IBKR 账户的最新持仓数据，包括账户净值、现金余额、"
            "各持仓的市值、成本、浮动盈亏等信息。"
            "当用户询问持仓、账户状况、盈亏情况、某只股票是否持有等问题时调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # Phase 2: get_news
    # Phase 3: get_risk_analysis
]


# ── 工具执行器 ────────────────────────────────────────────────────────────────

def execute_tool(name: str, tool_input: dict) -> str:
    """
    根据工具名称执行对应函数，返回字符串结果（传回给 Claude）。
    """
    if name == "get_portfolio":
        return _get_portfolio()

    raise ValueError(f"未知工具: {name}")


def _get_portfolio() -> str:
    global _portfolio_cache, _portfolio_cache_ts
    from ibkr.flex_query import fetch_flex_report

    now = time.time()
    if _portfolio_cache and now - _portfolio_cache_ts < _PORTFOLIO_CACHE_TTL:
        logger.info("工具调用: get_portfolio — 使用缓存数据（剩余 %.0fs）", _PORTFOLIO_CACHE_TTL - (now - _portfolio_cache_ts))
        return json.dumps(_portfolio_cache, ensure_ascii=False)

    logger.info("工具调用: get_portfolio — 正在从 IBKR 获取数据...")
    data = fetch_flex_report()
    _portfolio_cache = data
    _portfolio_cache_ts = time.time()
    return json.dumps(data, ensure_ascii=False)
