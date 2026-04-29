# FinanceBro

通过 Telegram 与 AI 对话来分析 Interactive Brokers (IBKR) 账户：实时持仓、市场新闻、组合风险评估。

采用 **Supervisor + Specialist** 多 Agent 架构：Claude Sonnet 主导对话与调度，按需把工作分派给两个 Grok 专业 Agent（新闻 / 风险）和一组确定性数据工具。

---

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│  User  (Telegram)                                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│  Bot Layer  ·  bot/telegram_bot.py                               │
│  白名单鉴权 · 命令路由 · per-user 对话历史 · 文件回传            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ chat(history, text)
┌───────────────────────────▼─────────────────────────────────────┐
│  Orchestrator Agent  ·  Claude Sonnet 4.6                        │
│  agent/orchestrator.py                                           │
│  对话主循环 · 工具调度 · 滑窗历史 · prompt caching               │
└──────┬──────────────┬───────────────┬────────────────┬──────────┘
       │ tool         │ tool          │ tool           │ tool
       ▼              ▼               ▼                ▼
 ┌──────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐
 │ Data     │  │ Report       │  │ News Agent  │  │ Risk Analyst   │
 │ Tool     │  │ Tool         │  │             │  │ Agent          │
 │          │  │              │  │   Grok      │  │   Grok         │
 │get_      │  │generate_     │  │ +web_search │  │ +web_search    │
 │portfolio │  │report        │  │ +x_search   │  │ +x_search      │
 │(纯数据)  │  │(数据→HTML)   │  │             │  │                │
 └────┬─────┘  └──────┬───────┘  └─────────────┘  └────────┬───────┘
      │               │                                     │ metrics
      ▼               ▼                                     ▼
 ┌──────────────────────────────┐                  ┌────────────────┐
 │ IBKR Flex Query              │                  │ risk_calculator│
 │ ibkr/flex_query + parser     │                  │ (纯 Python)    │
 │ XML → 结构化持仓 · 10min缓存 │                  │ HHI / 集中度等 │
 └──────────────────────────────┘                  └────────────────┘
```

**分层原则**

- **Bot 层**：只做传输、鉴权、会话状态。不懂业务。
- **Orchestrator**：唯一的对话入口；不直接处理数据，全部通过工具。
- **Specialist Agent**：每个独立完成一件事，自带实时搜索能力。
- **确定性层**：拉取、解析、计算、渲染——纯 Python，无 AI，可缓存、可单测。

---

## 模型分工

| 任务 | 模型 | 理由 |
|------|------|------|
| 对话 / 工具调度 | `claude-sonnet-4-6` | 工具调用稳定，成本可控 |
| 新闻搜索 | `grok-4-1-fast-reasoning` | 原生 `web_search` + `x_search`，时效性强 |
| 风险分析 | `grok-4-1-fast-reasoning` | 实时搜索 + 推理，结合宏观环境判断 |
| 报表 / 风险指标 | 纯 Python | 确定性输出，零 AI 成本 |

**Sonnet 4.6 计价**：$3.00 / 1M input · $15.00 / 1M output · 缓存读取 $0.30 / 1M。每次回复后会显示当次 token 用量与美元开销。

---

## 命令

| 命令 | 行为 |
|------|------|
| `/start` | 显示帮助 |
| `/report` | 直接获取 IBKR 持仓 HTML 报告（不走 AI，省 token）|
| `/clear` | 清除当前对话历史（SQLite 持久化记录） |
| 普通文字消息 | 进入 Orchestrator 对话；持仓、新闻、风险等问题会自动调用对应工具 |

---

## 30 秒上手

```bash
git clone https://github.com/Jabin0214/FinanceBro.git
cd FinanceBro
cp .env.example .env       # 填入 token，见下方环境变量
docker compose up -d --build
docker compose logs -f
```

确认日志出现 `🤖 FinanceBro 启动中...` 后，去 Telegram 给你的 Bot 发任意消息即可。

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram BotFather 给的 Token |
| `TELEGRAM_ALLOWED_USERS` | 允许访问的用户 ID（逗号分隔）|
| `TELEGRAM_ALLOW_ALL` | 显式允许所有 Telegram 用户访问（默认 `false`，仅建议本地测试使用）|
| `IBKR_FLEX_TOKEN` | IBKR Flex Web Service Token |
| `IBKR_FLEX_QUERY_ID` | Flex Query ID（在 IBKR 后台创建）|
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `GROK_API_KEY` | xAI Grok API Key（[console.x.ai](https://console.x.ai)）|
| `DAILY_SNAPSHOT_ENABLED` | 是否启用每日自动持仓快照（`true`/`false`；未设置时如有白名单用户则默认启用）|
| `DAILY_SNAPSHOT_USER_ID` | 自动快照归属的 Telegram 用户 ID；未设置时使用 `TELEGRAM_ALLOWED_USERS` 第一个用户 |
| `DAILY_SNAPSHOT_TIME` | 每日快照时间，24 小时制 `HH:MM`，默认 `07:00` |
| `DAILY_SNAPSHOT_TIMEZONE` | 每日快照时区，默认 `Pacific/Auckland` |
| `DAILY_SNAPSHOT_NOTIFY` | 自动快照成功/失败后是否 Telegram 通知，默认 `true` |
| `PROACTIVE_BRIEF_ENABLED` | 是否启用每日开盘前简报；默认跟随 `DAILY_SNAPSHOT_ENABLED` |
| `PROACTIVE_BRIEF_USER_ID` | 开盘前简报接收人；默认跟随自动快照用户 |
| `PROACTIVE_BRIEF_TIME` | 开盘前简报时间，默认 `08:30` |
| `PROACTIVE_BRIEF_TIMEZONE` | 开盘前简报时区，默认跟随每日快照时区 |
| `PROACTIVE_ALERT_ENABLED` | 是否启用持仓阈值预警；默认跟随 `DAILY_SNAPSHOT_ENABLED` |
| `PROACTIVE_ALERT_USER_ID` | 阈值预警接收人；默认跟随自动快照用户 |
| `PROACTIVE_ALERT_TIME` | 阈值预警检查时间，默认 `08:35` |
| `PROACTIVE_ALERT_PNL_PCT` | 整体浮亏触发阈值，默认 `-5` |
| `PROACTIVE_ALERT_POSITION_WEIGHT_PCT` | 单一持仓集中度触发阈值，默认 `35` |
| `PROACTIVE_NEWS_ENABLED` | 是否启用重大新闻 / 财报提醒轮询，默认 `false` |
| `PROACTIVE_NEWS_USER_ID` | 新闻 / 财报提醒接收人；默认跟随自动快照用户 |
| `PROACTIVE_NEWS_INTERVAL_MINUTES` | 新闻 / 财报提醒轮询间隔，默认 `180` |

---

## 目录结构

```
FinanceBro/
├── main.py                 # 入口：启动 Telegram polling
├── config.py               # 环境变量 + 模型 ID
├── requirements.txt
├── Dockerfile / docker-compose.yml
│
├── bot/                    # Telegram 传输层
│   ├── telegram_bot.py     # Application 装配（仅路由表）
│   ├── handlers.py         # /start /report /clear + 普通消息 handler
│   ├── auth.py             # 白名单
│   ├── history.py          # per-user 对话历史（SQLite 持久化）
│   ├── proactive.py        # Phase 6 开盘简报 / 新闻提醒 / 阈值预警
│   └── messaging.py        # 长消息切分 / HTML 降级 / typing 心跳
│
├── agent/                  # AI 层
│   ├── orchestrator.py     # Supervisor: Sonnet tool-use 主循环
│   ├── tools/              # 工具注册表（每个工具一个文件）
│   │   ├── __init__.py     # TOOL_DEFINITIONS 聚合 + execute_tool 分派
│   │   ├── portfolio.py    # get_portfolio + per-user 10min 缓存
│   │   ├── report.py       # generate_report
│   │   ├── news.py         # get_news（News Specialist Agent）
│   │   ├── risk.py         # get_risk_analysis（Risk Analyst Agent）
│   │   └── _state.py       # active_user / pending_files
│   ├── analyzer.py         # Risk Analyst 实现（Grok 调用）
│   └── risk_calculator.py  # 风险指标（HHI、集中度、币种敞口）
│
├── ibkr/
│   ├── flex_query.py       # Flex Web Service 拉取
│   └── parser.py           # XML → 结构化持仓
│
└── report/
    └── html_report.py      # HTML 报表渲染（纯 Python，深色主题）
```

---

## 开发阶段

### Phase 1 — 基础报表 ✅
- IBKR Flex Query 连接，XML 解析（多账户、多币种、汇率折算）
- 纯 Python 生成深色主题 HTML 报告
- Telegram `/report` 命令

### Phase 2 — AI 对话 + 持仓工具 ✅
- 工具注册表（可扩展）+ Sonnet tool use 主循环
- per-user 对话历史（SQLite 持久化），滑动窗口 `MAX_HISTORY=20`
- 裁剪时确保从普通 user 文本开始，避免破坏 `tool_use`/`tool_result` 配对
- prompt caching（system prompt + 工具定义），每次回复显示 token 与费用
- HTML 解析失败自动降级为纯文本

### Phase 3 — 新闻 Agent ✅
- News Agent：Grok `grok-4-1-fast-reasoning` + `web_search` + `x_search`
- `get_news` 工具，自然语言触发；5 分钟缓存避免重复调用
- Sonnet 对返回内容做利好/利空/中性解读

### Phase 4 — 风险 Agent ✅
- Risk Analyst Agent：先用 `risk_calculator` 算出结构化指标（HHI、集中度、币种敞口、盈亏分布），再交给 Grok 结合实时搜索给出建议
- 自然语言触发 `get_risk_analysis` 工具（用户问"风险/集中度/健康度"等会自动调）

### Phase 5 — 跨天记忆 ✅
- SQLite 持久化对话历史，容器重建后保留
- `/report` 拉取 IBKR 报表时保存每日账户 / 持仓 / 现金快照
- 可配置每日自动从 IBKR 拉取持仓并保存快照
- 提供基础历史查询接口，供后续 AI 历史分析工具使用
- 原始结构化报表 JSON 入库，方便未来重算历史
- 超长历史用 Sonnet 生成日摘要，作为 system prompt 背景（后续）

### Phase 6 — 定时任务 + 主动推送 ✅
- 每日开盘前简报：拉取最新 IBKR 持仓、保存快照、推送净值 / 盈亏 / 集中度 / 主要持仓
- 持仓盈亏阈值预警：按整体浮亏和单一持仓占比阈值主动提醒
- 重大新闻 / 财报提醒：按主要持仓定时轮询 Grok 搜索并推送摘要（默认关闭，避免成本失控）

---

## 部署

生产环境部署到 Oracle Cloud VM（Ubuntu 24.04，应用目录 `/opt/financebro`），由 GitHub Actions 在 `main` 分支收到推送后自动 `docker compose up -d --build`。

```bash
git push origin main    # GitHub Actions 自动部署到 Oracle VM
```

### GitHub Actions Secrets

`ORACLE_HOST` · `ORACLE_HOST_KEY` · `ORACLE_PORT` · `ORACLE_SSH_KEY` · `ORACLE_USER`

### 首次服务器初始化

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
newgrp docker

sudo mkdir -p /opt/financebro
sudo chown "$USER":"$USER" /opt/financebro
git clone https://github.com/Jabin0214/FinanceBro.git /opt/financebro
cd /opt/financebro
cp .env.example .env       # 填入真实 token
docker compose up -d --build
```

### 手动兜底部署

自动部署失败时，先看 GitHub Actions 日志和 VM 上的容器状态，再手动同步：

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
