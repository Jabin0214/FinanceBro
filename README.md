# FinanceBro

FinanceBro 是一个通过 Telegram 使用的私人投资助手，用来分析 Interactive Brokers (IBKR) 账户：实时持仓、HTML 报表、组合风险、历史复盘、观察列表机会侦察、每日快照和开盘前简报。

它采用 **Supervisor + Specialist** 多 Agent 架构：Claude Sonnet 负责对话和工具调度，Grok 专门处理实时新闻与风险分析，IBKR / SQLite / HTML 报表等确定性工作全部由 Python 工具完成。

---

## 当前状态

V1.1 已完成并可部署。接下来不再优先新增 Agent，而是围绕现有核心入口继续打磨：

- Telegram 私聊 Bot，带白名单鉴权
- IBKR Flex Query 拉取持仓
- HTML 持仓报告
- Claude Orchestrator 对话入口
- Grok News Agent
- Grok Risk Analyst Agent
- Portfolio Historian Agent，可回答 7 / 30 / 90 天组合变化并生成复盘
- Watchlist Scout Agent，可维护观察列表并结合当前持仓搜索候选机会
- 投资画像，可记录风险偏好、仓位上限、现金底线和偏好市场
- SQLite 持久化对话历史、原始报表、账户快照、持仓快照、现金快照
- 每日自动快照
- 开盘前简报
- 持仓阈值预警
- 可选实验功能：重大新闻 / 财报提醒轮询
- GitHub Actions 自动部署到 Oracle Cloud VM

产品主线：

- `/brief`：每日状态入口
- `/profile`：个人投资纪律入口
- `/risk`：组合脆弱点入口
- `/history`：历史复盘入口
- `/watchlist` + `/scout`：研究候选入口
- `/report`：无 AI 成本的完整持仓兜底

---

## 用户怎么用

在 Telegram 私聊 Bot 发送命令或自然语言。

| 命令 | 行为 |
|------|------|
| `/start` | 显示帮助 |
| `/report` | 获取 IBKR 持仓 HTML 报告，不走 AI |
| `/risk` | 直接触发 Risk Analyst Agent |
| `/news <关键词>` | 直接触发 News Agent，例如 `/news AAPL earnings` |
| `/brief` | 立即生成一次开盘前简报，包含核心指标、今天只看三件事、主要持仓和风险提醒 |
| `/profile` | 查看投资画像 |
| `/profile set risk conservative max 25 cash 12` | 更新风险偏好、单一持仓上限、现金底线等画像字段 |
| `/history` | 查看最近 30 天组合复盘 |
| `/watchlist` | 查看观察列表 |
| `/watchlist add <代码> <备注>` | 添加或更新观察标的 |
| `/watchlist set <代码> status waiting trigger 175 thesis <逻辑> risk <风险>` | 更新观察标的研究字段 |
| `/watchlist remove <代码>` | 移除观察标的 |
| `/scout` | 运行 Watchlist Scout Agent |
| `/alerts` | 手动检查持仓浮亏 / 集中度阈值，主要用于临时排查 |
| `/clear` | 清除当前 Telegram 用户的对话历史 |

自然语言也可以直接触发工具：

```text
帮我看看现在持仓怎么样
```

```text
这个组合风险高不高？
```

```text
今天 TSLA 有什么新闻？
```

```text
过去 30 天我的组合发生了什么变化？
```

```text
帮我看看观察列表里哪些值得继续跟踪
```

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
- 新闻 / 财报轮询间隔：`180` 分钟，默认关闭，建议只在需要主动监控时开启

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
  - /report /risk /news /brief /profile /alerts /history /watchlist /scout /clear
  - 普通消息转给 Orchestrator
  |
  v
agent/orchestrator.py
  - Claude Sonnet
  - tool-use 主循环
  - history trim
  - token / cost 统计
  |
  +--> agent/tools/portfolio.py  -> IBKR Flex Query
  +--> agent/tools/history.py    -> Portfolio Historian Agent + SQLite 历史快照聚合
  +--> agent/tools/report.py     -> HTML 报告
  +--> agent/tools/news.py       -> Grok web_search + x_search
  +--> agent/tools/risk.py       -> risk_calculator + Grok Risk Analyst
  +--> agent/tools/watchlist.py  -> Watchlist Scout Agent + SQLite 观察列表
  +--> agent/tools/profile.py    -> SQLite 投资画像
```

后台任务：

```text
bot/scheduler.py
  |
  +--> daily_snapshot_job      每日持仓快照
  +--> opening_brief_job       开盘前简报
  +--> threshold_alert_job     持仓阈值预警
  +--> news_monitor_job        重大新闻 / 财报提醒轮询
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
  - portfolio_snapshots
  - position_snapshots
  - cash_snapshots
  - 历史聚合查询

storage/watchlist_store.py
  - watchlist_items
  - per-user 观察列表与研究字段

storage/investor_profile_store.py
  - investor_profiles
  - per-user 风险偏好、仓位上限、现金底线和偏好市场
```

---

## 模型分工

| 任务 | 实现 | 说明 |
|------|------|------|
| 对话 / 工具调度 | `claude-sonnet-4-6` | 负责理解用户意图和调用工具 |
| 新闻搜索 | `grok-4-1-fast-reasoning` | 使用 `web_search` 和 `x_search` |
| 风险分析 | `grok-4-1-fast-reasoning` | 结合风险指标和实时搜索 |
| 历史复盘 | Python + Claude | SQLite 聚合历史快照，Claude 负责解释 |
| 观察列表侦察 | Python + Grok | SQLite 维护 watchlist，Grok 搜索新闻和市场讨论 |
| 报表渲染 | Python | 确定性 HTML 输出 |
| 风险指标 | Python | HHI、集中度、币种敞口、盈亏分布 |
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
│   ├── telegram_bot.py
│   ├── handlers.py
│   ├── auth.py
│   ├── history.py
│   ├── messaging.py
│   ├── proactive.py
│   └── scheduler.py
│
├── agent/
│   ├── orchestrator.py
│   ├── analyzer.py
│   ├── historian.py
│   ├── risk_calculator.py
│   ├── scout.py
│   └── tools/
│       ├── __init__.py
│       ├── _state.py
│       ├── portfolio.py
│       ├── history.py
│       ├── report.py
│       ├── news.py
│       ├── risk.py
│       └── watchlist.py
│
├── ibkr/
│   ├── flex_query.py
│   └── parser.py
│
├── report/
│   └── html_report.py
│
├── storage/
│   ├── db.py
│   ├── memory.py
│   ├── portfolio_store.py
│   └── watchlist_store.py
│
└── tests/
```

---

## 开发阶段

### Phase 1 — 基础报表

状态：完成

- IBKR Flex Query
- XML 解析
- HTML 报告
- Telegram `/report`

### Phase 2 — AI 对话 + 持仓工具

状态：完成

- Claude Orchestrator
- Tool registry
- SQLite 对话历史
- prompt caching
- token / cost footer

### Phase 3 — 新闻 Agent

状态：完成

- Grok News Agent
- `web_search`
- `x_search`
- `/news <关键词>`

### Phase 4 — 风险 Agent

状态：完成

- Python 风险指标
- Grok Risk Analyst
- `/risk`

### Phase 5 — 跨天记忆

状态：完成

- SQLite conversation history
- raw IBKR report 入库
- 账户 / 持仓 / 现金快照
- `/history` 30 天组合复盘摘要

### Phase 6 — 定时任务 + 主动推送

状态：完成

- 每日快照
- 开盘前简报，包含风险提醒
- 阈值预警，可手动检查或随简报查看
- 实验性新闻 / 财报轮询，默认关闭

### Phase 7 — Portfolio Historian Agent

状态：完成

- `get_portfolio_history` Orchestrator 工具
- `agent/historian.py` Specialist Agent，将结构化历史摘要生成中文复盘
- 支持 7 / 30 / 90 天历史窗口
- 对比净值、股票市值、现金、浮盈和成本变化
- 识别开仓、平仓、加仓、减仓
- 汇总主要浮盈浮亏贡献
- `/history` 直接触发 30 天 Portfolio Historian 复盘

### Phase 8 — Watchlist Scout Agent

状态：完成

- `watchlist_items` SQLite 持久化观察列表
- `/watchlist` 查看、添加、更新、移除观察标的
- `/scout` 触发 Watchlist Scout Agent
- `run_watchlist_scout` Orchestrator 工具
- 结合 watchlist、当前持仓、实时新闻和 X 市场讨论生成候选观察
- 对比观察标的与现有持仓的主题重叠和风险相关性

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

常用命令：

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

- “给 FinanceBro 加一个新 Agent”
- “帮我修 Telegram bot”
- “新增一个 slash command”
- “完善 IBKR 持仓历史分析”
- “修部署 / GitHub Actions”
- “检查 V1 上线风险”

### 工作原则

1. 不要泄露 secret
   不打印 `.env` 中的 token、API key、SSH key。检查配置时只输出是否存在、数量、布尔状态。

2. 不要绕过 Telegram 私聊限制
   FinanceBro 处理的是账户和持仓数据。群聊、频道、匿名用户默认拒绝。

3. 不要让 AI 直接碰确定性逻辑
   IBKR 拉取、XML 解析、风险指标、HTML 渲染、SQLite 写入都应保持纯 Python、可测试、可复现。

4. 新功能先接测试
   命令、工具、scheduler job、数据库写入、异常路径都要有 focused tests。

5. 优先复用现有边界
   Bot 层只负责 Telegram；Agent 层只负责推理和工具调用；Storage 层只负责 SQLite；IBKR 层只负责 Flex Query。

6. 控制外部 API 成本
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
2. 定义 `DEFINITION`
3. 实现 `execute(tool_input) -> str`
4. 在 `agent/tools/__init__.py` 加入 `_TOOLS` 和 `TOOL_DEFINITIONS`
5. 如果需要当前用户，使用 `agent/tools/_state.py` 的 `current_user_id`
6. 给工具写单测
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
4. 如果会主动发 Telegram，要做去重或冷却
5. 失败要记录日志，不要让 job crash 整个 bot
6. 测试 `run_daily` / `run_once` / `run_repeating` 的注册

### 如何改数据库

1. schema 在 `storage/db.py`
2. 写入逻辑放在 `storage/*`
3. 使用事务
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

---

## 产品收敛方向

FinanceBro 现在进入收敛阶段：不继续堆新 Agent，不追求覆盖所有投资场景，而是把已经完成的能力打磨得更可靠、更少打扰、更适合每天使用。

核心原则：

- 日常入口少一点：优先让 `/brief`、`/risk`、`/history`、`/watchlist`、`/scout` 这几条路径足够好。
- 确定性逻辑更强：IBKR 拉取、历史聚合、风险指标、watchlist 存储继续保持 Python 可测试实现。
- AI 只做解释和归纳：模型负责把结构化数据讲清楚，不负责生成账务事实或替代数据库查询。
- 主动推送保守：默认只保留每日快照、开盘简报和阈值提醒；新闻轮询仍是实验功能，避免噪音和成本失控。
- 不新增自动交易：所有输出只做复盘、观察、提醒和研究建议。

### 当前核心能力

1. 开盘前简报

目标：每天一眼看清组合状态。

强化方向：

- 让 `/brief` 更像每日仪表盘，突出净值、浮盈亏、集中度、主要持仓和触发风险。
- 减少重复文字，把“今天只看三件事”放在最前面，并按 `/profile` 的现金底线和单一持仓上限判断是否需要行动。
- 后续可加入“相比上一快照变化”，但仍复用现有历史快照，不新建 Agent。

2. 风险分析

目标：回答“这个组合现在哪里最脆弱”。

强化方向：

- 让 `/risk` 更稳定地区分集中度、主题相关性、币种敞口、浮亏压力。
- 将 Grok 搜索结果限制在主要持仓和关键宏观变量，避免泛泛市场新闻。
- 后续优先增强风险指标本身，而不是新增 Risk Sentinel Agent。

3. Portfolio Historian

目标：把历史快照变成真正的复盘。

强化方向：

- 强化 7 / 30 / 90 天复盘质量，解释净值、现金、仓位和浮盈亏变化。
- 更清楚地区分“市场价格导致的市值变化”和“用户主动加仓 / 减仓”。
- 后续可增强交易归因和主题漂移识别，但继续依赖 `portfolio_snapshots`、`position_snapshots`、`cash_snapshots`。

4. Watchlist Scout

目标：让观察列表服务于研究，而不是变成另一个新闻流。

强化方向：

- `/watchlist` 保持轻量，只维护标的和备注。
- `/watchlist` 可额外维护状态、关注逻辑、触发价和风险点。
- `/scout` 聚焦候选观察、与现有持仓关系、近期催化和下一步研究动作，并把观察标的的研究字段传给模型。
- 后续可增强价格异动和财报窗口提醒，但默认不做高频主动推送。

5. HTML 报表

目标：保留一个稳定、无 AI 成本的完整持仓视图。

强化方向：

- `/report` 继续作为确定性兜底入口。
- 报表只做清晰展示，不承载复杂交互或额外 AI 解读。

### 暂缓开发

以下方向先不做独立 Agent，除非现有核心能力已经明显不够用：

- Earnings Calendar Agent
- Trade Journal Agent
- Macro Regime Agent
- Rebalancing Agent
- Tax & Realized PnL Agent

如果未来确实要加入，也优先作为现有能力的增强项，例如把财报日作为 `/brief` 或 `/scout` 的一个字段，而不是再开一个新入口。

---

## License

私人项目。默认不建议公开部署给未授权用户使用。
