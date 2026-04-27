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

### Phase 4 — 风险分析 ✅
**目标**：对整体仓位做深度风险评估

- [x] 新增 `get_risk_analysis` 工具（Claude 对话可触发，`/risk` 命令直接调用）
- [x] 集中度分析（单标的占比、HHI 指数）、币种敞口、资产类别分布、盈亏分布
- [x] `agent/risk_calculator.py`：纯 Python 指标计算（权重以多头总市值为分母；多币种统一用 `cost_basis_base`）
- [x] `agent/analyzer.py`：Grok 分析引擎（`web_search` + `x_search` 实时搜索，结合当前市场动态输出风险报告）
- [x] Telegram `/risk` 命令

**模型**：Grok `grok-4-1-fast-reasoning`（实时搜索 + 深度分析，替代原计划的 Opus，兼具时效性和推理能力）

### Phase 5 — 跨天记忆
**目标**：对话历史持久化，重启不丢失

- [ ] 历史序列化存储（SQLite 或 JSON 文件）
- [ ] 超长历史摘要压缩（调用 Sonnet 生成日摘要，作为 system prompt 背景）

### Phase 6 — 定时任务 + 主动推送
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
│
├── report/                 # 报告输出层（纯 Python，不含 AI）
│   └── html_report.py      # HTML 报告生成
│
├── agent/                  # AI 层
│   ├── tools.py            # 工具注册表（报表/新闻/风险分析）
│   ├── orchestrator.py     # Sonnet 对话引擎（tool use 循环）
│   ├── analyzer.py         # Phase 5: Grok 风险分析引擎
│   └── risk_calculator.py  # Phase 5: 纯 Python 风险指标计算
│
├── bot/
│   ├── telegram_bot.py     # Bot 主逻辑（命令 + 消息处理）
│   └── keyboards.py        # Phase 7: 确认按钮
│
└── scheduler/
    └── tasks.py            # Phase 8: 定时任务
```

---

## 模型分工

| 任务 | 模型 | 理由 |
|------|------|------|
| 对话 / 工具调度 | claude-sonnet-4-6 | 够用，省钱 |
| 数据格式化 / HTML 生成 | 纯 Python | 确定性输出，无需 AI |
| 新闻搜索（实时） | grok-4-1-fast-reasoning | X/web 实时数据源 |
| 风险分析 | grok-4-1-fast-reasoning | 深度推理 + 实时搜索，兼具时效性 |

---

## 环境变量

```
TELEGRAM_BOT_TOKEN       Telegram Bot Token
TELEGRAM_ALLOWED_USERS   允许访问的用户 ID（逗号分隔）
IBKR_FLEX_TOKEN          IBKR Flex Web Service Token
IBKR_FLEX_QUERY_ID       Flex Query ID（在 IBKR 后台配置）
ANTHROPIC_API_KEY        Anthropic API Key
GROK_API_KEY             xAI Grok API Key（console.x.ai）
```

## 部署

生产环境部署到 Oracle Cloud VM（Ubuntu 24.04，应用目录 `/opt/financebro`，运行方式 `docker compose up -d`），默认由 GitHub Actions 在 `main` 分支收到新提交后自动执行。

日常发布流程：

```bash
git add .
git commit -m "your change"
git push origin main
```

推送完成后，GitHub Actions 会连接 Oracle VM，在 `/opt/financebro` 上部署这次提交对应的精确 commit，并重建 `financebro` 容器。

### GitHub Actions Secrets

- `ORACLE_HOST`
- `ORACLE_HOST_KEY`
- `ORACLE_PORT`
- `ORACLE_SSH_KEY`
- `ORACLE_USER`

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
cp .env.example .env
# edit .env with your real tokens before starting
docker compose up -d --build
```

### 手动兜底部署

自动部署失败时，先看 GitHub Actions 日志和 VM 上的容器状态，再用以下命令手动同步：

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
