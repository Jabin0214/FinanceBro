# FinanceBro — 项目大纲

## 架构总览

```
用户 (Telegram)
    ↓
Telegram Bot
    ↓
Orchestrator (Claude Sonnet 4.6) — 调度 + 工具调用
    ↓              ↓              ↓
IBKR 报表模块   新闻模块      仓位操作模块
    ↓
Analyzer (Claude Opus 4.6) — 深度分析 + 结论
    ↓
格式化输出 → Telegram
```

---

## 开发阶段

### Phase 1 — 基础报表 ✅
**目标**：Telegram 发指令 → 获取 IBKR 报告 → 格式化返回

- [x] IBKR Flex Query 连接
- [x] XML 解析持仓/现金数据（支持多账户、多币种、汇率折算）
- [x] 生成 HTML 报告文件（纯 Python，深色主题）
- [x] Telegram Bot `/report` 命令 → 发送 HTML 文件

### Phase 2 — 新闻解读 (当前)
**目标**：对持仓标的做新闻分析

- [ ] 集成 Web Search 工具（用 Claude 内置）
- [ ] 针对每个持仓抓取相关新闻
- [ ] Opus 做影响分析：利好/利空/中性
- [ ] Telegram `/news AAPL` 命令

### Phase 3 — 风险分析
**目标**：Opus 对整体仓位做深度风险评估

- [ ] 集中度分析（单标的占比）
- [ ] 板块分布分析
- [ ] 历史回撤估算
- [ ] Telegram `/risk` 命令

### Phase 4 — 多模型 Orchestration
**目标**：Sonnet 调度，Opus 分析，分工明确

- [ ] 重构为 Sonnet 做工具调度
- [ ] Opus 专注深度分析
- [ ] 对话式交互（自由提问）
- [ ] 上下文记忆（多轮对话）

### Phase 5 — 仓位操作（慎重）
**目标**：支持下单，三层确认机制

- [ ] TWS API 连接（ib_insync）
- [ ] 规则引擎（风控检查）
- [ ] Telegram 确认按钮（inline keyboard）
- [ ] 操作日志审计

### Phase 6 — 定时任务 + 主动推送
**目标**：自动化，无需手动触发

- [ ] 每日早间报告（开盘前）
- [ ] 重大新闻即时推送
- [ ] 持仓盈亏预警（超过阈值）
- [ ] 财报日提醒

---

## 文件结构

```
ibkr-agent/
├── main.py                 # 入口
├── config.py               # 配置（从 .env 读取）
├── requirements.txt
├── .env.example
│
├── ibkr/
│   ├── flex_query.py       # Flex Query 报表获取
│   ├── tws_client.py       # Phase 5: TWS 实时连接
│   └── models.py           # 数据模型
│
├── agent/
│   ├── formatter.py        # Sonnet: 数据格式化
│   ├── analyzer.py         # Phase 3+: Opus 深度分析
│   ├── orchestrator.py     # Phase 4+: Sonnet 多工具调度
│   └── tools.py            # Phase 4+: 工具定义
│
├── bot/
│   ├── telegram_bot.py     # Bot 主逻辑
│   └── keyboards.py        # Phase 5: 确认按钮
│
└── scheduler/
    └── tasks.py            # Phase 6: 定时任务
```

---

## 模型分工

| 任务 | 模型 | 理由 |
|------|------|------|
| 工具调度 / 参数提取 | claude-sonnet-4-6 | 够用，省钱 |
| 数据格式化 | claude-sonnet-4-6 | 结构化任务 |
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
