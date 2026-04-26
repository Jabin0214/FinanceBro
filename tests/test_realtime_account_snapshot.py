import json

from agent.tools import TOOL_DEFINITIONS, execute_tool
from ibkr.account import get_realtime_account_snapshot
from ibkr.tws_client import TWSNotConnectedError


def test_realtime_account_snapshot_returns_minimal_fields(monkeypatch):
    class Row:
        def __init__(self, account, tag, value, currency):
            self.account = account
            self.tag = tag
            self.value = value
            self.currency = currency

    class Position:
        def __init__(self, account, symbol, quantity, avg_cost, sec_type="STK"):
            self.account = account
            self.position = quantity
            self.avgCost = avg_cost
            self.contract = type(
                "Contract",
                (),
                {"symbol": symbol, "secType": sec_type},
            )()

    class FakeIB:
        def accountSummary(self):
            return [
                Row("U1234567", "NetLiquidation", "123456.78", "USD"),
                Row("U1234567", "AvailableFunds", "45678.90", "USD"),
            ]

        def positions(self):
            return [
                Position("U1234567", "MSFT", 10, 312.34, sec_type="OPT"),
                Position("U1234567", "AAPL", 200, 185.42),
            ]

    class FakeClient:
        def __init__(self):
            self.ib = FakeIB()

        def run(self, coro, timeout=30):
            import asyncio

            return asyncio.run(coro)

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["source"] == "ib_gateway"
    assert result["account_id"] == "U1234567"
    assert result["base_currency"] == "USD"
    assert result["net_liquidation"] == 123456.78
    assert result["available_cash"] == 45678.9
    assert result["positions"] == [
        {"symbol": "AAPL", "quantity": 200, "avg_cost": 185.42}
    ]
    assert result["error"] is None


def test_realtime_account_snapshot_prefers_request_methods(monkeypatch):
    class Row:
        def __init__(self, account, tag, value, currency):
            self.account = account
            self.tag = tag
            self.value = value
            self.currency = currency

    class FakeIB:
        def __init__(self):
            self.summary_requested = False
            self.positions_requested = False

        async def reqAccountSummaryAsync(self):
            self.summary_requested = True
            return [Row("U1", "NetLiquidation", "100000", "USD")]

        async def reqPositionsAsync(self):
            self.positions_requested = True
            return []

    class FakeClient:
        def __init__(self):
            self.ib = FakeIB()

        def run(self, coro, timeout=30):
            import asyncio

            result = asyncio.run(coro)
            assert self.ib.summary_requested is True
            assert self.ib.positions_requested is True
            return result

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["account_id"] == "U1"


def test_realtime_account_snapshot_reads_summary_after_async_refresh(monkeypatch):
    class Row:
        def __init__(self, account, tag, value, currency):
            self.account = account
            self.tag = tag
            self.value = value
            self.currency = currency

    class FakeIB:
        async def reqAccountSummaryAsync(self):
            return None

        def accountSummary(self):
            return [
                Row("U1", "NetLiquidation", "100000", "USD"),
                Row("U1", "AvailableFunds", "9000", "USD"),
            ]

        async def reqPositionsAsync(self):
            return []

    class FakeClient:
        def __init__(self):
            self.ib = FakeIB()

        def run(self, coro, timeout=30):
            import asyncio

            return asyncio.run(coro)

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["account_id"] == "U1"
    assert result["available_cash"] == 9000.0


def test_realtime_account_snapshot_returns_structured_error_on_connection_failure(monkeypatch):
    def fake_get_client():
        raise TWSNotConnectedError("无法连接 IB Gateway")

    monkeypatch.setattr("ibkr.account.get_tws_client", fake_get_client)

    result = get_realtime_account_snapshot()

    assert result["error"] == "无法连接 IB Gateway"
    assert result["positions"] == []
    assert result["net_liquidation"] is None
    assert result["available_cash"] is None


def test_realtime_account_snapshot_does_not_create_query_when_connect_fails(monkeypatch):
    class FakeClient:
        ib = None

        def ensure_connected(self):
            raise TWSNotConnectedError("无法连接 IB Gateway")

        def run(self, coro, timeout=30):
            raise AssertionError("run should not be called when connection fails")

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["error"] == "无法连接 IB Gateway"


def test_realtime_account_snapshot_falls_back_to_total_cash_value(monkeypatch):
    class Row:
        def __init__(self, account, tag, value, currency):
            self.account = account
            self.tag = tag
            self.value = value
            self.currency = currency

    class FakeIB:
        def accountSummary(self):
            return [
                Row("U1", "NetLiquidation", "100000", "USD"),
                Row("U1", "TotalCashValue", "12000", "USD"),
            ]

        def positions(self):
            return []

    class FakeClient:
        def __init__(self):
            self.ib = FakeIB()

        def run(self, coro, timeout=30):
            import asyncio

            return asyncio.run(coro)

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["available_cash"] == 12000.0
    assert result["positions"] == []
    assert result["error"] is None


def test_realtime_account_snapshot_returns_error_when_summary_empty(monkeypatch):
    class FakeIB:
        def accountSummary(self):
            return []

        def positions(self):
            return []

    class FakeClient:
        def __init__(self):
            self.ib = FakeIB()

        def run(self, coro, timeout=30):
            import asyncio

            return asyncio.run(coro)

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert "未获取到账户摘要" in result["error"]
    assert result["positions"] == []


def test_tool_registry_includes_realtime_account_snapshot():
    names = [tool["name"] for tool in TOOL_DEFINITIONS]

    assert "get_realtime_account_snapshot" in names


def test_execute_tool_returns_snapshot_json(monkeypatch):
    monkeypatch.setattr(
        "ibkr.account.get_realtime_account_snapshot",
        lambda: {
            "source": "ib_gateway",
            "generated_at": "2026-04-27T12:00:00+00:00",
            "account_id": "U1",
            "base_currency": "USD",
            "net_liquidation": 100000.0,
            "available_cash": 9000.0,
            "positions": [],
            "error": None,
        },
    )

    payload = execute_tool("get_realtime_account_snapshot", {})
    result = json.loads(payload)

    assert result["account_id"] == "U1"
    assert result["available_cash"] == 9000.0
