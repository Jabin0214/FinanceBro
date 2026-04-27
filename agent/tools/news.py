"""get_news tool — News Specialist Agent (Grok web_search + x_search)."""

import logging
import time

import requests

from config import GROK_API_KEY

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes
_cache: dict[str, tuple[str, float]] = {}

_GROK_API_URL = "https://api.x.ai/v1/responses"
_GROK_MODEL = "grok-4-1-fast-reasoning"
_TIMEOUT = 60

_SYSTEM_PROMPT = (
    "你是一个金融新闻助手。请搜索并汇总关于用户查询的最新新闻，"
    "重点关注：重大公告、财报、监管动态、市场情绪（来自 X/Twitter）。"
    "用中文输出，结构清晰，每条新闻注明时间（若可知）。"
)

DEFINITION = {
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
}


def execute(tool_input: dict) -> str:
    return _get_news(tool_input["query"])


def _get_news(query: str) -> str:
    if not GROK_API_KEY:
        return "错误：未配置 GROK_API_KEY，无法搜索新闻。"

    cache_key = query.strip().lower()
    now = time.time()
    if cache_key in _cache:
        result, ts = _cache[cache_key]
        if now - ts < CACHE_TTL:
            logger.info("get_news cache hit (%.0fs left)", CACHE_TTL - (now - ts))
            return result

    logger.info("get_news — query=%s", query)
    payload = {
        "model": _GROK_MODEL,
        "input": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"请搜索关于「{query}」的最新新闻和市场动态。"},
        ],
        "tools": [{"type": "web_search"}, {"type": "x_search"}],
    }

    resp = None
    try:
        resp = requests.post(
            _GROK_API_URL,
            headers={
                "Authorization": f"Bearer {GROK_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        result = _extract_text(resp.json())
        if not result:
            return "新闻获取失败：返回内容为空"
        _cache[cache_key] = (result, time.time())
        return result
    except requests.HTTPError as e:
        body = resp.text if resp is not None else ""
        logger.error("Grok API request failed: %s — %s", e, body)
        return f"新闻获取失败（HTTP {resp.status_code if resp else '?'}）：{body[:200]}"
    except Exception as e:
        logger.exception("get_news exception")
        return f"新闻获取失败：{e}"


def _extract_text(data: dict) -> str:
    """Pull the assistant message text out of a Grok Responses API payload."""
    for item in reversed(data.get("output", [])):
        if item.get("type") != "message":
            continue
        for block in item.get("content", []):
            if block.get("type") == "output_text":
                return block.get("text", "")
    return ""
