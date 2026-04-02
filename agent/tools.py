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
import tempfile
import os
import time

logger = logging.getLogger(__name__)

# 持仓数据本地缓存
_portfolio_cache: dict | None = None
_portfolio_cache_ts: float = 0.0
_PORTFOLIO_CACHE_TTL = 600  # 10 分钟

# 待发送文件队列（由 bot 层在每次 chat() 后消费）
_pending_files: list[dict] = []

# ── 工具 Schema（发给 Claude） ─────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "get_portfolio",
        "description": (
            "获取 IBKR 账户的最新实时持仓数据，包括账户净值、现金余额、"
            "各持仓的市值、成本、浮动盈亏等信息。"
            "用于回答用户关于持仓、盈亏、账户状况等问题，以文字形式分析和回复。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "generate_report",
        "description": (
            "生成完整的 IBKR 持仓 HTML 报表文件并发送给用户。"
            "当用户明确要求报表、报告文件、完整持仓表格时调用。"
            "与 get_portfolio 的区别：此工具发送可下载的 HTML 文件，而不是文字回复。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # Phase 3: get_news
    # Phase 4: get_risk_analysis
]


# ── 工具执行器 ────────────────────────────────────────────────────────────────

def execute_tool(name: str, tool_input: dict) -> str:
    if name == "get_portfolio":
        return _get_portfolio()
    if name == "generate_report":
        return _generate_report()
    raise ValueError(f"未知工具: {name}")


def pop_pending_files() -> list[dict]:
    """取出并清空待发送文件队列，由 bot 层调用。"""
    global _pending_files
    files, _pending_files = _pending_files, []
    return files


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


def _generate_report() -> str:
    from ibkr.flex_query import fetch_flex_report
    from report.html_report import build_html_file

    logger.info("工具调用: generate_report — 正在生成 HTML 报表...")

    # 优先用缓存，避免重复拉 IBKR
    global _portfolio_cache, _portfolio_cache_ts
    now = time.time()
    if _portfolio_cache and now - _portfolio_cache_ts < _PORTFOLIO_CACHE_TTL:
        data = _portfolio_cache
    else:
        data = fetch_flex_report()
        _portfolio_cache = data
        _portfolio_cache_ts = time.time()

    report_date = data.get("report_date", "report").replace("-", "")
    tmp_path = os.path.join(tempfile.gettempdir(), f"ibkr_report_{report_date}.html")
    build_html_file(data, tmp_path)

    _pending_files.append({
        "path": tmp_path,
        "filename": f"ibkr_report_{report_date}.html",
        "caption": f"📊 IBKR 持仓报告 {data.get('report_date', '')}",
    })

    return "报表已生成，正在发送给你。"
