"""Portfolio Historian Specialist Agent.

This layer turns deterministic SQLite portfolio history summaries into a
Telegram-safe narrative recap. The data aggregation remains in Python; the
model only explains patterns and trade-offs.
"""

from __future__ import annotations

import json
import logging
import re

import anthropic

from config import ANTHROPIC_API_KEY, ORCHESTRATOR_MODEL

logger = logging.getLogger(__name__)

HISTORIAN_MODEL = ORCHESTRATOR_MODEL
_client: anthropic.Anthropic | None = None

_SYSTEM_PROMPT = """你是 FinanceBro 的 Portfolio Historian，用户的组合历史复盘分析师。

你只根据输入的结构化历史快照摘要做分析，不编造不存在的交易、价格或新闻。你的任务是解释过去一段时间组合发生了什么变化、这些变化说明了什么，以及用户下一步复盘时该关注什么。

请严格按以下五段输出，每段标题独占一行用 <b> 包裹：

<b>一句话结论</b>
用 1-2 句总结这段时间组合最重要的变化。

<b>资产变化</b>
说明净值、现金、浮盈亏或成本的主要变化，突出方向和幅度。

<b>持仓动作</b>
总结开仓、清仓、加仓、减仓，指出最值得复盘的动作。

<b>盈亏贡献</b>
说明主要浮盈浮亏贡献来自哪些标的，避免把市值变化误说成已实现收益。

<b>复盘建议</b>
给 2-3 条具体建议，聚焦仓位、现金、集中度、交易纪律或需要补记的买卖理由。

输出格式：
1. 中文，简洁直接。
2. 只允许使用 <b> 和 <i> 两种 HTML 标签。
3. 禁止 Markdown、表格、URL、引用标记。
4. 数字加千位分隔符，百分比保留一位小数。
5. 不提供买卖指令，只提供复盘观察和待确认问题。"""

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


def analyze_history(summary: dict) -> str:
    """Return a narrative portfolio history recap for Telegram."""
    if int(summary.get("snapshot_count") or 0) == 0:
        days = summary.get("period_days", 30)
        return f"暂无足够历史快照。先积累每日快照后，我就能复盘过去 {days} 天的组合变化。"

    if not ANTHROPIC_API_KEY:
        return "错误：未配置 ANTHROPIC_API_KEY，无法生成 Portfolio Historian 复盘。"

    response = _get_client().messages.create(
        model=HISTORIAN_MODEL,
        max_tokens=1600,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "请基于以下 JSON 历史摘要生成 Portfolio Historian 复盘：\n"
                    f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
                ),
            }
        ],
    )
    text = next((block.text for block in response.content if hasattr(block, "text")), "")
    if not text:
        return "历史复盘失败：模型返回内容为空。"
    return _sanitize_output(text)


def _sanitize_output(text: str) -> str:
    for pattern in _STRIP_PATTERNS:
        text = pattern.sub("", text)
    text = re.sub(r"<(?!/?(?:b|i)\b)[^>]+>", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        logger.info("initializing Portfolio Historian client")
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client
