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
                      Analyzer (Claude Opus 4.6) — 深度分析（Phase 3+）
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
- 跨天持久化 + 日摘要压缩待 Phase 5 实现

**定价（Sonnet 4.6）**：$3.00 / 1M input tokens，$15.00 / 1M output tokens

### Phase 3 — 新闻解读
**目标**：对持仓标的做新闻分析

- [ ] 选型并集成新闻/搜索 API（Tavily / yfinance / Serper）
- [ ] 新增 `get_news` 工具（加入 tools.py 注册表）
- [ ] Opus 做影响分析：利好/利空/中性
- [ ] 支持自然语言触发（"帮我看看腾讯最近有什么新闻"）

### Phase 4 — 风险分析
**目标**：Opus 对整体仓位做深度风险评估

- [ ] 新增 `get_risk_analysis` 工具
- [ ] 集中度分析（单标的占比）、板块分布、历史回撤估算
- [ ] Telegram `/risk` 命令

### Phase 5 — 跨天记忆
**目标**：对话历史持久化，重启不丢失

- [ ] 历史序列化存储（SQLite 或 JSON 文件）
- [ ] 超长历史摘要压缩（调用 Sonnet 生成日摘要，作为 system prompt 背景）

### Phase 6 — 仓位操作（慎重）
**目标**：支持下单，三层确认机制

- [ ] TWS API 连接（ib_insync）
- [ ] 规则引擎（风控检查）
- [ ] Telegram 确认按钮（inline keyboard）
- [ ] 操作日志审计

### Phase 7 — 定时任务 + 主动推送
**目标**：自动化，无需手动触发

- [ ] 每日早间报告（开盘前）
- [ ] 重大新闻即时推送
- [ ] 持仓盈亏预警（超过阈值）
- [ ] 财报日提醒

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
│   ├── tws_client.py       # Phase 6: TWS 实时连接
│   └── models.py           # 数据模型
│
├── report/                 # 报告输出层（纯 Python，不含 AI）
│   ├── html_report.py      # HTML 报告生成
│   └── formatter.py        # Telegram 文本格式化
│
├── agent/                  # AI 层
│   ├── tools.py            # 工具注册表（扩展新工具只改这里）
│   ├── orchestrator.py     # Sonnet 对话引擎（tool use 循环）
│   └── analyzer.py         # Phase 4+: Opus 深度分析
│
├── bot/
│   ├── telegram_bot.py     # Bot 主逻辑（命令 + 消息处理）
│   └── keyboards.py        # Phase 6: 确认按钮
│
└── scheduler/
    └── tasks.py            # Phase 7: 定时任务
```

---

## 模型分工

| 任务 | 模型 | 理由 |
|------|------|------|
| 对话 / 工具调度 | claude-sonnet-4-6 | 够用，省钱 |
| 数据格式化 / HTML 生成 | 纯 Python | 确定性输出，无需 AI |
| 风险分析 / 新闻解读 | claude-opus-4-6 | 需要深度推理 |
| 交易决策建议 | claude-opus-4-6 + thinking | 最高质量 |

---

## 环境变量

```
TELEGRAM_BOT_TOKEN       Telegram Bot Token
TELEGRAM_ALLOWED_USERS   允许访问的用户 ID（逗号分隔）
IBKR_FLEX_TOKEN          IBKR Flex Web Service Token
IBKR_FLEX_QUERY_ID       Flex Query ID（在 IBKR 后台配置）
ANTHROPIC_API_KEY        Anthropic API Key
```
