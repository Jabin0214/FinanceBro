"""
Realtime IB Gateway account snapshot helpers.

This module is intentionally read-only. It reports the minimum account fields
needed for realtime account checks without changing the Flex Query report flow.
"""

from datetime import datetime, timezone

from ibkr.tws_client import TWSNotConnectedError, get_tws_client


def get_realtime_account_snapshot() -> dict:
    """Return a JSON-serializable realtime account snapshot from IB Gateway."""
    try:
        client = get_tws_client()
        if hasattr(client, "ensure_connected"):
            client.ensure_connected()
        return client.run(_fetch_realtime_account_snapshot(client.ib), timeout=30)
    except TWSNotConnectedError as exc:
        return _empty_snapshot(error=str(exc))
    except Exception as exc:
        return _empty_snapshot(error=f"实时账户快照获取失败：{exc}")


async def _fetch_realtime_account_snapshot(ib) -> dict:
    summary_rows = await _get_account_summary(ib)
    positions = await _get_positions(ib)

    if not summary_rows:
        return _empty_snapshot(error="未获取到账户摘要，请确认 IB Gateway 已连接且账户可访问")

    account_id = summary_rows[0].account
    base_currency = None
    net_liquidation = None
    available_cash = None
    total_cash_value = None

    for row in summary_rows:
        if row.account != account_id:
            continue
        if row.tag == "NetLiquidation":
            net_liquidation = _safe_float(row.value)
            base_currency = row.currency or base_currency
        elif row.tag == "AvailableFunds":
            available_cash = _safe_float(row.value)
            base_currency = row.currency or base_currency
        elif row.tag == "TotalCashValue":
            total_cash_value = _safe_float(row.value)
            base_currency = row.currency or base_currency

    if available_cash is None:
        available_cash = total_cash_value

    normalized_positions = []
    for item in positions:
        if item.account != account_id:
            continue
        if getattr(item.contract, "secType", None) != "STK":
            continue
        normalized_positions.append(
            {
                "symbol": item.contract.symbol,
                "quantity": item.position,
                "avg_cost": item.avgCost,
            }
        )

    normalized_positions.sort(key=lambda pos: pos["symbol"])

    return {
        "source": "ib_gateway",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_id": account_id,
        "base_currency": base_currency,
        "net_liquidation": net_liquidation,
        "available_cash": available_cash,
        "positions": normalized_positions,
        "error": None,
    }


def _safe_float(value: str | None):
    if value in (None, ""):
        return None
    return float(value)


async def _get_account_summary(ib):
    if hasattr(ib, "reqAccountSummaryAsync"):
        summary_rows = await ib.reqAccountSummaryAsync()
        if summary_rows is not None:
            return summary_rows
    return ib.accountSummary()


async def _get_positions(ib):
    if hasattr(ib, "reqPositionsAsync"):
        return await ib.reqPositionsAsync()
    return ib.positions()


def _empty_snapshot(error: str) -> dict:
    return {
        "source": "ib_gateway",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account_id": None,
        "base_currency": None,
        "net_liquidation": None,
        "available_cash": None,
        "positions": [],
        "error": error,
    }
