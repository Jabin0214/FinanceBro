# FinanceBro — 项目大纲

## 架构总览

```
用户 (Telegram)
    ↓
Telegram Bot
    ↓
Orchestrator (Claude Sonnet 4.6) — 对话 + 工具调度
    ↓              ↓              ↓
IBKR 报表模块   新闻模块      期权数据模块
```

---

## 开发阶段

### Phase 1 — 基础报表 ✅
**目标**：Telegram 发指令 → 获取 IBKR 报告 → 格式化返回

- [x] IBKR Flex Query 连接
- [x] XML 解析持仓/现金数据（多账户、多币种、汇率折算）
- [x] HTML 报告生成（纯 Python，深色主题）
- [x] Telegram `/report` 命令 → 发送 HTML 文件

### Phase 2 — AI 对话 + 持仓工具 ✅
**目标**：与 Claude Sonnet 自由对话，按需自动调取持仓数据

- [x] `agent/tools.py`：工具注册表（`TOOL_DEFINITIONS` + `execute_tool`），可扩展
- [x] `agent/orchestrator.py`：Sonnet 对话循环，滑动窗口历史（`MAX_HISTORY=20`），tool use 自动循环，每次返回 token 用量
- [x] `bot/telegram_bot.py`：MessageHandler 接收普通消息，per-user 对话历史（内存），`/clear` 命令清除历史
- [x] `/report` 命令保留，直接获取 HTML 不走 AI
- [x] 每次回复后显示 token 用量与费用（美元）
- [x] 回复 HTML 解析失败时自动降级为纯文本

**历史管理策略**：
- 滑动窗口：保留最近 20 条，裁剪时确保从普通 user 消息开始（不破坏 tool_use/tool_result 配对）
- 重启后历史清空（内存存储），跨天持久化待 Phase 5

**定价（Sonnet 4.6）**：$3.00 / 1M input tokens，$15.00 / 1M output tokens

### Phase 3 — 新闻解读 ✅
**目标**：对持仓标的及大盘做新闻分析

- [x] 集成 xAI Grok API（`grok-4-1-fast-reasoning`，Responses API `/v1/responses`）
- [x] `get_news` 工具（`web_search` + `x_search` 双源实时搜索）
- [x] Sonnet 对 Grok 返回内容做利好/利空/中性分析
- [x] 支持自然语言触发：个股、行业、大盘、宏观主题
- [x] 5 分钟新闻缓存，相同 query 不重复调用 Grok

**新增环境变量**：`GROK_API_KEY`

### Phase 4 — IBKR 实时期权数据 + 卖方策略辅助 ✅
**目标**：基于 IBKR 行情订阅，提供实时/准实时期权链查看与 `cash-secured put` / `covered call` 候选筛选

- [x] 接入 IBKR TWS / IB Gateway（`ib_insync`）
- [x] `get_option_chain` 工具：按股票代码返回到期日、行权价、bid/ask、delta、IV、OI、volume
- [x] `scan_short_put_candidates` 工具：面向 `cash-secured put`
- [x] `scan_covered_call_candidates` 工具：面向 `covered call`
- [x] Telegram 只读命令：`/options`、`/puts`、`/calls`，附自然语言触发
- [x] 输出区分"数据事实"与"策略建议"，统一展示关键假设、候选合约和风险提示
- [x] 缺失 Greeks / IV 时仍返回基础报价，标注 `greeks_available=False`
- [x] TWS 未连接时返回友好错误，不抛异常
- [x] 账户级约束：
  - `cash-secured put` 结合账户 USD 现金计算单张资金占用与可卖张数
  - `covered call` 结合现有正股数量限制可卖张数，不返回裸 call
  - 卖 put 检查卖出后单标的占账户净值是否超过默认 `25%`
  - 候选结果限制同一到期日最多 `2` 个，避免到期日过度集中
- [x] 自动化校验覆盖命令参数解析、格式化输出和关键边界条件

**约束**：
- 只读，不触发任何下单操作
- 标的限美股 / ETF 期权，策略限 `cash-secured put` 与 `covered call`
- 裸 `call` 不作为推荐策略
- 所有建议附带"非投资建议，仅供决策辅助"提示

**初始筛选原则（可参数化）**：
- `cash-secured put`：`20-45 DTE`、`|delta| 0.15-0.30`、OI/volume 满足流动性
- `covered call`：在已有持仓上找 `15-45 DTE`、`delta 0.10-0.25`

### Phase 5 — 跨天记忆
**目标**：对话历史持久化，重启不丢失

- [ ] 历史序列化存储（SQLite 或 JSON）
- [ ] 超长历史摘要压缩（Sonnet 生成日摘要，作为 system prompt 背景）

### Phase 6 — 仓位操作（慎重）
**目标**：支持下单，三层确认机制；仅在只读辅助稳定后推进

- [ ] TWS API 下单连接
- [ ] 规则引擎（风控检查）
- [ ] Telegram 确认按钮（inline keyboard）
- [ ] 操作日志审计
- [ ] 期权单仅开放 `cash-secured put` / `covered call` 两类受限模板
- [ ] 下单前展示盈亏结构、最大风险、资金占用、到期义务
- [ ] 三层确认：策略 → 参数 → 最终发送

### Phase 7 — 定时任务 + 主动推送
**目标**：自动化，无需手动触发

- [ ] 每日早间报告（开盘前）
- [ ] 重大新闻即时推送
- [ ] 持仓盈亏预警（超过阈值）
- [ ] 财报日提醒
- [ ] 期权仓位到期、被指派、临近除息 covered call 提醒

---

## 文件结构

```
FinanceBro/
├── main.py                 # 入口
├── config.py               # 配置（从 .env 读取）
├── requirements.txt
│
├── ibkr/
│   ├── flex_query.py       # Flex Query 报表获取
│   ├── parser.py           # XML 解析 → 结构化数据
│   ├── tws_client.py       # TWS / IB Gateway 实时连接
│   ├── options.py          # 期权链查询与候选筛选
│   └── models.py           # 数据模型
│
├── report/                 # 报告输出层（纯 Python，不含 AI）
│   ├── html_report.py      # HTML 报告生成
│   └── formatter.py        # Telegram 文本格式化（含期权链/候选摘要）
│
├── agent/
│   ├── tools.py            # 工具注册表（报表 / 新闻 / 期权扫描）
│   └── orchestrator.py     # Sonnet 对话引擎（tool use 循环）
│
└── bot/
    └── telegram_bot.py     # Bot 主逻辑（命令 + 消息处理）
```

---

## Telegram 命令

| 命令 | 说明 |
|------|------|
| `/start` | 显示帮助 |
| `/report` | 直接获取持仓 HTML 报告（不走 AI） |
| `/options SYMBOL [dte_min] [dte_max]` | 查看期权链摘要 |
| `/puts SYMBOL [dte_min] [dte_max]` | 扫描 cash-secured put 候选 |
| `/calls SYMBOL [dte_min] [dte_max]` | 扫描 covered call 候选 |
| `/clear` | 清除当前对话历史 |
| 普通消息 | 与 Claude Sonnet 对话，按需自动调取持仓 / 新闻 / 期权数据 |

---

## 模型分工

| 任务 | 模型 | 理由 |
|------|------|------|
| 对话 / 工具调度 | claude-sonnet-4-6 | 够用，省钱 |
| 数据格式化 / HTML 生成 | 纯 Python | 确定性输出，无需 AI |
| 新闻搜索（实时） | grok-4-1-fast-reasoning | X / web 实时数据源 |
| 实时期权链 / 候选筛选 | 纯 Python + IBKR API | 确定性过滤，低延迟，可测试 |
| 交易决策建议 | claude-opus-4-6 + thinking | 解释与权衡，不直接替代风控 |

---

## 环境变量

```
TELEGRAM_BOT_TOKEN       Telegram Bot Token
TELEGRAM_ALLOWED_USERS   允许访问的用户 ID（逗号分隔）
IBKR_FLEX_TOKEN          IBKR Flex Web Service Token
IBKR_FLEX_QUERY_ID       Flex Query ID（IBKR 后台配置）
ANTHROPIC_API_KEY        Anthropic API Key
GROK_API_KEY             xAI Grok API Key（console.x.ai）
IBKR_TWS_HOST            IB Gateway / TWS 主机，默认 127.0.0.1
IBKR_TWS_PORT            IB Gateway / TWS 端口，默认 4001
IBKR_TWS_CLIENT_ID       IB Gateway / TWS client id，默认 10
```
