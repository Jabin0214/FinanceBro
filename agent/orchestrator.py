"""
Orchestrator — Claude Sonnet 对话引擎

功能：
  - 维护多轮对话（历史由外部传入/传出，存储在 bot 层）
  - 滑动窗口裁剪（保留最近 MAX_HISTORY 条）
  - Tool use 循环（自动调用工具直到 end_turn）

用法：
    reply, updated_history, usage = chat(history, "我的持仓怎么样？")
"""

import logging
import anthropic
from config import ORCHESTRATOR_MODEL
from agent.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(__name__)
client = anthropic.Anthropic()

MAX_HISTORY = 20  # 滑动窗口大小（条数）

SYSTEM_PROMPT = """你是 FinanceBro，用户的私人投资助手。

你可以通过工具获取用户的 IBKR 账户实时持仓数据。
当用户询问持仓、盈亏、账户净值、某只股票是否持有等问题时，主动调用 get_portfolio 工具获取最新数据，不要凭记忆回答。

回复格式（严格遵守）：
- 使用中文回答
- 只允许使用这几个 HTML 标签：<b>粗体</b>、<i>斜体</i>、<code>等宽</code>
- 禁止使用 Markdown（不能用 **、__、`、# 等）
- 禁止使用表格（不能用 | 分隔符）
- 禁止使用任何其他 HTML 标签
- 数字加千位分隔符，保留两位小数
- 盈利用 🟢，亏损用 🔴，持平用 ⚪
- 回复简洁，不废话"""


# Sonnet 4.6 定价（美元 / token）
_PRICE_INPUT         = 3.0   / 1_000_000
_PRICE_CACHE_WRITE   = 3.75  / 1_000_000  # 写入缓存：比普通贵 25%
_PRICE_CACHE_READ    = 0.30  / 1_000_000  # 读取缓存：比普通便宜 90%
_PRICE_OUTPUT        = 15.0  / 1_000_000


def chat(history: list[dict], user_message: str) -> tuple[str, list[dict], dict]:
    """
    发送一条用户消息，返回 (Claude 回复文本, 更新后的对话历史, 用量统计)。

    用量统计格式：{"input_tokens": int, "output_tokens": int, "cost_usd": float}
    history 格式为 Anthropic messages 列表，由调用方维护和存储。
    """
    history = history + [{"role": "user", "content": user_message}]
    total_input = total_cache_write = total_cache_read = total_output = 0

    while True:
        trimmed = _trim(history)

        response = client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
            tools=TOOL_DEFINITIONS,
            messages=trimmed,
        )

        u = response.usage
        total_input       += u.input_tokens
        total_cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        total_cache_read  += getattr(u, "cache_read_input_tokens", 0) or 0
        total_output      += u.output_tokens

        if response.stop_reason == "end_turn":
            reply = next(
                (b.text for b in response.content if hasattr(b, "text")), ""
            )
            history = history + [{"role": "assistant", "content": reply}]
            return reply, _trim(history), _calc_usage(total_input, total_cache_write, total_cache_read, total_output)

        if response.stop_reason == "tool_use":
            assistant_blocks = [b.model_dump() for b in response.content]
            history = history + [{"role": "assistant", "content": assistant_blocks}]

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info(f"调用工具: {block.name} input={block.input}")
                    try:
                        result = execute_tool(block.name, block.input)
                    except Exception as e:
                        logger.exception(f"工具 {block.name} 执行失败")
                        result = f"工具执行失败: {e}"
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            history = history + [{"role": "user", "content": tool_results}]
            continue

        # 其他 stop_reason（max_tokens 等），尽力提取文本
        logger.warning(f"意外的 stop_reason: {response.stop_reason}")
        reply = "".join(b.text for b in response.content if hasattr(b, "text"))
        history = history + [{"role": "assistant", "content": reply or "(无回复)"}]
        return reply or "(无回复)", _trim(history), _calc_usage(total_input, total_cache_write, total_cache_read, total_output)


def _calc_usage(input_tokens: int, cache_write: int, cache_read: int, output_tokens: int) -> dict:
    cost = (
        input_tokens  * _PRICE_INPUT +
        cache_write   * _PRICE_CACHE_WRITE +
        cache_read    * _PRICE_CACHE_READ +
        output_tokens * _PRICE_OUTPUT
    )
    return {
        "input_tokens": input_tokens,
        "cache_write_tokens": cache_write,
        "cache_read_tokens": cache_read,
        "output_tokens": output_tokens,
        "cost_usd": cost,
    }


def _trim(history: list[dict]) -> list[dict]:
    """
    滑动窗口裁剪：保留最近 MAX_HISTORY 条，
    并确保裁剪后第一条是普通 user 文本消息（非 tool_result）。
    """
    if len(history) <= MAX_HISTORY:
        return history

    trimmed = history[-MAX_HISTORY:]

    # 找到第一条普通 user 消息（content 为字符串）作为起点
    for i, msg in enumerate(trimmed):
        if msg["role"] == "user" and isinstance(msg["content"], str):
            return trimmed[i:]

    return trimmed
