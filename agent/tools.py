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
from contextvars import ContextVar
from uuid import uuid4

logger = logging.getLogger(__name__)

# 持仓数据本地缓存
_portfolio_cache: dict | None = None
_portfolio_cache_ts: float = 0.0
_PORTFOLIO_CACHE_TTL = 600  # 10 分钟

# 新闻缓存（query → (结果, 时间戳)）
_news_cache: dict[str, tuple[str, float]] = {}
_NEWS_CACHE_TTL = 300  # 5 分钟

# 待发送文件队列（按 user_id 隔离，由 bot 层在每次 chat() 后消费）
_pending_files: dict[int, list[dict]] = {}
_active_user_id: ContextVar[int | None] = ContextVar("active_user_id", default=None)

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
    {
        "name": "get_news",
        "description": (
            "搜索最新财经新闻和 X（Twitter）上的实时市场讨论。"
            "适用场景：某只股票/公司的最新动态、大盘行情、宏观经济事件、行业趋势、"
            "今日市场概况等。只要用户问到任何与新闻、市场动态、最新消息相关的问题都应调用。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，可以是股票代码、公司名、宏观主题（如 'Fed interest rate'、'AI stocks today'、'今日美股'）等",
                },
            },
            "required": ["query"],
        },
    },
    # Phase 4: get_risk_analysis
]


# ── 工具执行器 ────────────────────────────────────────────────────────────────

def execute_tool(name: str, tool_input: dict) -> str:
    if name == "get_portfolio":
        return _get_portfolio()
    if name == "generate_report":
        return _generate_report()
    if name == "get_news":
        return _get_news(tool_input["query"])
    raise ValueError(f"未知工具: {name}")


def set_active_user(user_id: int) -> object:
    """设置当前工具调用所属用户，返回可用于 reset 的 token。"""
    return _active_user_id.set(user_id)


def reset_active_user(token: object) -> None:
    _active_user_id.reset(token)


def pop_pending_files(user_id: int) -> list[dict]:
    """取出并清空指定用户的待发送文件队列，由 bot 层调用。"""
    return _pending_files.pop(user_id, [])


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

    user_id = _active_user_id.get()
    if user_id is None:
        raise RuntimeError("未设置当前用户，无法安全生成报表")

    report_date = data.get("report_date", "report").replace("-", "")
    unique_suffix = uuid4().hex[:8]
    tmp_path = os.path.join(
        tempfile.gettempdir(),
        f"ibkr_report_{report_date}_{user_id}_{unique_suffix}.html",
    )
    build_html_file(data, tmp_path)

    _pending_files.setdefault(user_id, []).append({
        "path": tmp_path,
        "filename": f"ibkr_report_{report_date}.html",
        "caption": f"📊 IBKR 持仓报告 {data.get('report_date', '')}",
    })

    return "报表已生成，正在发送给你。"


def _get_news(query: str) -> str:
    import requests
    from config import GROK_API_KEY

    logger.info("工具调用: get_news — query=%s", query)

    if not GROK_API_KEY:
        return "错误：未配置 GROK_API_KEY，无法搜索新闻。"

    # 缓存命中
    now = time.time()
    cache_key = query.strip().lower()
    if cache_key in _news_cache:
        cached_result, cached_ts = _news_cache[cache_key]
        if now - cached_ts < _NEWS_CACHE_TTL:
            logger.info("get_news — 缓存命中（剩余 %.0fs）", _NEWS_CACHE_TTL - (now - cached_ts))
            return cached_result

    payload = {
        "model": "grok-4-1-fast-reasoning",
        "input": [
            {
                "role": "system",
                "content": (
                    "你是一个金融新闻助手。请搜索并汇总关于用户查询的最新新闻，"
                    "重点关注：重大公告、财报、监管动态、市场情绪（来自 X/Twitter）。"
                    "用中文输出，结构清晰，每条新闻注明时间（若可知）。"
                ),
            },
            {
                "role": "user",
                "content": f"请搜索关于「{query}」的最新新闻和市场动态。",
            },
        ],
        "tools": [
            {"type": "web_search"},
            {"type": "x_search"},
        ],
    }

    try:
        resp = requests.post(
            "https://api.x.ai/v1/responses",
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        # Responses API 返回格式：output 数组，取最后一条 message 的文本
        result = ""
        for item in reversed(data.get("output", [])):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        result = block.get("text", "")
                        break
            if result:
                break

        if not result:
            return "新闻获取失败：返回内容为空"

        _news_cache[cache_key] = (result, time.time())
        return result
    except requests.HTTPError as e:
        logger.error("Grok API 请求失败: %s — %s", e, resp.text)
        return f"新闻获取失败（HTTP {resp.status_code}）：{resp.text[:200]}"
    except Exception as e:
        logger.exception("get_news 执行异常")
        return f"新闻获取失败：{e}"
