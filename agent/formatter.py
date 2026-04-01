"""
用 Claude Sonnet 将 IBKR 结构化数据格式化为 Telegram HTML 报告。

Telegram HTML 支持的标签：
  <b>粗体</b>  <i>斜体</i>  <code>等宽</code>  <u>下划线</u>
  <s>删除线</s>  <pre>代码块</pre>

Telegram 单条消息上限 4096 字符，超出时需要分段发送。
"""

import logging
import anthropic
from config import ORCHESTRATOR_MODEL

logger = logging.getLogger(__name__)
client = anthropic.Anthropic()

MAX_MSG_LENGTH = 4000  # 留点余量

SYSTEM_PROMPT = """你是一个专业的投资组合报告生成助手。
你的任务是将 IBKR 账户数据转换为清晰易读的 Telegram 消息。

规则：
1. 只使用 Telegram 支持的 HTML 标签：<b> <i> <code> <u> <s>
2. 数字加千位分隔符，保留两位小数
3. 盈利前加 🟢，亏损前加 🔴，持平加 ⚪
4. 百分比变化：+X.XX% 或 -X.XX%
5. 报告结构：
   - 第一段：账户概览（净值、现金、总盈亏）
   - 第二段：持仓明细（按市值从大到小）
   - 最后一行：生成时间
6. 简洁，不要废话，数据要准确
7. 如果仓位很多（>10个），只列出前10个，说明还有N个未显示"""


def format_report(data: dict) -> list[str]:
    """
    将 IBKR 数据格式化为 Telegram HTML，返回消息列表（超长时自动分段）。
    """
    logger.info("正在用 Claude Sonnet 格式化报告...")

    response = client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"请格式化以下 IBKR 账户数据：\n\n{data}"
        }],
    )

    full_text = response.content[0].text
    return _split_message(full_text)


def _split_message(text: str) -> list[str]:
    """将超长消息按段落切分，每段不超过 MAX_MSG_LENGTH。"""
    if len(text) <= MAX_MSG_LENGTH:
        return [text]

    parts = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= MAX_MSG_LENGTH:
            current = current + ("\n\n" if current else "") + para
        else:
            if current:
                parts.append(current)
            current = para

    if current:
        parts.append(current)

    return parts
