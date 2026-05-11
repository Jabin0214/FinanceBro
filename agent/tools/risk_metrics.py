"""Orchestrator tool: historical risk metrics from snapshot series."""

from __future__ import annotations

from agent.risk_metrics import compute_history_metrics
from agent.tools._state import current_user_id
from storage.portfolio_store import get_net_liquidation_series

DEFINITION = {
    "name": "get_risk_metrics",
    "description": (
        "Compute historical risk metrics (annualized volatility, max drawdown, "
        "VaR 95%, CVaR 95%, Sharpe, Sortino) from the user's portfolio_snapshots "
        "history. Use when the user asks about portfolio risk over a window."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Lookback window in calendar days (max 365). Default 90.",
                "minimum": 7,
                "maximum": 365,
            },
        },
    },
}


def execute(tool_input: dict) -> str:
    user_id = current_user_id()
    if user_id is None:
        return "❌ 无法识别当前 Telegram 用户，无法读取历史快照。"

    days = int(tool_input.get("days") or 90)
    days = max(7, min(days, 365))

    series = get_net_liquidation_series(user_id, days=days)
    metrics = compute_history_metrics(series)

    if "error" in metrics:
        return f"⚠️ 历史风险指标无法计算：{metrics['error']}（窗口 {days} 天）"

    dd = metrics["max_drawdown"]
    return (
        f"📊 历史风险指标（{metrics['start_date']} → {metrics['end_date']}，"
        f"{metrics['window_days']} 个交易日样本）\n\n"
        f"• 累计收益：{metrics['total_return_pct']:.2f}%\n"
        f"• 年化波动率：{metrics['annualized_volatility'] * 100:.2f}%\n"
        f"• 最大回撤：{dd['max_drawdown_pct']:.2f}% "
        f"（{dd['peak_date']} → {dd['trough_date']}）\n"
        f"• 历史 VaR 95%：{metrics['var_95'] * 100:.2f}%\n"
        f"• 历史 CVaR 95%：{metrics['cvar_95'] * 100:.2f}%\n"
        f"• Sharpe：{metrics['sharpe']:.2f}\n"
        f"• Sortino：{metrics['sortino']:.2f}"
    )
