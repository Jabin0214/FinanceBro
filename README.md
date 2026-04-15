# FinanceBro — 项目大纲

## 架构总览

```
用户 (Telegram)
    ↓
Telegram Bot
    ↓
Orchestrator (Claude Sonnet 4.6) — 对话 + 工具调度
    ↓              ↓              ↓
IBKR 报表模块   新闻模块      仓位操作模块
                                  ↓
                      Analyzer (Grok) — 风险分析（Phase 5）
```

---

## 开发阶段

### Phase 1 — 基础报表 ✅
**目标**：Telegram 发指令 → 获取 IBKR 报告 → 格式化返回

- [x] IBKR Flex Query 连接
- [x] XML 解析持仓/现金数据（支持多账户、多币种、汇率折算）
- [x] 生成 HTML 报告文件（纯 Python，深色主题）
- [x] Telegram Bot `/report` 命令 → 发送 HTML 文件

### Phase 2 — AI 对话 + 持仓工具 ✅
**目标**：与 Claude Sonnet 自由对话，按需自动调取持仓数据

- [x] `agent/tools.py`：工具注册表（TOOL_DEFINITIONS + execute_tool），可扩展
- [x] `agent/orchestrator.py`：Sonnet 对话循环，滑动窗口历史（MAX_HISTORY=20），tool use 自动循环，每次返回 token 用量
- [x] `bot/telegram_bot.py`：MessageHandler 接收普通消息，per-user 对话历史（内存），`/clear` 命令清除历史
- [x] `/report` 命令保留，直接获取 HTML 不走 AI
- [x] 每次回复后显示 token 用量和费用（美元）
- [x] 回复 HTML 解析失败时自动降级为纯文本

**历史管理策略**：
- 滑动窗口：保留最近 20 条，裁剪时确保从普通 user 消息开始（不破坏 tool_use/tool_result 配对）
- 重启后历史清空（内存存储）
- 跨天持久化 + 日摘要压缩待 Phase 6 实现

**定价（Sonnet 4.6）**：$3.00 / 1M input tokens，$15.00 / 1M output tokens

### Phase 3 — 新闻解读 ✅
**目标**：对持仓标的及大盘做新闻分析

- [x] 集成 xAI Grok API（`grok-4-1-fast-reasoning`，Responses API `/v1/responses`）
- [x] 新增 `get_news` 工具（`web_search` + `x_search` 双源实时搜索）
- [x] Claude Sonnet 对 Grok 返回内容做利好/利空/中性分析
- [x] 支持自然语言触发：个股、行业、大盘、宏观主题均可
- [x] 5 分钟新闻缓存，相同 query 不重复调用 Grok

**模型**：Grok `grok-4-1-fast-reasoning`（xAI Responses API）
**新增环境变量**：`GROK_API_KEY`

### Phase 4 — IBKR 实时期权数据 + 卖方策略辅助
**目标**：基于 IBKR 账户已有行情订阅，提供实时/准实时期权链查看与卖 `cash-secured put` / `covered call` 的候选筛选

- [x] 接入 IBKR TWS / IB Gateway（优先 `ib_insync`）
- [x] 新增 `get_option_chain` 工具：按股票代码返回到期日、行权价、bid/ask、delta、IV、OI、volume
- [x] 新增 `scan_short_put_candidates` 工具：面向 `cash-secured put`
- [x] 新增 `scan_covered_call_candidates` 工具：面向 `covered call`
- [x] 支持自然语言触发：如“帮我看看 AAPL 能卖哪些 put / call”
- [x] 输出中明确区分“数据事实”和“策略建议”，避免把建议包装成确定结论
- [x] 对缺失字段做降级处理：无 Greeks / 无 IV 时仍可返回基础报价，但提示数据不完整

**当前迭代进展（2026-04-16）**：
- 已补强 `get_option_chain` / `scan_short_put_candidates` / `scan_covered_call_candidates` 的参数校验与友好报错
- 已在 Telegram Bot 增加只读命令：`/options`、`/puts`、`/calls`
- 已补充 Telegram 文本格式化，统一展示关键假设、候选合约和风险提示
- 已把账户级约束接入期权扫描：
  - `cash-secured put` 会结合账户 USD 现金余额计算单张资金占用与可卖张数
  - `covered call` 会结合现有正股数量限制可卖张数，不再返回裸 call 候选
- 已补充更严格的账户级风控：
  - 卖 put 会检查卖出后单标的占账户净值是否超过默认 `25%`
  - 候选结果会限制同一到期日最多返回 `2` 个，避免到期日过度集中
- 已补充基础自动化校验，覆盖命令参数解析、格式化输出和关键边界条件

**最小可用范围（MVP）**：
- 标的范围先限制为美股 / ETF 期权
- 策略范围先限制为 `cash-secured put` 与 `covered call`
- 行情范围先做 Level 1 所需字段，不做复杂期权组合定价
- 先服务“人工决策辅助”，不直接联动自动下单

**迭代要求**：
- 每次迭代都必须先保证“只读”，不得默认触发下单、改单、撤单
- 每次迭代都必须有明确输入输出样例，便于 Telegram 和工具层联调
- 每次迭代都必须兼容“无订阅 / 延迟数据 / TWS 未连接”三种失败场景
- 每次迭代都必须补充最少一条风控约束，避免策略建议越做越激进
- 每次迭代都必须在回复中标注关键假设：DTE、delta 范围、OI / volume 下限、是否要求 IV Rank
- 每次迭代完成后，都要用 2 到 3 个真实标的做人工验收（如 `SPY`、`QQQ`、单一个股）

**推荐迭代拆分**：
- Iteration 1：打通 IBKR 连接与单标的期权链读取，先返回原始关键字段
- Iteration 2：加入筛选逻辑，支持按 DTE、delta、权利金、OI、volume 过滤
- Iteration 3：加入自然语言封装与 Telegram 呈现，输出“候选合约 + 理由 + 风险提示”
- Iteration 4：把结果纳入风险分析上下文，例如结合账户现金、现有持仓、集中度做约束

**初始筛选原则（默认，可后续参数化）**：
- `cash-secured put`：优先 `20-45 DTE`、`delta 0.15-0.30`、OI/volume 足够、权利金覆盖值得卖
- `covered call`：优先在已有持仓上寻找 `15-45 DTE`、`delta 0.10-0.25` 的 call
- 裸 `call` 默认不作为推荐策略；如用户明确要求，也必须单独提示无限风险
- 所有建议默认附带“非投资建议，仅供决策辅助”提示

### Phase 5 — 风险分析 ✅（基础完成，期权约束待 Phase 4 完成后补充）
**目标**：对整体仓位做深度风险评估，并为期权卖方策略提供账户级约束

- [x] 新增 `get_risk_analysis` 工具（Claude 对话可触发，`/risk` 命令直接调用）
- [x] 集中度分析（单标的占比、HHI 指数）、币种敞口、资产类别分布、盈亏分布
- [x] `agent/risk_calculator.py`：纯 Python 指标计算（权重以多头总市值为分母；多币种统一用 `cost_basis_base`）
- [x] `agent/analyzer.py`：Grok 分析引擎（`web_search` + `x_search` 实时搜索，结合当前市场动态输出风险报告）
- [x] Telegram `/risk` 命令
- [x] 在期权扫描结果中评估卖 put 所需现金占用、卖 covered call 对现有仓位的影响（基础版）
- [x] 为期权建议增加账户级限制：现金充足度、单标的上限、到期日分散度（基础版）

**模型**：Grok `grok-4-1-fast-reasoning`（实时搜索 + 深度分析，替代原计划的 Opus，兼具时效性和推理能力）

### Phase 6 — 跨天记忆
**目标**：对话历史持久化，重启不丢失

- [ ] 历史序列化存储（SQLite 或 JSON 文件）
- [ ] 超长历史摘要压缩（调用 Sonnet 生成日摘要，作为 system prompt 背景）

### Phase 7 — 仓位操作（慎重）
**目标**：支持下单，三层确认机制；仅在只读辅助稳定后推进

- [ ] TWS API 连接（ib_insync）
- [ ] 规则引擎（风控检查）
- [ ] Telegram 确认按钮（inline keyboard）
- [ ] 操作日志审计
- [ ] 期权单仅开放 `cash-secured put` / `covered call` 两类受限模板
- [ ] 下单前展示盈亏结构、最大风险、资金占用、到期义务
- [ ] 至少三层确认：策略确认 → 参数确认 → 最终发送确认

### Phase 8 — 定时任务 + 主动推送
**目标**：自动化，无需手动触发

- [ ] 每日早间报告（开盘前）
- [ ] 重大新闻即时推送
- [ ] 持仓盈亏预警（超过阈值）
- [ ] 财报日提醒
- [ ] 期权仓位到期提醒、被指派风险提醒、临近除息 covered call 提醒

---

## 文件结构

```
FinanceBro/
├── main.py                 # 入口
├── config.py               # 配置（从 .env 读取）
├── requirements.txt
├── .env.example
│
├── ibkr/
│   ├── flex_query.py       # Flex Query 报表获取
│   ├── parser.py           # XML 解析 → 结构化数据
│   ├── tws_client.py       # Phase 4/7: TWS 实时连接与下单
│   ├── options.py          # Phase 4: 期权链查询与候选筛选
│   └── models.py           # 数据模型
│
├── report/                 # 报告输出层（纯 Python，不含 AI）
│   ├── html_report.py      # HTML 报告生成
│   └── formatter.py        # Telegram 文本格式化（含期权链/候选摘要）
│
├── agent/                  # AI 层
│   ├── tools.py            # 工具注册表（含报表/新闻/期权扫描工具）
│   ├── orchestrator.py     # Sonnet 对话引擎（tool use 循环）
│   ├── analyzer.py         # Phase 5: Grok 风险分析引擎
│   └── risk_calculator.py  # Phase 5: 纯 Python 风险指标计算
│
└── bot/
    └── telegram_bot.py     # Bot 主逻辑（命令 + 消息处理）
```

---

## 模型分工

| 任务 | 模型 | 理由 |
|------|------|------|
| 对话 / 工具调度 | claude-sonnet-4-6 | 够用，省钱 |
| 数据格式化 / HTML 生成 | 纯 Python | 确定性输出，无需 AI |
| 新闻搜索（实时） | grok-4-1-fast-reasoning | X/web 实时数据源 |
| 实时期权链 / 候选筛选 | 纯 Python + IBKR API | 确定性过滤，低延迟，可测试 |
| 风险分析 | grok-4-1-fast-reasoning | 深度推理 + 实时搜索，兼具时效性 |
| 交易决策建议 | claude-opus-4-6 + thinking | 负责解释与权衡，不直接替代风控 |

---

## 环境变量

```
TELEGRAM_BOT_TOKEN       Telegram Bot Token
TELEGRAM_ALLOWED_USERS   允许访问的用户 ID（逗号分隔）
IBKR_FLEX_TOKEN          IBKR Flex Web Service Token
IBKR_FLEX_QUERY_ID       Flex Query ID（在 IBKR 后台配置）
ANTHROPIC_API_KEY        Anthropic API Key
GROK_API_KEY             xAI Grok API Key（console.x.ai）
IBKR_TWS_HOST            IB Gateway / TWS 主机，默认 127.0.0.1
IBKR_TWS_PORT            IB Gateway / TWS 端口，默认 4001
IBKR_TWS_CLIENT_ID       IB Gateway / TWS client id，默认 10
```
