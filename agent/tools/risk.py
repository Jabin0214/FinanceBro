"""get_risk_analysis tool — Risk Analyst Specialist Agent.

Pipeline: shared portfolio cache → risk_calculator (deterministic metrics)
→ analyzer (Grok + web_search + x_search) → narrative report.
"""

import logging

from agent.tools.portfolio import get_cached_portfolio

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "get_risk_analysis",
    "description": (
        "对整体持仓进行深度风险评估，包括集中度分析、板块分布、币种敞口、"
        "盈亏分布，并结合实时市场动态给出风险建议。"
        "当用户询问风险、仓位安全性、是否过度集中、投资组合健康度等问题时调用。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def execute(_tool_input: dict) -> str:
    from agent.analyzer import analyze_risk
    from agent.risk_calculator import compute_metrics

    logger.info("get_risk_analysis — computing metrics")
    metrics = compute_metrics(get_cached_portfolio())
    if "error" in metrics:
        return f"风险分析失败：{metrics['error']}"

    logger.info("get_risk_analysis — invoking Grok analyst")
    return analyze_risk(metrics)
