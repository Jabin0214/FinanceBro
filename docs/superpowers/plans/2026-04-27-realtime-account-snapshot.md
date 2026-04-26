# Realtime Account Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only IB Gateway realtime account snapshot feature that returns net liquidation, available cash, and current stock positions with quantity and average cost.

**Architecture:** Introduce a new `ibkr/account.py` module that reuses the existing `TWSClient` connection manager, reads `accountSummary` plus `positions` from IBKR via `ib_insync`, normalizes the results into a stable JSON-serializable snapshot, and exposes it through a dedicated Claude tool without changing the existing Flex Query report path.

**Tech Stack:** Python, ib_insync, IB Gateway, existing `agent/tools.py` tool registry, unittest/pytest-style tests

---

## File Structure

- Create: `ibkr/account.py`
  - Realtime account snapshot query and normalization
- Modify: `agent/tools.py`
  - Register and execute `get_realtime_account_snapshot`
- Modify: `README.md`
  - Document the new realtime account snapshot capability
- Create: `tests/test_realtime_account_snapshot.py`
  - Unit tests for success and failure cases

## Task 1: Implement The Realtime Account Snapshot Module

**Files:**
- Create: `ibkr/account.py`
- Test: `tests/test_realtime_account_snapshot.py`

- [ ] **Step 1: Write the failing test for the happy path**

Create `tests/test_realtime_account_snapshot.py` with:

```python
from ibkr.account import get_realtime_account_snapshot


def test_realtime_account_snapshot_returns_minimal_fields(monkeypatch):
    class FakeClient:
        def run(self, coro, timeout=30):
            return {
                "source": "ib_gateway",
                "generated_at": "2026-04-27T12:00:00Z",
                "account_id": "U1234567",
                "base_currency": "USD",
                "net_liquidation": 123456.78,
                "available_cash": 45678.9,
                "positions": [
                    {"symbol": "AAPL", "quantity": 200, "avg_cost": 185.42}
                ],
                "error": None,
            }

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["source"] == "ib_gateway"
    assert result["account_id"] == "U1234567"
    assert result["base_currency"] == "USD"
    assert result["net_liquidation"] == 123456.78
    assert result["available_cash"] == 45678.9
    assert result["positions"][0]["symbol"] == "AAPL"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py::test_realtime_account_snapshot_returns_minimal_fields -q
```

Expected:
- FAIL because `ibkr/account.py` or `get_realtime_account_snapshot` does not exist yet

- [ ] **Step 3: Write the minimal implementation skeleton**

Create `ibkr/account.py` with:

```python
from datetime import datetime, timezone

from ibkr.tws_client import TWSNotConnectedError, get_tws_client


def get_realtime_account_snapshot() -> dict:
    try:
        client = get_tws_client()
        return client.run(_fetch_realtime_account_snapshot(client.ib), timeout=30)
    except TWSNotConnectedError as exc:
        return _empty_snapshot(error=str(exc))
    except Exception as exc:
        return _empty_snapshot(error=f"实时账户快照获取失败：{exc}")


async def _fetch_realtime_account_snapshot(ib) -> dict:
    raise NotImplementedError


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
```

- [ ] **Step 4: Run the test to verify the module shape is correct but behavior still fails**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py::test_realtime_account_snapshot_returns_minimal_fields -q
```

Expected:
- FAIL for behavior mismatch or monkeypatch wiring, not for missing module

- [ ] **Step 5: Implement the realtime snapshot fetcher**

Extend `ibkr/account.py` to:

```python
from datetime import datetime, timezone

from ibkr.tws_client import TWSNotConnectedError, get_tws_client


def get_realtime_account_snapshot() -> dict:
    try:
        client = get_tws_client()
        return client.run(_fetch_realtime_account_snapshot(client.ib), timeout=30)
    except TWSNotConnectedError as exc:
        return _empty_snapshot(error=str(exc))
    except Exception as exc:
        return _empty_snapshot(error=f"实时账户快照获取失败：{exc}")


async def _fetch_realtime_account_snapshot(ib) -> dict:
    summary_rows = ib.accountSummary()
    positions = ib.positions()

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
```

- [ ] **Step 6: Run the test to verify it passes**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py::test_realtime_account_snapshot_returns_minimal_fields -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add ibkr/account.py tests/test_realtime_account_snapshot.py
git commit -m "feat: add realtime account snapshot module"
```

## Task 2: Add Error And Edge-Case Tests

**Files:**
- Modify: `tests/test_realtime_account_snapshot.py`
- Test: `tests/test_realtime_account_snapshot.py`

- [ ] **Step 1: Write failing tests for error and fallback cases**

Append these tests:

```python
from ibkr.tws_client import TWSNotConnectedError


def test_realtime_account_snapshot_returns_structured_error_on_connection_failure(monkeypatch):
    class FakeClient:
        pass

    def fake_get_client():
        raise TWSNotConnectedError("无法连接 IB Gateway")

    monkeypatch.setattr("ibkr.account.get_tws_client", fake_get_client)

    result = get_realtime_account_snapshot()

    assert result["error"] == "无法连接 IB Gateway"
    assert result["positions"] == []
    assert result["net_liquidation"] is None


def test_realtime_account_snapshot_falls_back_to_total_cash_value(monkeypatch):
    class Row:
        def __init__(self, account, tag, value, currency):
            self.account = account
            self.tag = tag
            self.value = value
            self.currency = currency

    class Position:
        def __init__(self, account, symbol, quantity, avg_cost):
            self.account = account
            self.position = quantity
            self.avgCost = avg_cost
            self.contract = type("Contract", (), {"symbol": symbol, "secType": "STK"})()

    class FakeIB:
        def accountSummary(self):
            return [
                Row("U1", "NetLiquidation", "100000", "USD"),
                Row("U1", "TotalCashValue", "12000", "USD"),
            ]

        def positions(self):
            return [Position("U1", "AAPL", 100, 180.0)]

    class FakeClient:
        def __init__(self):
            self.ib = FakeIB()

        def run(self, coro, timeout=30):
            import asyncio
            return asyncio.run(coro)

    monkeypatch.setattr("ibkr.account.get_tws_client", lambda: FakeClient())

    result = get_realtime_account_snapshot()

    assert result["available_cash"] == 12000.0


def test_realtime_account_snapshot_returns_empty_positions_when_none_held(monkeypatch):
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
                Row("U1", "AvailableFunds", "9000", "USD"),
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

    assert result["error"] is None
    assert result["positions"] == []
```

- [ ] **Step 2: Run the targeted test file to verify the new tests fail correctly first**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py -q
```

Expected:
- At least one new test fails before implementation is adjusted

- [ ] **Step 3: Adjust implementation only where needed**

Update `ibkr/account.py` as needed so:
- `TWSNotConnectedError` becomes structured output
- `AvailableFunds` falls back to `TotalCashValue`
- Empty stock positions are valid and not treated as errors

- [ ] **Step 4: Run the targeted test file to verify all tests pass**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py -q
```

Expected:
- All tests in the file pass

- [ ] **Step 5: Commit**

```bash
git add ibkr/account.py tests/test_realtime_account_snapshot.py
git commit -m "test: cover realtime account snapshot edge cases"
```

## Task 3: Expose The Snapshot Through Claude Tools

**Files:**
- Modify: `agent/tools.py`
- Test: `tests/test_realtime_account_snapshot.py`

- [ ] **Step 1: Write the failing tool-surface test**

Add a test like:

```python
import json

from agent.tools import TOOL_DEFINITIONS, execute_tool


def test_tool_registry_includes_realtime_account_snapshot():
    names = [tool["name"] for tool in TOOL_DEFINITIONS]
    assert "get_realtime_account_snapshot" in names


def test_execute_tool_returns_snapshot_json(monkeypatch):
    monkeypatch.setattr(
        "ibkr.account.get_realtime_account_snapshot",
        lambda: {
            "source": "ib_gateway",
            "generated_at": "2026-04-27T12:00:00Z",
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
```

- [ ] **Step 2: Run the tool test to verify it fails first**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py -q
```

Expected:
- FAIL because the tool is not yet registered

- [ ] **Step 3: Add the new tool schema and executor branch**

Update `agent/tools.py` to add:

```python
{
    "name": "get_realtime_account_snapshot",
    "description": (
        "通过 IB Gateway 获取实时账户快照，包括总净值、可用现金、"
        "当前持仓、持仓数量和平均成本。"
        "当用户询问当前实时持仓、实时现金、实时净值、当前有多少股某标的时调用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}
```

And add:

```python
if name == "get_realtime_account_snapshot":
    return _get_realtime_account_snapshot()
```

Plus:

```python
def _get_realtime_account_snapshot() -> str:
    from ibkr.account import get_realtime_account_snapshot

    logger.info("工具调用: get_realtime_account_snapshot")
    result = get_realtime_account_snapshot()
    return json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 4: Run the test file again to verify the tool path passes**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py -q
```

Expected:
- All tests pass

- [ ] **Step 5: Commit**

```bash
git add agent/tools.py tests/test_realtime_account_snapshot.py
git commit -m "feat: expose realtime account snapshot tool"
```

## Task 4: Document The Capability

**Files:**
- Modify: `README.md`
- Test: local grep verification

- [ ] **Step 1: Verify docs do not already describe the feature**

Run:

```bash
rg -n "实时账户快照|get_realtime_account_snapshot|IB Gateway.*持仓" README.md
```

Expected:
- No exact documentation for this new feature yet

- [ ] **Step 2: Add a concise README note**

Add text like:

```md
### Realtime Account Snapshot

通过 IB Gateway 可读取实时账户快照，包含：

- 总净值
- 可用现金
- 当前股票持仓
- 持仓数量
- 平均成本

该能力用于实时账户状态查询，不替代 Flex Query 报表。
```

- [ ] **Step 3: Verify the documentation update is present**

Run:

```bash
rg -n "Realtime Account Snapshot|实时账户快照|可用现金|平均成本" README.md
```

Expected:
- The new capability is documented

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document realtime account snapshot"
```

## Task 5: Verification And Manual Validation

**Files:**
- Test: `tests/test_realtime_account_snapshot.py`
- Test: runtime manual check against IB Gateway

- [ ] **Step 1: Run the focused automated tests**

Run:

```bash
pytest tests/test_realtime_account_snapshot.py -q
```

Expected:
- All realtime account snapshot tests pass

- [ ] **Step 2: Run a broader regression slice**

Run:

```bash
pytest tests/test_option_interfaces.py tests/test_realtime_account_snapshot.py -q
```

Expected:
- Existing option interface tests still pass
- New realtime snapshot tests pass

- [ ] **Step 3: Manually validate against a live IB Gateway**

Run a direct Python check such as:

```bash
python - <<'PY'
from ibkr.account import get_realtime_account_snapshot
from pprint import pprint

pprint(get_realtime_account_snapshot())
PY
```

Expected:
- Returns a structured snapshot
- Shows `net_liquidation`
- Shows `available_cash`
- Shows current stock positions with `symbol`, `quantity`, `avg_cost`

- [ ] **Step 4: Verify failure-path behavior**

With IB Gateway stopped, rerun:

```bash
python - <<'PY'
from pprint import pprint
from ibkr.account import get_realtime_account_snapshot

pprint(get_realtime_account_snapshot())
PY
```

Expected:
- Returns a structured error payload
- Does not crash with an uncaught traceback

- [ ] **Step 5: Commit**

```bash
git log --oneline -n 6
```

Expected:
- Recent history shows the implementation, tests, and docs commits for this feature
