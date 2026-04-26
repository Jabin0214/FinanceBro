# Realtime Account Snapshot Design

## Goal

新增一个基于 IB Gateway / `ib_insync` 的只读实时账户快照能力，返回最小必需字段：

- 总净值
- 可用现金
- 当前持仓列表
- 每个持仓的数量
- 每个持仓的平均成本

该能力用于替代“实时账户状态”场景下对 Flex Query 的依赖，但不取代现有报表链路。

## Scope

本次只做“实时账户快照查询”，不扩展到：

- 股票实时行情
- 期权链
- Greeks / IV / OI / volume
- 自动下单
- 风险分析重构

## Current State

- 仓库已有 `ibkr/tws_client.py`，负责管理 IB Gateway 连接
- 仓库已有 Phase 4 的期权查询逻辑，已依赖 `get_tws_client()`
- 当前账户类数据主路径仍然是 Flex Query，适合报表，不适合实时查询

## Recommended Approach

新增独立的实时账户工具，不改写现有 `get_portfolio` / Flex Query 路径。

设计原则：

1. 报表和实时快照语义分离
2. 只读
3. 最小字段集优先
4. 后续 Phase 4 的现金约束和持仓约束可以直接复用此数据结构

## Files And Responsibilities

### New File

- `ibkr/account.py`
  - 负责通过 IB Gateway 拉取实时账户摘要和持仓
  - 提供结构化、可序列化的快照结果

### Modified Files

- `agent/tools.py`
  - 新增工具 schema
  - 新增执行入口

- `bot/telegram_bot.py`
  - 如项目已有直接命令模式，可增加一个基础命令入口
  - 如果暂不加命令，也至少保证 Claude tool use 可调用

- `README.md`
  - 补充“实时账户快照”能力说明

- `tests/`
  - 为实时账户快照返回结构、失败场景、格式化结果补测试

## Data Contract

第一版返回结构建议固定为：

```python
{
    "source": "ib_gateway",
    "generated_at": "2026-04-27T12:34:56Z",
    "account_id": "U1234567",
    "base_currency": "USD",
    "net_liquidation": 123456.78,
    "available_cash": 45678.90,
    "positions": [
        {
            "symbol": "AAPL",
            "quantity": 200,
            "avg_cost": 185.42,
        }
    ],
    "error": None,
}
```

失败时：

```python
{
    "source": "ib_gateway",
    "generated_at": "...",
    "account_id": None,
    "base_currency": None,
    "net_liquidation": None,
    "available_cash": None,
    "positions": [],
    "error": "无法连接 IB Gateway ..."
}
```

## Data Sources Inside IBKR API

第一版建议只用两类数据：

1. `accountSummary`
   - 读取 `NetLiquidation`
   - 读取 `AvailableFunds`

2. `positions`
   - 读取 `contract.symbol`
   - 读取 `position`
   - 读取 `avgCost`

如果 `AvailableFunds` 缺失，可以接受降级为：
- 优先取 `AvailableFunds`
- 若不存在，再尝试 `TotalCashValue`
- 但对外字段仍统一叫 `available_cash`

## Error Handling

需明确支持以下场景：

1. IB Gateway 未启动 / 无法连接
   - 返回结构化错误
   - 不把底层 traceback 直接暴露给用户

2. 已连接但账户摘要为空
   - 返回结构化错误

3. 已连接但无持仓
   - 返回空 `positions`
   - `error` 仍为 `None`

4. 多账户 / 多 model code
   - 第一版先优先返回默认主账户快照
   - 不在本次引入复杂账户切换参数

## Tool Surface

建议新增工具：

- `get_realtime_account_snapshot`

描述：
- 获取 IB Gateway 的实时账户快照
- 用于回答“当前持仓”“当前可用现金”“我现在有多少股某标的”“现在账户净值是多少”等问题

## User-Facing Behavior

第一版至少支持两种入口之一：

1. Claude tool use 调用
2. Telegram 直接命令调用

如果为了缩小范围，优先级建议是：

1. 先接 `agent/tools.py`
2. 再视项目现有命令结构决定是否增加 bot 命令

## Testing Plan

测试至少覆盖：

1. 成功返回最小字段集
2. IB Gateway 未连接时返回结构化错误
3. 无持仓时返回空列表
4. 缺失 `AvailableFunds` 时的降级逻辑
5. JSON 序列化兼容

## Non-Goals

本次不做：

- 用实时账户快照替换全部 Flex Query 逻辑
- 重新设计风险分析
- 增加实时股票 quote 工具
- 增加实时期权链工具
- 增加下单 / 撤单 / 修改单

## Rollout Plan

1. 新增 `ibkr/account.py`
2. 写最小快照查询函数
3. 在 `agent/tools.py` 注册新工具
4. 增加测试
5. 视范围决定是否接 Telegram 命令
6. 用真实 IB Gateway 做一次人工验证
