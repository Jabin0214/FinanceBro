"""Rebalancing engine — pure Python, no external deps.

Compares current portfolio weights against user-defined target allocations
and computes position drift + suggested trade direction/size.
"""

from __future__ import annotations


def compute_rebalancing(
    current_weights: list[dict],
    targets: dict[str, float],
    total_portfolio_value: float,
) -> dict:
    """
    Args:
        current_weights: list of {"symbol": str, "weight_pct": float, "market_value_base": float}
                         (the "concentration" list from risk_calculator.compute_metrics)
        targets: {SYMBOL: target_pct} — sum should be <= 100
        total_portfolio_value: total net liquidation in base currency

    Returns:
        {
            "drift": [
                {
                    "symbol": str,
                    "target_pct": float,
                    "current_pct": float,
                    "drift_pct": float,          # current - target; positive = overweight
                    "suggested_trade_base": float,  # negative = sell, positive = buy
                },
                ...                              # sorted by abs(drift_pct) desc
            ],
            "total_target_pct": float,
            "unallocated_pct": float,            # 100 - total_target_pct
            "max_drift_symbol": str | None,
            "max_drift_abs_pct": float,
        }
        or {"error": str} on invalid input.
    """
    if not targets:
        return {"error": "no targets defined"}
    if total_portfolio_value <= 0:
        return {"error": "invalid portfolio value"}

    # Build lookup: SYMBOL → current weight_pct
    current_by_symbol: dict[str, float] = {
        pos["symbol"].upper(): float(pos["weight_pct"])
        for pos in current_weights
    }

    total_target = sum(targets.values())
    drift_rows: list[dict] = []

    for symbol, target_pct in sorted(targets.items()):
        sym_upper = symbol.upper()
        current_pct = current_by_symbol.get(sym_upper, 0.0)
        drift = round(current_pct - target_pct, 2)
        # A positive drift means overweight → suggested trade is negative (sell)
        trade_value = round(-drift / 100.0 * total_portfolio_value, 2)
        drift_rows.append({
            "symbol": sym_upper,
            "target_pct": round(float(target_pct), 2),
            "current_pct": round(current_pct, 2),
            "drift_pct": drift,
            "suggested_trade_base": trade_value,
        })

    drift_rows.sort(key=lambda r: abs(r["drift_pct"]), reverse=True)

    max_row = drift_rows[0] if drift_rows else None
    return {
        "drift": drift_rows,
        "total_target_pct": round(float(total_target), 2),
        "unallocated_pct": round(100.0 - float(total_target), 2),
        "max_drift_symbol": max_row["symbol"] if max_row else None,
        "max_drift_abs_pct": abs(max_row["drift_pct"]) if max_row else 0.0,
    }
