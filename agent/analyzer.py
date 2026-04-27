"""
风险分析引擎 — Grok（实时搜索 + 深度分析）

调用 xAI Responses API，启用 web_search + x_search，
让 Grok 在分析持仓风险的同时搜索主要持仓的实时市场动态。
"""

import logging
import re

import requests

from config import GROK_API_KEY

logger = logging.getLogger(__name__)

_GROK_API_URL = "https://api.x.ai/v1/responses"
_GROK_MODEL   = "grok-4-1-fast-reasoning"
_TIMEOUT      = 120  # 风险分析搜索较多，给足时间

_SYSTEM_PROMPT = """你是用户的私人理财顾问。用户是有一定基础但不是专业人士的散户投资者。
基于用户的 IBKR 持仓和实时市场信息给出风险评估，要像在和朋友面对面解释一样：先讲结论，再讲数据，专业名词第一次出现时用一句大白话解释。

请严格按以下七段输出，每段标题独占一行用 <b> 包裹，段落之间空一行：

<b>一句话结论</b>
风险等级（低 / 中 / 高）+ 当前最值得关注的一件事，不超过两句。

<b>关键数字</b>
3-5 行，每行一个核心指标，格式："指标名：数值，一句通俗解读"。
例如："HHI 集中度：2,292（HHI 衡量分散度，1 万 = 全押一只股，3,000 以上算高度集中）"。

<b>集中度风险</b>
最大持仓和前五大占比说明了什么，是否需要调整。2-4 行。

<b>行业与主题</b>
钱主要压在哪些方向（科技 / 金融 / 现金替代等），相关性是否高。2-4 行。

<b>个股近况</b>
针对前几大持仓搜索近期事件，标注影响方向。每条 1 行，最多 4 条。

<b>宏观环境</b>
挑出对当前组合影响最大的 2-3 个宏观因素（利率 / 地缘 / 汇率等），不要泛泛而谈。

<b>下一步动作</b>
按优先级排：P1（本周内做）、P2（本月考虑）、P3（持续观察）。最多 3 条，每条具体到"减 / 加 / 盯什么、为什么"。

输出格式（严格遵守，违反任何一条都属于错误输出）：
1. 中文，简洁直接，不堆砌专业词。
2. 只允许使用这两个 HTML 标签：<b>粗体</b>、<i>斜体</i>。其它 HTML 一律禁止。
3. 严禁任何形式的引用标记：[1]、[[1]]、[[1]](https://...)、(source: ...)、<grok:render>、citation_id 等任何 XML / 方括号 / 内联链接形式。引用一律不要出现。
4. 严禁 Markdown 语法：**、__、`、#、---、表格的 | 分隔符 等。
5. 严禁出现任何 URL，无论是否包在标记里。
6. emoji 只能用三种：🟢 健康 / 低风险，🔴 警示 / 高风险，⚪ 中性 / 观察。禁止使用 🟡 或其它彩色圆。
7. 数字加千位分隔符（如 1,234,567），百分比保留一位小数（如 35.6%）。
8. 段落之间一定要空一行。每段 2-4 行可读，不要一段写成一坨。"""


# Defense-in-depth: Grok web_search/x_search often inserts citations even when
# told not to. Strip them post-hoc so Telegram HTML parse never breaks and the
# user never sees raw [[N]](url) / <grok:render> tags.
_CITATION_PATTERNS = [
    re.compile(r"<\s*g?\s*rok\s*:\s*render\b[^>]*>.*?<\s*/\s*g?\s*rok\s*:\s*render\s*>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\s*g?\s*rok\s*:\s*render\b[^>]*/?>", re.IGNORECASE),
    re.compile(r"<argument\s+name=\"citation_id\">\s*\d+\s*</argument>", re.IGNORECASE),
    re.compile(r"\[\[\s*\d+\s*\]\]\([^)]*\)"),  # [[1]](url)
    re.compile(r"\[\[\s*\d+\s*\]\]"),            # [[1]]
    re.compile(r"\[\s*\d+\s*\]"),                 # [1]
    re.compile(r"https?://\S+"),                  # any leftover URL
]


def _sanitize_output(text: str) -> str:
    for pat in _CITATION_PATTERNS:
        text = pat.sub("", text)
    # 🟡 isn't allowed by the prompt; downgrade to ⚪ rather than drop entirely.
    text = text.replace("🟡", "⚪")
    # Collapse blank space introduced by removals.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def analyze_risk(metrics: dict) -> str:
    """
    调用 Grok 对持仓进行风险分析。

    metrics: risk_calculator.compute_metrics() 的完整输出
    返回: Grok 生成的风险分析报告（HTML 格式文本）
    """
    if not GROK_API_KEY:
        return "错误：未配置 GROK_API_KEY，无法进行风险分析。"

    user_content = _build_prompt(metrics)

    payload = {
        "model": _GROK_MODEL,
        "input": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        "tools": [
            {"type": "web_search"},
            {"type": "x_search"},
        ],
    }

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
        data = resp.json()

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
            return "风险分析失败：返回内容为空"
        return _sanitize_output(result)

    except requests.HTTPError as e:
        logger.error("Grok 风险分析请求失败: %s — %s", e, resp.text)
        return f"风险分析失败（HTTP {resp.status_code}）"
    except Exception as e:
        logger.exception("风险分析执行异常")
        return f"风险分析失败：{e}"


def _build_prompt(metrics: dict) -> str:
    """将结构化风险指标格式化为 Grok 的 user message。"""
    pnl = metrics["pnl_summary"]
    pnl_sign = "+" if pnl["total_pnl_pct"] >= 0 else ""

    # 持仓列表：最多取前 15 个，避免 context 过长
    positions_lines = []
    for p in metrics["concentration"][:15]:
        sign = "+" if p["unrealized_pnl_pct"] >= 0 else ""
        positions_lines.append(
            f"  {p['symbol']}: 占比 {p['weight_pct']}%，"
            f"浮{sign}{p['unrealized_pnl_pct']}%"
        )

    gainer = pnl.get("biggest_gainer")
    loser  = pnl.get("biggest_loser")

    lines = [
        "请对以下投资组合进行全面风险评估，并搜索主要持仓的最新市场动态：",
        "",
        "【持仓概况】",
        f"总净值：${metrics['total_net_liquidation']:,.2f}",
        f"持仓数量：{metrics['positions_count']} 个",
        f"HHI 集中度指数：{metrics['hhi']:.0f}（0=极分散，10000=单一持仓）",
        f"前 5 大持仓合计：{metrics['top5_concentration_pct']}%",
        "",
        "【币种敞口】",
        *[f"  {k}: {v}%" for k, v in metrics["currency_exposure"].items()],
        "",
        "【资产类别】",
        *[f"  {k}: {v}%" for k, v in metrics["asset_class"].items()],
        "",
        "【盈亏状态】",
        f"盈利持仓：{pnl['profitable_count']} 个 | 亏损持仓：{pnl['loss_count']} 个",
        f"整体浮动：{pnl_sign}{pnl['total_pnl_pct']}%",
    ]

    if gainer:
        g_pct = gainer['unrealized_pnl_pct']
        lines.append(f"最大赢家：{gainer['symbol']} ({'+' if g_pct >= 0 else ''}{g_pct}%)")
    if loser:
        l_pct = loser['unrealized_pnl_pct']
        lines.append(f"最大输家：{loser['symbol']} ({'+' if l_pct >= 0 else ''}{l_pct}%)")

    lines += [
        "",
        "【主要持仓（按市值排序）】",
        *positions_lines,
    ]

    return "\n".join(lines)
