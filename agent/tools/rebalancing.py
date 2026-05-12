"""get_rebalancing_suggestion tool — compares portfolio to stored target allocations."""

from __future__ import annotations

import json
import logging

from agent.rebalancing import compute_rebalancing
from agent.risk_calculator import compute_metrics
from agent.tools._state import current_user_id
from agent.tools.portfolio import get_cached_portfolio
from storage.allocation_store import get_targets

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "get_rebalancing_suggestion",
    "description": (
        "根据用户通过 /settarget 设定的目标仓位比例，分析当前组合与目标的偏差并给出调仓建议。"
        "返回每个目标标的的超配/低配程度及建议买卖金额。"
        "当用户询问调仓、再平衡、仓位偏离、需要买入或卖出哪些标的时调用。"
        "若用户未设置目标仓位则返回提示。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def execute(_tool_input: dict) -> str:
    user_id = current_user_id()
    if user_id is None:
        return json.dumps({"error": "未知用户"}, ensure_ascii=False)

    targets = get_targets(user_id)
    if not targets:
        return json.dumps(
            {"error": "未设置目标仓位，请先发送 /settarget AAPL 30 MSFT 20 ..."},
            ensure_ascii=False,
        )

    portfolio = get_cached_portfolio()
    metrics = compute_metrics(portfolio)
    if "error" in metrics:
        return json.dumps(metrics, ensure_ascii=False)

    result = compute_rebalancing(
        current_weights=metrics["concentration"],
        targets=targets,
        total_portfolio_value=metrics["total_net_liquidation"],
    )
    logger.info(
        "rebalancing suggestion — user=%s max_drift=%s%%",
        user_id,
        result.get("max_drift_abs_pct"),
    )
    return json.dumps(result, ensure_ascii=False)
