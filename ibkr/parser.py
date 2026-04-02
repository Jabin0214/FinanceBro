"""
IBKR Flex Query XML → 结构化 JSON

返回格式：
{
  "generated_at": "2026-04-01 03:23:16",
  "report_date": "2026-03-31",
  "accounts": [
    {
      "account_id": "U20420291",
      "alias": "Growth",
      "base_currency": "HKD",
      "summary": {
        "net_liquidation": 495414.07,   # 净值（基础货币）
        "stock_value_base": 494732.57,
        "cash_base": 681.51,
        "total_unrealized_pnl_base": -16241.73,
        "total_cost_base": 511655.80,
        "total_unrealized_pnl_pct": -3.17
      },
      "positions": [
        {
          "symbol": "700",
          "description": "TENCENT HOLDINGS LTD",
          "currency": "HKD",
          "asset_category": "STK",
          "quantity": 200,
          "cost_price": 563.82,
          "mark_price": 484.0,
          "market_value": 96800.0,       # 本币
          "market_value_base": 96800.0,  # 折算基础货币
          "cost_basis": 112764.85,       # 本币
          "cost_basis_base": 112764.85,  # 折算基础货币
          "unrealized_pnl": -15964.85,   # 本币
          "unrealized_pnl_base": -15964.85,
          "unrealized_pnl_pct": -14.16,
          "fx_rate": 1.0
        }
      ],
      "cash_balances": [
        {"currency": "HKD", "ending_cash": 327.23, "ending_cash_base": 327.23},
        {"currency": "USD", "ending_cash": 45.19,  "ending_cash_base": 354.28}
      ]
    }
  ]
}
"""

import xml.etree.ElementTree as ET
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_flex_xml(xml_str: str) -> dict:
    """将 Flex Query XML 解析为结构化 dict，支持多账户、多货币。"""
    root = ET.fromstring(xml_str)

    # 顶层元数据
    generated_at = ""
    report_date = ""

    accounts = []
    for stmt in root.findall(".//FlexStatement"):
        account = _parse_statement(stmt)
        if account:
            if not generated_at:
                generated_at = _fmt_datetime(stmt.get("whenGenerated", ""))
            if not report_date:
                report_date = _fmt_date(stmt.get("toDate", ""))
            accounts.append(account)

    return {
        "generated_at": generated_at,
        "report_date": report_date,
        "accounts": accounts,
    }


def _parse_statement(stmt: ET.Element) -> dict:
    account_id = stmt.get("accountId", "")
    alias = stmt.get("acctAlias", "") or ""
    base_currency = _parse_equity_summary(stmt)[2]

    # ---- 1. 汇率表（本币 → 基础货币）----
    fx_rates = _parse_fx_rates(stmt)

    # ---- 2. 持仓 ----
    positions = _parse_positions(stmt)

    # ---- 3. 现金 ----
    cash_balances, cash_base_total = _parse_cash(stmt, fx_rates, base_currency)

    # ---- 4. 净值（从 EquitySummary 取最新一天）----
    net_liquidation, stock_value_base, base_currency = _parse_equity_summary(stmt)

    # ---- 5. 汇总计算 ----
    total_unrealized_pnl_base = sum(p["unrealized_pnl_base"] for p in positions)
    total_cost_base = sum(p["cost_basis_base"] for p in positions)
    total_unrealized_pnl_pct = (
        (total_unrealized_pnl_base / total_cost_base * 100)
        if total_cost_base != 0 else 0
    )

    return {
        "account_id": account_id,
        "alias": alias,
        "base_currency": base_currency,
        "summary": {
            "net_liquidation": net_liquidation,
            "stock_value_base": stock_value_base,
            "cash_base": cash_base_total,
            "total_unrealized_pnl_base": total_unrealized_pnl_base,
            "total_cost_base": total_cost_base,
            "total_unrealized_pnl_pct": total_unrealized_pnl_pct,
        },
        "positions": positions,
        "cash_balances": cash_balances,
    }


def _parse_fx_rates(stmt: ET.Element) -> dict[str, float]:
    """返回 {currency: rate_to_base}，base 货币自身 rate=1。"""
    rates: dict[str, float] = {}
    for rate in stmt.findall(".//ConversionRate"):
        from_ccy = rate.get("fromCurrency", "")
        to_ccy = rate.get("toCurrency", "")
        r = float(rate.get("rate") or 1)
        if from_ccy and to_ccy:
            rates[f"{from_ccy}->{to_ccy}"] = r
    return rates


def _parse_positions(stmt: ET.Element) -> list[dict]:
    positions = []
    for pos in stmt.findall(".//OpenPosition"):
        # levelOfDetail: SUMMARY 是每个标的聚合持仓，这正是我们需要的
        # （不要跳过 SUMMARY！）
        level = pos.get("levelOfDetail", "")
        if level not in ("SUMMARY", ""):
            continue

        symbol = pos.get("symbol", "")
        description = pos.get("description", "")
        currency = pos.get("currency", "USD")
        asset_category = pos.get("assetCategory", "STK")
        quantity = float(pos.get("position") or 0)
        cost_price = float(pos.get("costBasisPrice") or 0)
        mark_price = float(pos.get("markPrice") or 0)
        market_value = float(pos.get("positionValue") or 0)
        cost_basis = float(pos.get("costBasisMoney") or 0)
        fx_rate = float(pos.get("fxRateToBase") or 1)

        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis != 0 else 0

        # 折算为基础货币
        market_value_base = market_value * fx_rate
        cost_basis_base = cost_basis * fx_rate
        unrealized_pnl_base = unrealized_pnl * fx_rate

        positions.append({
            "symbol": symbol,
            "description": description,
            "currency": currency,
            "asset_category": asset_category,
            "quantity": quantity,
            "cost_price": cost_price,
            "mark_price": mark_price,
            "market_value": market_value,
            "market_value_base": market_value_base,
            "cost_basis": cost_basis,
            "cost_basis_base": cost_basis_base,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_base": unrealized_pnl_base,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "fx_rate": fx_rate,
        })

    # 按基础货币市值降序
    return sorted(positions, key=lambda x: abs(x["market_value_base"]), reverse=True)


def _parse_cash(stmt: ET.Element, fx_rates: dict, base_currency: str) -> tuple[list[dict], float]:
    balances = []
    cash_base_total = 0.0

    for c in stmt.findall(".//CashReportCurrency"):
        currency = c.get("currency", "")
        level = c.get("levelOfDetail", "")

        if currency in ("", "BASE_SUMMARY") or level == "BaseCurrency":
            # BASE_SUMMARY 已是折算后汇总，直接用来得到 cash_base_total
            if level == "BaseCurrency":
                cash_base_total = float(c.get("endingCash") or 0)
            continue

        ending_cash = float(c.get("endingCash") or 0)

        # 用 ConversionRate 折算（如无，fallback 1）
        # 从持仓的 fxRateToBase 推断也可，这里用 rates 表
        rate_key = f"{currency}->{base_currency}"
        fx = fx_rates.get(rate_key, None)
        if fx is None:
            # 尝试从持仓中找该货币的汇率
            for pos in stmt.findall(".//OpenPosition"):
                if pos.get("currency") == currency:
                    fx = float(pos.get("fxRateToBase") or 1)
                    break
        if fx is None:
            fx = 1.0

        balances.append({
            "currency": currency,
            "ending_cash": ending_cash,
            "ending_cash_base": ending_cash * fx,
        })

    return balances, cash_base_total


def _parse_equity_summary(stmt: ET.Element) -> tuple[float, float, str]:
    """返回 (net_liquidation, stock_value, base_currency)，取最新日期的记录。"""
    summaries = stmt.findall(".//EquitySummaryByReportDateInBase")
    if not summaries:
        return 0.0, 0.0, "USD"

    latest = summaries[-1]
    net_liq = float(latest.get("total") or 0)
    stock = float(latest.get("stock") or 0)
    base_currency = latest.get("currency", "USD")

    return net_liq, stock, base_currency


def _fmt_datetime(raw: str) -> str:
    """'20260401;032316' → '2026-04-01 03:23:16'"""
    try:
        date_part, time_part = raw.split(";")
        dt = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return raw


def _fmt_date(raw: str) -> str:
    """'20260331' → '2026-03-31'"""
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%Y-%m-%d")
    except Exception:
        return raw
