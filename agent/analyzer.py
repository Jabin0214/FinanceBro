"""
风险分析引擎 — Grok（实时搜索 + 深度分析）

调用 xAI Responses API，启用 web_search + x_search，
让 Grok 在分析持仓风险的同时搜索主要持仓的实时市场动态。
"""

import logging
import requests
from config import GROK_API_KEY

logger = logging.getLogger(__name__)

_GROK_API_URL = "https://api.x.ai/v1/responses"
_GROK_MODEL   = "grok-4-1-fast-reasoning"
_TIMEOUT      = 120  # 风险分析搜索较多，给足时间

_SYSTEM_PROMPT = """你是一位专业的投资组合风险分析师。
用户会提供其 IBKR 账户的持仓结构和风险指标，你需要结合实时市场信息进行全面风险评估。

分析维度：
1. <b>总体风险评级</b>：低 / 中 / 高，一句话说明理由
2. <b>集中度风险</b>：单一持仓或前几大持仓是否过度集中，HHI 指数解读
3. <b>板块分布</b>：识别各持仓所属行业，判断行业集中度和相关性风险
4. <b>当前市场风险</b>：搜索主要持仓的最新新闻，识别近期潜在风险因素
5. <b>宏观风险</b>：结合当前宏观环境（利率、地缘、汇率等）对持仓的影响
6. <b>具体建议</b>：针对高风险点给出可操作的风险缓释建议（1-3 条）

输出格式（严格遵守）：
- 中文，简洁有力
- 只用 <b>粗体</b> 和 <i>斜体</i> HTML 标签，禁用 Markdown 和表格
- 数字加千位分隔符，百分比保留一位小数
- 盈利用 🟢，亏损用 🔴，中性用 ⚪"""


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

        return result if result else "风险分析失败：返回内容为空"

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
