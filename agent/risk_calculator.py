"""
风险指标计算 — 纯 Python，基于 IBKR 持仓数据

不调用任何外部 API，直接从 parse_flex_xml() 返回的结构计算：
  - 集中度 + HHI
  - 币种敞口
  - 资产类别分布
  - 盈亏分布
"""


def compute_metrics(portfolio_data: dict) -> dict:
    """
    从 IBKR 持仓数据计算风险指标。

    返回结构：
    {
        "total_net_liquidation": float,
        "positions_count": int,
        "concentration": [{"symbol", "weight_pct", "market_value_base", "unrealized_pnl_pct"}, ...],
        "top5_concentration_pct": float,
        "hhi": float,               # 0–10000，越高越集中
        "currency_exposure": {ccy: pct, ...},
        "asset_class": {cat: pct, ...},
        "pnl_summary": {
            "profitable_count": int,
            "loss_count": int,
            "total_unrealized_pnl": float,
            "total_pnl_pct": float,
            "biggest_gainer": {"symbol": str, "unrealized_pnl_pct": float} | None,
            "biggest_loser":  {"symbol": str, "unrealized_pnl_pct": float} | None,
        },
    }
    """
    accounts = portfolio_data.get("accounts", [])

    all_positions: list[dict] = []
    total_net_liquidation = 0.0

    for account in accounts:
        summary = account.get("summary", {})
        net_liq = float(summary.get("net_liquidation", 0) or 0)
        total_net_liquidation += net_liq

        for pos in account.get("positions", []):
            mv = float(pos.get("market_value_base", 0) or 0)
            if mv <= 0:
                continue
            all_positions.append({
                "symbol":            pos.get("symbol", ""),
                "description":       pos.get("description", ""),
                "asset_category":    pos.get("asset_category", "STK"),
                "currency":          pos.get("currency", "USD"),
                "market_value_base": mv,
                "unrealized_pnl_base": float(pos.get("unrealized_pnl_base", 0) or 0),
                "unrealized_pnl_pct":  float(pos.get("unrealized_pnl_pct", 0) or 0),
                "cost_basis_base":     float(pos.get("cost_basis_base", 0) or 0),
            })

    if not all_positions or total_net_liquidation <= 0:
        return {"error": "无有效持仓数据"}

    # 按市值降序
    all_positions.sort(key=lambda x: x["market_value_base"], reverse=True)

    # 权重：用多头总市值做分母（而非 net_liquidation），确保权重之和 = 100%，HHI ∈ [0, 10000]
    total_long_value = sum(p["market_value_base"] for p in all_positions)
    for pos in all_positions:
        pos["weight_pct"] = round(pos["market_value_base"] / total_long_value * 100, 2)

    # 集中度指标
    top5_weight = round(sum(p["weight_pct"] for p in all_positions[:5]), 2)
    hhi = round(sum(p["weight_pct"] ** 2 for p in all_positions), 1)

    # 币种敞口
    currency_exposure: dict[str, float] = {}
    for pos in all_positions:
        ccy = pos["currency"]
        currency_exposure[ccy] = currency_exposure.get(ccy, 0.0) + pos["weight_pct"]
    currency_exposure = {
        k: round(v, 2)
        for k, v in sorted(currency_exposure.items(), key=lambda x: -x[1])
    }

    # 资产类别分布
    asset_class: dict[str, float] = {}
    for pos in all_positions:
        cat = pos["asset_category"]
        asset_class[cat] = asset_class.get(cat, 0.0) + pos["weight_pct"]
    asset_class = {
        k: round(v, 2)
        for k, v in sorted(asset_class.items(), key=lambda x: -x[1])
    }

    # 盈亏分布
    profitable  = [p for p in all_positions if p["unrealized_pnl_base"] > 0]
    loss_pos    = [p for p in all_positions if p["unrealized_pnl_base"] < 0]
    total_pnl   = sum(p["unrealized_pnl_base"] for p in all_positions)
    total_cost  = sum(p["cost_basis_base"] for p in all_positions)  # 统一用基础货币，多币种正确
    total_pnl_pct = round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0.0

    biggest_gainer = max(all_positions, key=lambda x: x["unrealized_pnl_pct"], default=None)
    biggest_loser  = min(all_positions, key=lambda x: x["unrealized_pnl_pct"], default=None)

    return {
        "total_net_liquidation": round(total_net_liquidation, 2),
        "positions_count": len(all_positions),
        "concentration": [
            {
                "symbol":            p["symbol"],
                "weight_pct":        p["weight_pct"],
                "market_value_base": round(p["market_value_base"], 2),
                "unrealized_pnl_pct": round(p["unrealized_pnl_pct"], 2),
            }
            for p in all_positions
        ],
        "top5_concentration_pct": top5_weight,
        "hhi": hhi,
        "currency_exposure": currency_exposure,
        "asset_class": asset_class,
        "pnl_summary": {
            "profitable_count":    len(profitable),
            "loss_count":          len(loss_pos),
            "total_unrealized_pnl": round(total_pnl, 2),
            "total_pnl_pct":       total_pnl_pct,
            "biggest_gainer": {
                "symbol":             biggest_gainer["symbol"],
                "unrealized_pnl_pct": round(biggest_gainer["unrealized_pnl_pct"], 2),
            } if biggest_gainer else None,
            "biggest_loser": {
                "symbol":             biggest_loser["symbol"],
                "unrealized_pnl_pct": round(biggest_loser["unrealized_pnl_pct"], 2),
            } if biggest_loser else None,
        },
    }
