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
| `IBKR_FLEX_TOKEN` | IBKR Flex Web Service Token |
| `IBKR_FLEX_QUERY_ID` | Flex Query ID（在 IBKR 后台创建）|
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `GROK_API_KEY` | xAI Grok API Key（[console.x.ai](https://console.x.ai)）|
| `PROACTIVE_NEWS_ENABLED` | 是否启用重大新闻 / 财报提醒轮询，默认 `false` |

固定产品默认值写在 `config.py`：自动快照 `07:00`、开盘前简报 `08:30`、阈值预警 `08:35`，时区均为 `Pacific/Auckland`；主动推送接收人使用 `TELEGRAM_ALLOWED_USERS` 的第一个用户；整体浮亏阈值为 `-5%`，单一持仓集中度阈值为 `35%`。

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

## V2 Roadmap

V2 的方向是从“问答式账户助手”升级为“长期投资工作台”：更重视历史、复盘、提醒和决策约束。下面是候选 Agent，按优先级排列。

### 1. Portfolio Historian Agent

定位：组合历史分析师，优先级最高。

能力：
- 基于 SQLite 快照回答“过去 7 / 30 / 90 天组合发生了什么变化”
- 对比净值、现金、持仓、仓位、浮盈浮亏的历史变化
- 找出主要盈亏贡献、加仓 / 减仓痕迹、组合主题漂移
- 生成周报 / 月报复盘

依赖：
- 现有 `portfolio_snapshots`、`position_snapshots`、`cash_snapshots`
- 需要新增历史聚合查询工具，例如 `get_portfolio_history`、`get_position_changes`

### 2. Earnings Calendar Agent

定位：财报日提醒与财报后总结。

能力：
- 根据当前持仓生成本周 / 本月财报日列表
- 财报前提醒高仓位标的和潜在波动风险
- 财报后总结收入、利润、指引、盘后反应和对持仓的影响
- 接入 Phase 6 主动推送，在财报前自动提醒

依赖：
- 财报日数据源或搜索能力
- 当前持仓权重，用来判断提醒优先级

### 3. Trade Journal Agent

定位：交易复盘助手。

能力：
- 记录买入 / 卖出理由、预期、风险点和复盘日期
- 回看交易是否符合原计划
- 识别行为模式：追高、过早止盈、亏损加仓、过度集中等
- 生成个人投资习惯报告

依赖：
- 新增交易日志表
- 可选接入 IBKR 交易记录；V2 初期可以先让用户手动记录

### 4. Risk Sentinel Agent

定位：主动风险哨兵。

能力：
- 把当前阈值预警升级成更智能的组合风险判断
- 结合仓位、集中度、个股新闻、财报日、宏观事件判断风险等级
- 在风险升高时主动提醒，而不是等用户发问
- 跟踪同一风险是否已提醒，避免重复打扰

依赖：
- Phase 6 阈值预警
- News Agent / Risk Analyst Agent
- 风险事件去重和冷却时间机制

### 5. Macro Regime Agent

定位：宏观环境分析师。

能力：
- 跟踪利率、美元、通胀、就业、央行政策等宏观变量
- 判断当前宏观环境对组合是顺风还是逆风
- 每周输出宏观简报，并映射到当前持仓主题
- 解释“为什么这周科技股 / 港股 / 汇率影响了我的组合”

依赖：
- Grok 实时搜索
- 组合行业 / 币种 / 主题归因

### 6. Rebalancing Agent

定位：再平衡建议官。

能力：
- 支持用户设置目标约束：现金比例、单股上限、行业上限、币种上限
- 定期检查当前组合与目标组合的偏离
- 给出“需要减 / 加什么，减 / 加多少”的建议
- 默认只做建议，不自动交易

依赖：
- 用户偏好配置表
- 当前持仓与历史风险指标

### 7. Watchlist Scout Agent

定位：机会侦察员。

能力：
- 维护关注列表
- 监控 watchlist 的新闻、财报、价格异动和估值变化
- 对比 watchlist 与现有持仓，提醒潜在替代机会
- 生成“本周值得关注”的候选清单

依赖：
- Watchlist 存储
- 新闻 / 财报 / 市场数据源

### 8. Tax & Realized PnL Agent

定位：税务与已实现盈亏助手。

能力：
- 汇总已实现盈亏、股息、利息、费用
- 按年度 / 月度生成税务辅助报表
- 给 accountant 准备结构化导出

依赖：
- IBKR Flex Query 增加交易记录、已实现盈亏、股息和费用字段
- 新增税务报表渲染

### 推荐 V2 顺序

1. Portfolio Historian Agent：直接复用现有快照数据，投入产出最高。
2. Earnings Calendar Agent：和主动推送天然结合，用户感知强。
3. Trade Journal Agent：让 FinanceBro 从查数据升级为投资复盘工具。
4. Risk Sentinel Agent：把现有风险分析升级成主动守门员。

V2 的产品目标：FinanceBro 不只回答“我现在怎么样”，还要告诉用户“我的组合正在怎么变化，我的投资行为正在形成什么模式”。

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
