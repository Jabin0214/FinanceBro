# FinanceBro

FinanceBro 是一个通过 Telegram 使用的私人投资助手，用来分析 Interactive Brokers (IBKR) 账户：实时持仓、HTML 报表、组合风险、历史复盘、历史风险指标、每日快照和开盘前简报。

它采用 **Supervisor + Specialist** 多 Agent 架构：Claude Sonnet 负责对话和工具调度，Grok 专门处理实时新闻与风险分析，IBKR / SQLite / HTML 报表等确定性工作全部由 Python 工具完成。

---

## 当前状态

**V1 已完成并可部署**，**V2 Iteration 1 已落地（PR #1）**：

### V1 功能

- Telegram 私聊 Bot，带白名单鉴权
- IBKR Flex Query 拉取持仓
- HTML 持仓报告
- Claude Orchestrator 对话入口
- Grok News Agent
- Grok Risk Analyst Agent
- Portfolio Historian 工具，可回答 7 / 30 / 90 天组合变化
- SQLite 持久化对话历史、原始报表、账户快照、持仓快照、现金快照
- 每日自动快照
- 开盘前简报
- 持仓阈值预警
- 可选实验功能：重大新闻 / 财报提醒轮询
- GitHub Actions 自动部署到 Oracle Cloud VM

### V2 Iteration 1（已落地）

- **历史风险指标**：年化波动率、最大回撤、历史 VaR 95%、CVaR 95%、Sharpe、Sortino，基于每日快照序列计算
- **`get_risk_metrics` Orchestrator 工具**：自然语言直接触发，例如"过去 30 天我的组合风险怎么样"
- **持久化触发去重**：新建 `bot/triggers.py` + `trigger_files` 表，阈值预警和新闻监控的去重状态写入 SQLite，重启不丢
- **新闻影响排序**：`agent/news_impact.py` 对新闻按"持仓权重 × 关键词极性"打分，开盘前新闻推送优先展示高影响条目

### V2 Iteration 2（已落地）
- **目标仓位管理**：`/settarget` 存储目标配置，`get_rebalancing_suggestion` 工具分析偏差
- **调仓建议**：AI 可回答"当前哪些标的需要买入/卖出"
- **开盘简报增强**：加入昨日净值变动趋势行（📈/📉）
- **仓位偏离预警**：持仓偏离目标超阈值时自动推送（`DRIFT_ALERT_ENABLED=true`）

---

## 用户怎么用

在 Telegram 私聊 Bot 发送命令或自然语言。所有命令只在私聊中有效，群聊会被拒绝。

---

### 命令速查表

| 命令 | 说明 |
|------|------|
| `/start` | 显示帮助信息 |
| `/report` | 拉取 IBKR 最新持仓，生成 HTML 报告，不走 AI |
| `/risk` | 直接触发 Risk Analyst（Grok）对当前组合做风险点评 |
| `/news <关键词>` | 直接触发 News Agent 搜索新闻，例如 `/news AAPL earnings` |
| `/brief` | 立即生成开盘前简报，包含净值、NLV 趋势、主要持仓和风险提醒 |
| `/history` | 查看最近 30 天组合复盘，对比净值 / 持仓 / 现金变化 |
| `/alerts` | 手动检查持仓浮亏 / 集中度阈值，主要用于临时排查 |
| `/settarget <SYMBOL> <PCT> ...` | 设置目标仓位，支持一次批量输入多个标的 |
| `/target` | 查看当前已保存的目标仓位配置 |
| `/clear` | 清除当前用户对话历史，重置对话上下文 |

---

### 1. 持仓查询

**直接拉报告（不走 AI）：**

```text
/report
```

返回当前 IBKR 账户的 HTML 持仓报告，包含各账户汇总、持仓明细、现金、净值（NLV）。适合想快速看数字而不需要 AI 解读时使用。

**通过自然语言查询（AI 汇总分析）：**

```text
帮我看看现在持仓怎么样
```

```text
我现在哪些仓位亏损最多？
```

```text
港股和美股各占多少比例？
```

```text
现金比例多少？
```

AI（Claude Sonnet）会实时拉取 IBKR 数据，分析后用自然语言回复。支持追问，上下文跨多轮保留。

---

### 2. 风险分析

**直接触发风险分析（Grok Risk Analyst）：**

```text
/risk
```

**通过自然语言触发：**

```text
这个组合风险高不高？
```

```text
集中度是多少？有没有单一持仓超过 30%？
```

```text
有没有潜在风险需要注意？
```

风险分析包含：
- HHI 赫芬达尔指数（集中度量化）
- 前五大持仓占比
- 单一持仓超阈值提醒
- 浮盈 / 浮亏分布
- Grok 结合实时信息的风险点评

**历史风险指标（基于过去快照序列）：**

```text
过去 90 天的年化波动率、最大回撤和 Sharpe 是多少？
```

```text
帮我看看过去 30 天组合风险，包括 VaR 和 Sortino
```

```text
最大回撤是什么时候发生的？
```

支持窗口：7 天 / 30 天 / 60 天 / 90 天。指标包括：
- 年化波动率
- 最大回撤（及发生日期）
- 历史 VaR 95%（单日最坏亏损估计）
- CVaR 95%（极端情况平均亏损）
- Sharpe 比率（无风险利率 2%）
- Sortino 比率（只惩罚下行波动）

---

### 3. 历史复盘

**查看最近 30 天组合变化：**

```text
/history
```

**通过自然语言查询：**

```text
过去 30 天我的组合发生了什么变化？
```

```text
上个月净值变动了多少？
```

```text
过去 90 天有哪些持仓新开仓或平仓了？
```

```text
过去 7 天浮盈最大的标的是哪个？
```

复盘内容包括：净值 / 股票市值 / 现金 / 浮盈 / 成本变化，以及开仓、平仓、加仓、减仓事件识别。

---

### 4. 目标仓位与调仓建议

这是 V2 Iteration 2 新增功能，用来管理目标仓位配置、计算当前偏差并获取 AI 调仓建议。

#### 4.1 设置目标仓位

```text
/settarget AAPL 30 MSFT 20 CASH 10
```

格式：`/settarget 标的1 百分比1 标的2 百分比2 ...`

- 标的名称不区分大小写（会自动转大写）
- 百分比是以净值（NLV）为基准的目标占比，单位 `%`
- 支持 `CASH` 作为现金目标
- 目标仓位不必加总到 100%（未分配部分视为"自由仓位"）
- 每次调用 `/settarget` 会**完全替换**已有配置（不是追加）

示例：科技股为主的组合

```text
/settarget AAPL 25 MSFT 20 NVDA 15 TSLA 10 CASH 10
```

Bot 回复：

```text
✅ 目标仓位已保存（5 个标的）

AAPL  25.0%
MSFT  20.0%
NVDA  15.0%
TSLA  10.0%
CASH  10.0%

合计：80.0%（剩余 20.0% 未分配）
```

#### 4.2 查看目标仓位

```text
/target
```

显示已保存的目标配置和各仓位百分比。未设置过目标时会提示使用 `/settarget`。

#### 4.3 获取调仓建议（AI）

设置目标仓位后，可以直接用自然语言让 AI 计算偏差并给出操作建议：

```text
我现在哪些标的需要买入或卖出？
```

```text
和目标仓位相比，现在偏差最大的是哪个？
```

```text
帮我做一下调仓分析，告诉我每个标的的偏差和建议操作金额
```

```text
NVDA 现在是超配还是低配？
```

AI 会综合当前持仓和目标配置，输出每个标的的：
- 当前权重 vs 目标权重
- 偏差百分点（正数 = 超配，负数 = 低配）
- 建议买入 / 卖出金额（以 NLV 为基准）

示例回复（精简）：

```text
当前组合 vs 目标仓位偏差：

🟡 AAPL：低配 -8.3%  → 建议买入 $12,450
🔴 NVDA：超配 +5.1%  → 建议卖出 $7,650
🟡 CASH：低配 -3.2%  → 建议增持 $4,800
🟢 MSFT：基本持平 +0.4%

最大偏差标的：AAPL -8.3%
```

> **注意：** FinanceBro 只给建议，不会自动下单。所有交易需在 IBKR 客户端手动执行。

---

### 5. 新闻与财报搜索

**直接搜索：**

```text
/news TSLA earnings
```

```text
/news AAPL 苹果 新产品
```

**通过自然语言触发：**

```text
今天 TSLA 有什么新闻？
```

```text
NVDA 最近财报情况怎么样？下次财报是什么时候？
```

```text
美联储最新政策对我的科技股持仓有什么影响？
```

新闻 Agent（Grok）同时搜索 Web 和 X（Twitter），返回最相关的近期新闻，并标注来源时间。

---

### 6. 开盘前简报解读

**立即获取简报：**

```text
/brief
```

Bot 会实时拉取 IBKR 数据，生成一份包含以下内容的简报：

```text
📊 开盘前简报

日期：2026-01-15
净值：$142,358.20
📉 净值变动：-1,243.00（-0.9%）vs 昨日
🔴 整体浮动：-3.2%（$-4,682.00）

前五大持仓：71.3% · HHI：1,842

主要持仓
AAPL 28.1%（浮动 +12.3%）
NVDA 19.4%（浮动 -5.1%）
MSFT 15.2%（浮动 +8.7%）
TSLA 8.6%（浮动 -18.2%）
CASH 6.8%

风险提醒
🔴 TSLA 单一持仓占比 8.6%（未触发阈值）
🟢 未触发浮亏阈值
```

**关键字段解读：**

| 字段 | 含义 |
|------|------|
| `净值（NLV）` | 账户总市值（股票 + 现金） |
| `净值变动` | 与前一日快照相比的 NLV 变化（📈 正 / 📉 负） |
| `整体浮动` | 总持仓未实现盈亏 / 总成本 |
| `HHI` | 赫芬达尔指数，越高表示集中度越高（2500+ 为高度集中） |
| `前五大持仓 %` | 前五大持仓占 NLV 的合计比例 |
| `浮动 %（每个标的）` | 该标的的未实现盈亏比例 |

**净值变动（NLV 趋势行）**只有在有两天及以上历史快照时才出现。首次部署当天会缺失该行，第二天起自动显示。

---

### 7. 预警系统

FinanceBro 支持三类预警，全部基于 Telegram 主动推送。

#### 7.1 持仓阈值预警（默认开启）

**触发条件：**
- 整体浮亏 ≤ -5%（可在 `config.py` 修改）
- 单一持仓占比 ≥ 35%（可在 `config.py` 修改）

**推送时间：** 每天 08:35（`Pacific/Auckland` 时区）

**手动触发检查：**

```text
/alerts
```

**去重规则：** 同一天同一条件触发后，冷却 12 小时才再次推送，每日最多 3 次。

#### 7.2 仓位偏离预警（默认关闭）

偏离预警在当前持仓与目标仓位偏差超过阈值时自动推送。

**启用方式（`.env` 或环境变量）：**

```env
DRIFT_ALERT_ENABLED=true
DRIFT_ALERT_THRESHOLD_PCT=10.0
```

**触发条件：** 任意标的的当前权重与目标权重偏差 ≥ `DRIFT_ALERT_THRESHOLD_PCT`（百分点）

**推送时间：** 每天 09:00

**推送内容示例：**

```text
📊 仓位偏离预警

🟡 AAPL：低配 8.3%（建议买入 $12,450）
🔴 NVDA：超配 5.1%（建议卖出 $7,650）
🟡 CASH：低配 3.2%（建议增持 $4,800）

最大偏离：AAPL 8.3%（阈值 10%）
```

**去重规则：** 冷却 12 小时，每日最多 2 次。

> 使用偏离预警必须先通过 `/settarget` 设置目标仓位，否则 Bot 会跳过该 job 并记录日志。

#### 7.3 重大新闻 / 财报提醒（默认关闭，实验性）

**启用方式：**

```env
PROACTIVE_NEWS_ENABLED=true
```

**触发频率：** 每 180 分钟扫描一次当前持仓的前五大标的

**推送内容：** 相关新闻摘要 + 按"持仓权重 × 新闻极性"排序的前 3 条高影响新闻

**去重规则：** 冷却 4 小时，每日最多 4 次。

---

### 8. 对话示例（多轮）

FinanceBro 支持多轮对话，会记住上下文直到使用 `/clear` 清除。

**示例一：持仓审视 + 调仓决策**

```text
用户：帮我看看现在持仓
Bot：[拉取持仓，列出各账户汇总]

用户：NVDA 现在是多少比例？
Bot：NVDA 当前占 NLV 的 19.4%，是您第二大持仓...

用户：和我的目标配置相比呢？
Bot：您的目标是 NVDA 15%，当前超配 4.4%，建议卖出约 $6,600...

用户：那 AAPL 呢？
Bot：AAPL 目标 25%，当前 16.2%，低配 8.8%，建议买入约 $13,200...
```

**示例二：风险审查 + 历史对比**

```text
用户：过去 30 天我的组合风险指标是多少？
Bot：[展示波动率、最大回撤、VaR、Sharpe 等指标]

用户：最大回撤是什么时候发生的？
Bot：30 天内最大回撤 -4.2%，发生在 12 月 18 日...

用户：那个时候有什么新闻？
Bot：[搜索 12 月 18 日前后的相关新闻]
```

**示例三：调仓工作流**

```text
用户：/settarget AAPL 25 MSFT 20 NVDA 15 CASH 10
Bot：✅ 目标仓位已保存（4 个标的）

用户：现在哪些标的偏离最大？
Bot：[调用 get_rebalancing_suggestion，计算偏差]

用户：帮我把这些偏差总结一下，以便我去 IBKR 手动操作
Bot：[输出结构化操作清单]
```

---

---

## 30 秒上手

```bash
git clone https://github.com/Jabin0214/FinanceBro.git
cd FinanceBro
cp .env.example .env
docker compose up -d --build
docker compose logs -f
```

确认日志出现：

```text
🤖 FinanceBro 启动中...
```

然后去 Telegram 私聊 Bot，发送：

```text
/start
```

---

## 环境变量

`.env` 只保留真正需要部署时填写的内容。

| 变量 | 说明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | BotFather 给的 Telegram Bot Token |
| `TELEGRAM_ALLOWED_USERS` | 允许访问的 Telegram user id，逗号分隔 |
| `IBKR_FLEX_TOKEN` | IBKR Flex Web Service Token |
| `IBKR_FLEX_QUERY_ID` | IBKR Flex Query ID |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `GROK_API_KEY` | xAI Grok API Key |
| `PROACTIVE_NEWS_ENABLED` | 是否启用实验性的新闻 / 财报轮询，默认 `false` |

产品默认值写在 `config.py`：

- 时区：`Pacific/Auckland`
- 每日快照：`07:00`
- 开盘前简报：`08:30`
- 阈值预警：`08:35`
- 主动推送接收人：`TELEGRAM_ALLOWED_USERS` 的第一个用户
- 整体浮亏阈值：`-5%`
- 单一持仓集中度阈值：`35%`
- 阈值预警触发冷却：`12 小时`，每日上限 `3 次`
- 新闻监控触发冷却：`4 小时`，每日上限 `4 次`
- 新闻 / 财报轮询间隔：`180` 分钟，默认关闭，建议只在需要主动监控时开启
- `DRIFT_ALERT_ENABLED`：仓位偏离预警开关（默认 false）
- `DRIFT_ALERT_THRESHOLD_PCT`：触发预警的最大偏离阈值，单位百分点（默认 10.0）

安全原则：

- 不要把 `.env` 提交到 Git
- 不要把真实 token 写进 README、测试或代码注释
- Telegram 只允许私聊使用，群聊里会拒绝响应

---

## 架构

```text
User (Telegram)
  |
  v
bot/telegram_bot.py
  - Application 装配
  - 命令注册
  - scheduler 初始化
  |
  v
bot/handlers.py
  - 私聊 + 白名单鉴权
  - /report /risk /news /brief /alerts /history /settarget /target /clear
  - 普通消息转给 Orchestrator
  |
  v
agent/orchestrator.py
  - Claude Sonnet
  - tool-use 主循环
  - history trim
  - token / cost 统计
  |
  +--> agent/tools/portfolio.py     -> IBKR Flex Query
  +--> agent/tools/history.py       -> SQLite 历史快照聚合
  +--> agent/tools/report.py        -> HTML 报告
  +--> agent/tools/news.py          -> Grok web_search + x_search
  +--> agent/tools/risk.py          -> risk_calculator + Grok Risk Analyst
  +--> agent/tools/risk_metrics.py  -> 历史风险指标（波动率 / 回撤 / VaR / Sharpe）
  +--> agent/tools/rebalancing.py   -> 调仓偏差计算（get_rebalancing_suggestion）
```

后台任务：

```text
bot/scheduler.py
  |
  +--> daily_snapshot_job      每日持仓快照
  +--> opening_brief_job       开盘前简报（含 NLV 趋势行）
  +--> threshold_alert_job     持仓阈值预警（Trigger 去重，冷却 12h）
  +--> news_monitor_job        重大新闻 / 财报提醒轮询（Trigger 去重，冷却 4h）
  |                              └── agent/news_impact.py  新闻影响打分（持仓权重 × 极性）
  +--> drift_alert_job         仓位偏离预警（默认关闭，Trigger 去重，冷却 12h）
                                 └── agent/rebalancing.py  偏差计算引擎
```

数据层：

```text
storage/db.py
  - SQLite schema
  - WAL + busy_timeout

storage/memory.py
  - per-user Telegram 对话历史

storage/portfolio_store.py
  - raw_reports
  - portfolio_snapshots      每日账户净值快照
  - position_snapshots       每日持仓快照
  - cash_snapshots           每日现金快照
  - 历史聚合查询
  - get_net_liquidation_series  NLV 时序（供风险指标计算）

storage/db.py 表清单
  - chat_messages            对话历史
  - raw_reports              原始 IBKR XML 报表
  - portfolio_snapshots      账户净值
  - position_snapshots       持仓
  - cash_snapshots           现金
  - trigger_fires            主动推送触发记录（去重 / 冷却）
  - target_allocations       目标仓位配置（user_id + symbol + target_pct）
```

---

## 模型分工

| 任务 | 实现 | 说明 |
|------|------|------|
| 对话 / 工具调度 | `claude-sonnet-4-6` | 负责理解用户意图和调用工具 |
| 新闻搜索 | `grok-4-1-fast-reasoning` | 使用 `web_search` 和 `x_search` |
| 风险分析 | `grok-4-1-fast-reasoning` | 结合风险指标和实时搜索 |
| 历史复盘 | Python + Claude | SQLite 聚合历史快照，Claude 负责解释 |
| 报表渲染 | Python | 确定性 HTML 输出 |
| 风险指标（实时） | Python | HHI、集中度、币种敞口、盈亏分布 |
| 历史风险指标 | Python | 波动率、最大回撤、VaR/CVaR、Sharpe、Sortino，基于快照序列 |
| 新闻影响排序 | Python | 关键词极性 × 持仓权重，确定性可复现，无 LLM 调用 |
| 触发去重 | SQLite | `trigger_fires` 表，冷却 + 每日上限，重启不丢 |
| 数据持久化 | SQLite | 本地文件，Docker volume 持久化 |

---

## 目录结构

```text
FinanceBro/
├── main.py
├── config.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── railway.toml
│
├── bot/
│   ├── telegram_bot.py       Telegram Application 装配 + 命令注册
│   ├── handlers.py           命令处理器 + 鉴权
│   ├── auth.py               白名单鉴权
│   ├── history.py            对话历史管理
│   ├── messaging.py          HTML 发送 + fallback
│   ├── proactive.py          主动推送任务逻辑（简报 / 预警 / 新闻）
│   ├── scheduler.py          APScheduler 注册
│   └── triggers.py           ★ 持久化触发去重（Trigger + cooldown）
│
├── agent/
│   ├── orchestrator.py       Claude Sonnet tool-use 主循环
│   ├── analyzer.py           组合分析辅助
│   ├── risk_calculator.py    实时风险指标（HHI / 集中度 / 盈亏分布）
│   ├── risk_metrics.py       ★ 历史风险指标（波动率 / 回撤 / VaR / Sharpe）
│   ├── news_impact.py        ★ 新闻影响打分（持仓权重 × 极性）
│   ├── rebalancing.py        ★★ 调仓偏差引擎（纯 Python，零外部依赖）
│   └── tools/
│       ├── __init__.py       工具注册表
│       ├── _state.py         当前用户状态
│       ├── portfolio.py      IBKR 持仓拉取
│       ├── history.py        历史快照聚合
│       ├── report.py         HTML 报告
│       ├── news.py           Grok 新闻搜索
│       ├── risk.py           Grok 风险分析
│       ├── risk_metrics.py   ★ 历史风险指标工具
│       └── rebalancing.py    ★★ get_rebalancing_suggestion 工具
│
├── ibkr/
│   ├── flex_query.py         Flex Web Service 拉取
│   └── parser.py             XML 解析
│
├── report/
│   └── html_report.py        HTML 报表渲染
│
├── storage/
│   ├── db.py                 SQLite schema + connect / transaction
│   ├── memory.py             per-user 对话历史
│   ├── portfolio_store.py    快照读写 + 历史聚合
│   └── allocation_store.py   ★★ 目标仓位 CRUD（set_targets / get_targets）
│
└── tests/
    ├── agent/                风险指标 / 新闻打分 / 工具单测
    ├── bot/                  命令 / Trigger / 主动推送单测
    ├── ibkr/                 Flex Query / parser 单测
    ├── scheduler/            scheduler job 注册单测
    └── storage/              DB schema / 快照读写单测
```

> ★ 标记为 V2 Iteration 1 新增文件；★★ 标记为 V2 Iteration 2 新增文件

---

## 开发阶段

### Phase 1 — 基础报表

状态：✅ 完成

- IBKR Flex Query
- XML 解析
- HTML 报告
- Telegram `/report`

### Phase 2 — AI 对话 + 持仓工具

状态：✅ 完成

- Claude Orchestrator
- Tool registry
- SQLite 对话历史
- prompt caching
- token / cost footer

### Phase 3 — 新闻 Agent

状态：✅ 完成

- Grok News Agent
- `web_search`
- `x_search`
- `/news <关键词>`

### Phase 4 — 风险 Agent

状态：✅ 完成

- Python 风险指标（HHI / 集中度 / 盈亏分布）
- Grok Risk Analyst
- `/risk`

### Phase 5 — 跨天记忆

状态：✅ 完成

- SQLite conversation history
- raw IBKR report 入库
- 账户 / 持仓 / 现金快照
- `/history` 30 天组合复盘摘要

### Phase 6 — 定时任务 + 主动推送

状态：✅ 完成

- 每日快照
- 开盘前简报，包含风险提醒
- 阈值预警，可手动检查或随简报查看
- 实验性新闻 / 财报轮询，默认关闭

### Phase 7 — Portfolio Historian 工具

状态：✅ 完成

- `get_portfolio_history` Orchestrator 工具
- 支持 7 / 30 / 90 天历史窗口
- 对比净值、股票市值、现金、浮盈和成本变化
- 识别开仓、平仓、加仓、减仓
- 汇总主要浮盈浮亏贡献

### Phase 8 — V2 Iteration 1（历史风险 + 持久触发 + 新闻打分）

状态：✅ 完成（PR #1）

**历史风险指标**
- `agent/risk_metrics.py`：年化波动率、最大回撤、历史 VaR 95%、CVaR 95%、Sharpe、Sortino
- `agent/tools/risk_metrics.py`：暴露为 `get_risk_metrics` Orchestrator 工具
- `storage.portfolio_store.get_net_liquidation_series`：NLV 时序读取，SQL-level LIMIT

**持久化触发去重**
- `bot/triggers.py`：`Trigger` 数据类（cooldown_seconds + max_fires_per_day）
- `trigger_fires` SQLite 表：持久化每次触发记录，跨重启有效
- `bot/proactive.py` 重构：`_sent_*_keys` 内存集合替换为 `should_fire` / `record_fire`

**新闻影响排序**
- `agent/news_impact.py`：`extract_mentioned_symbols` / `polarity_score` / `score_headline` / `rank_news_by_impact`
- `news_monitor_job` 在推送前插入"影响排序（前 3 条）"，高权重持仓优先展示

---

## 部署

生产环境部署到 Oracle Cloud VM。

约定：

- 服务器应用目录：`/opt/financebro`
- 数据库路径：`/opt/financebro/data/financebro.db`
- 容器内数据库路径：`/app/data/financebro.db`
- Docker volume：`./data:/app/data`

推送到 `main` 后，GitHub Actions 自动部署：

```bash
git push origin main
```

GitHub Actions Secrets：

```text
ORACLE_HOST
ORACLE_HOST_KEY
ORACLE_PORT
ORACLE_SSH_KEY
ORACLE_USER
```

手动兜底：

```bash
ssh ubuntu@<ORACLE_HOST> '
cd /opt/financebro &&
git fetch origin main &&
git checkout main &&
git reset --hard origin/main &&
docker compose up -d --build &&
docker compose ps &&
docker compose logs --tail=50
'
```

---

## 测试与验证

当前：**112 个测试，0 个失败**

```bash
pytest -q
```

```bash
python -m compileall -q . -x '(^|/)(\.git|\.worktrees|data|__pycache__|\.pytest_cache)(/|$)'
```

```bash
docker compose config --quiet
```

```bash
git diff --check
```

发布前至少确认：

- 全量测试通过
- `.env` 没有被 Git 跟踪
- `data/` 没有被 Git 跟踪
- Docker daemon 可用时，镜像能 build
- GitHub Actions 部署成功

---

## 给 AI 开发者的 Skill

这一节是给后续 AI 开发 FinanceBro 时使用的项目 skill。接手本项目时，先读本节，再读相关代码。

### 触发场景

当用户要求你开发、修复、审计或扩展 FinanceBro 时，使用本 README 作为项目上下文。

典型请求：

- "给 FinanceBro 加一个新 Agent"
- "帮我修 Telegram bot"
- "新增一个 slash command"
- "完善 IBKR 持仓历史分析"
- "修部署 / GitHub Actions"
- "检查 V1 上线风险"

### 工作原则

1. **不要泄露 secret**
   不打印 `.env` 中的 token、API key、SSH key。检查配置时只输出是否存在、数量、布尔状态。

2. **不要绕过 Telegram 私聊限制**
   FinanceBro 处理的是账户和持仓数据。群聊、频道、匿名用户默认拒绝。

3. **不要让 AI 直接碰确定性逻辑**
   IBKR 拉取、XML 解析、风险指标、HTML 渲染、SQLite 写入都应保持纯 Python、可测试、可复现。

4. **新功能先接测试**
   命令、工具、scheduler job、数据库写入、异常路径都要有 focused tests。

5. **优先复用现有边界**
   Bot 层只负责 Telegram；Agent 层只负责推理和工具调用；Storage 层只负责 SQLite；IBKR 层只负责 Flex Query。

6. **控制外部 API 成本**
   Grok 搜索和 Claude 调用都要有明确触发条件。轮询任务默认保守，避免高频自动调用。

### 如何新增 Telegram 命令

1. 在 `bot/handlers.py` 新增 `cmd_xxx(update, context)`
2. 使用 `_is_authorized_private(update)` 做鉴权
3. 长任务包在 `typing_indicator`
4. 阻塞工作用 `asyncio.to_thread`
5. 输出用 `send_html_with_fallback`
6. 在 `bot/telegram_bot.py` 注册 `CommandHandler`
7. 在 `tests/bot/test_commands.py` 覆盖命令行为
8. 更新 README 的命令表

### 如何新增 Orchestrator 工具

1. 在 `agent/tools/` 新增一个模块
2. 定义 `DEFINITION`（参考 `agent/tools/risk_metrics.py` 的结构）
3. 实现 `execute(tool_input) -> str`
4. 在 `agent/tools/__init__.py` 加入 `_TOOLS` 和 `TOOL_DEFINITIONS`
5. 如果需要当前用户，使用 `agent/tools/_state.py` 的 `current_user_id`
6. 给工具写单测（参考 `tests/agent/test_tools_risk_metrics.py`）
7. 确认 Orchestrator 的 tool loop 不会无限调用

### 如何新增 Specialist Agent

1. 先确认是否真的需要新模型调用
   能用 Python 确定性完成的，不要做成 Agent。

2. Specialist Agent 应只做一件事
   例如新闻、风险、财报、历史复盘、税务汇总。

3. Agent 输入应由 Python 预处理
   例如先算好风险指标，再交给模型解释。

4. Agent 输出必须适配 Telegram
   只使用安全 HTML 标签，避免 Markdown 表格、URL 噪音、引用标记污染。

5. 高成本 Agent 默认不要自动轮询
   除非有明确配置开关和去重机制。

### 如何新增 scheduler job

1. 业务逻辑放在 `bot/proactive.py` 或独立模块
2. `bot/scheduler.py` 只负责注册 job
3. 配置默认值尽量写在 `config.py`
4. 如果会主动发 Telegram，**必须**用 `bot.triggers.Trigger` 做冷却 / 去重，状态持久化到 `trigger_fires` 表，重启不丢
5. 失败要记录日志，不要让 job crash 整个 bot
6. 测试 `run_daily` / `run_once` / `run_repeating` 的注册

### 如何改数据库

1. schema 在 `storage/db.py` 的 `_init_schema` executescript 块中
2. 写入逻辑放在 `storage/*`
3. 只读查询用 `db.connect()`，写入用 `db.transaction()`
4. SQLite 连接保留 WAL 和 busy timeout
5. Docker volume 保持 `./data:/app/data`
6. 新表必须补读写测试
7. 不要把 `data/` 或 `.db` 文件打进镜像或提交 Git

### 如何处理 IBKR

1. Flex Query 拉取在 `ibkr/flex_query.py`
2. XML 解析在 `ibkr/parser.py`
3. 不要在异常里暴露带 token 的 URL
4. 解析字段变化时，优先加 parser 测试
5. 空账户报告不应伪装成功

### 如何部署

1. 本地测试通过
2. 提交到 `main`
3. 推送触发 GitHub Actions
4. 用 `gh run watch <run_id> --exit-status` 等待部署完成
5. 部署成功后在 Telegram 私聊测试 `/start`

### 常见坑

- Telegram 输入 `/` 不显示命令列表：这是 BotFather / Bot API command menu 问题，不是 `CommandHandler` 问题。
- 本机 `.env` 不会自动同步到服务器：生产读取服务器 `/opt/financebro/.env`。
- Docker build 失败但 compose config 通过：通常是本机 Docker daemon 没启动。
- 用户显示未授权：检查是否私聊、`TELEGRAM_ALLOWED_USERS` 是否包含 Telegram 数字 user id。
- Grok 返回引用或 URL：输出进入 Telegram 前要清洗或 fallback。
- `trigger_fires` 冷却基于 UTC 时间，确认服务器时区与 `config.py` 时区预期一致。

---

## V2 Roadmap

V2 目标：从"问答式账户助手"升级成"长期投资工作台"，重点是历史、复盘、提醒和决策约束。

| # | Agent | 状态 |
|---|-------|------|
| 1 | Portfolio Historian Agent | ✅ 工具版已完成，可按需升级为 Specialist |
| 2 | Earnings Calendar Agent | 🔜 待开发 |
| 3 | Trade Journal Agent | 🔜 待开发 |
| 4 | Risk Sentinel Agent | 🔜 待开发（Trigger + Drift 基础设施已就绪） |
| 5 | Macro Regime Agent | 🔜 待开发 |
| 6 | Rebalancing Agent | 🔜 待开发 |
| 7 | Watchlist Scout Agent | 🔜 待开发 |
| 8 | Tax & Realized PnL Agent | 🔜 待开发 |

### 1. Portfolio Historian Agent

状态：工具版已完成，后续可升级成更强的 Specialist Agent。

定位：组合历史分析师。

能力：

- 回答过去 7 / 30 / 90 天组合变化
- 对比净值、现金、持仓、仓位、浮盈浮亏
- 找出主要盈亏贡献、加仓 / 减仓痕迹、主题漂移
- 生成周报 / 月报复盘

依赖：

- `portfolio_snapshots`
- `position_snapshots`
- `cash_snapshots`
- `get_portfolio_history` 历史聚合查询工具

### 2. Earnings Calendar Agent

定位：财报日提醒与财报后总结。

能力：

- 根据当前持仓生成本周 / 本月财报日列表
- 财报前提醒高仓位标的
- 财报后总结收入、利润、指引、市场反应
- 接入主动推送（使用 `bot.triggers.Trigger`）

### 3. Trade Journal Agent

定位：交易复盘助手。

能力：

- 记录买入 / 卖出理由
- 回看交易是否符合原计划
- 识别追高、过早止盈、亏损加仓、过度集中等行为
- 生成投资习惯报告

### 4. Risk Sentinel Agent

定位：主动风险哨兵。

能力：

- 将固定阈值升级成智能风险判断
- 结合仓位、集中度、新闻、财报日、宏观事件
- 风险升高时主动提醒
- 基于 `bot.triggers.Trigger` 去重，避免重复打扰

基础设施已就绪：`Trigger` 去重、历史风险指标（VaR / 回撤）、新闻影响打分均可直接复用。

### 5. Macro Regime Agent

定位：宏观环境分析师。

能力：

- 跟踪利率、美元、通胀、就业、央行政策
- 判断当前宏观环境对组合是顺风还是逆风
- 输出每周宏观简报

### 6. Rebalancing Agent

定位：再平衡建议官。

能力：

- 支持目标现金比例、单股上限、行业上限、币种上限
- 检查当前组合偏离
- 给出调整建议
- 默认只建议，不自动交易

### 7. Watchlist Scout Agent

定位：机会侦察员。

能力：

- 维护关注列表
- 监控新闻、财报、价格异动
- 对比 watchlist 与现有持仓
- 生成候选清单

### 8. Tax & Realized PnL Agent

定位：税务与已实现盈亏助手。

能力：

- 汇总已实现盈亏、股息、利息、费用
- 按年度 / 月度生成税务辅助报表
- 为 accountant 准备导出

---

## License

私人项目。默认不建议公开部署给未授权用户使用。
