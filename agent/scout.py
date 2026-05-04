"""Watchlist Scout Specialist Agent."""

from __future__ import annotations

import logging
import re

import requests

from config import GROK_API_KEY

logger = logging.getLogger(__name__)

_GROK_API_URL = "https://api.x.ai/v1/responses"
SCOUT_MODEL = "grok-4-1-fast-reasoning"
_TIMEOUT = 90

_SYSTEM_PROMPT = """你是 FinanceBro 的 Watchlist Scout，用户的观察列表机会侦察员。

你会基于用户的 watchlist、当前已持仓，以及实时新闻 / X 市场讨论，筛选哪些标的值得继续观察、哪些需要等待、哪些与现有持仓高度重叠。你不做买卖指令，只给观察重点和下一步确认问题。

请严格按以下四段输出，每段标题独占一行用 <b> 包裹：

<b>候选观察</b>
列出最值得关注的 2-4 个 watchlist 标的，并说明触发原因。

<b>与现有持仓关系</b>
说明这些候选与当前持仓是否主题重复、风险相关性高，或能补足组合缺口。

<b>近期催化</b>
结合搜索结果概括新闻、财报、产品、监管、宏观或市场情绪催化。

<b>下一步</b>
给 2-3 条具体观察动作，例如等财报、等回调、补充研究问题或设置提醒。

输出格式：
1. 中文，简洁直接。
2. 只允许使用 <b> 和 <i> 两种 HTML 标签。
3. 禁止 Markdown、表格、URL、引用标记。
4. 不承诺收益，不提供直接买卖指令。"""

_STRIP_PATTERNS = [
    re.compile(r"\[\[\s*\d+\s*\]\]\([^)]*\)"),
    re.compile(r"\[\[\s*\d+\s*\]\]"),
    re.compile(r"\[\s*\d+\s*\]"),
    re.compile(r"https?://\S+"),
    re.compile(r"\*\*"),
    re.compile(r"__"),
    re.compile(r"`"),
    re.compile(r"#+\s*"),
]


def analyze_watchlist(items: list[dict], portfolio: dict) -> str:
    if not items:
        return "观察列表为空。先发送 /watchlist add AAPL 这样的命令添加标的。"
    if not GROK_API_KEY:
        return "错误：未配置 GROK_API_KEY，无法运行 Watchlist Scout。"

    payload = {
        "model": SCOUT_MODEL,
        "input": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(items, portfolio)},
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
        text = _extract_text(resp.json())
        if not text:
            return "Watchlist Scout 失败：返回内容为空。"
        return _sanitize_output(text)
    except requests.HTTPError as e:
        body = resp.text if resp is not None else ""
        logger.error("Watchlist Scout request failed: %s — %s", e, body)
        return f"Watchlist Scout 失败（HTTP {resp.status_code if resp else '?'}）"
    except Exception as e:
        logger.exception("Watchlist Scout exception")
        return f"Watchlist Scout 失败：{e}"


def _build_prompt(items: list[dict], portfolio: dict) -> str:
    watchlist_lines = [
        _format_watchlist_prompt_line(item)
        for item in items
    ]
    holding_lines = [
        f"- {symbol}：${market_value:,.2f}"
        for symbol, market_value in _current_holdings(portfolio)
    ]
    if not holding_lines:
        holding_lines = ["- 当前未解析到持仓"]

    symbols = " ".join(item["symbol"] for item in items)
    return (
        "请搜索并分析以下观察列表标的，结合当前已持仓判断哪些更值得继续跟踪。\n\n"
        "【观察列表】\n"
        + "\n".join(watchlist_lines)
        + "\n\n【当前已持仓】\n"
        + "\n".join(holding_lines)
        + "\n\n【搜索关键词】\n"
        + f"{symbols} earnings product news market sentiment valuation"
    )


def _format_watchlist_prompt_line(item: dict) -> str:
    parts = [f"- {item['symbol']}"]
    if item.get("status"):
        parts.append(f"状态={item['status']}")
    if item.get("note"):
        parts.append(f"备注={item['note']}")
    if item.get("thesis"):
        parts.append(f"关注逻辑={item['thesis']}")
    if item.get("trigger_price") is not None:
        parts.append(f"触发价={item['trigger_price']}")
    if item.get("risk_note"):
        parts.append(f"风险点={item['risk_note']}")
    return "；".join(parts)


def _current_holdings(portfolio: dict) -> list[tuple[str, float]]:
    totals: dict[str, float] = {}
    for account in portfolio.get("accounts", []):
        for pos in account.get("positions", []):
            symbol = (pos.get("symbol") or "").upper()
            if not symbol:
                continue
            totals[symbol] = totals.get(symbol, 0.0) + float(pos.get("market_value_base") or 0)
    return sorted(totals.items(), key=lambda item: abs(item[1]), reverse=True)[:10]


def _extract_text(data: dict) -> str:
    for item in reversed(data.get("output", [])):
        if item.get("type") != "message":
            continue
        for block in item.get("content", []):
            if block.get("type") == "output_text":
                return block.get("text", "")
    return ""


def _sanitize_output(text: str) -> str:
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"<(?!/?(?:b|i)\b)[^>]+>", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
