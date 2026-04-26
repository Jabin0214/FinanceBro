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

- [x] 新增 IB Gateway 实时账户快照工具：总净值、可用现金、当前股票持仓、数量、平均成本
- [ ] 接入 IBKR TWS / IB Gateway（优先 `ib_insync`）
- [ ] 新增 `get_option_chain` 工具：按股票代码返回到期日、行权价、bid/ask、delta、IV、OI、volume
- [ ] 新增 `scan_short_put_candidates` 工具：面向 `cash-secured put`
- [ ] 新增 `scan_covered_call_candidates` 工具：面向 `covered call`
- [ ] 支持自然语言触发：如“帮我看看 AAPL 能卖哪些 put / call”
- [ ] 输出中明确区分“数据事实”和“策略建议”，避免把建议包装成确定结论
- [ ] 对缺失字段做降级处理：无 Greeks / 无 IV 时仍可返回基础报价，但提示数据不完整

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
- Iteration 0：打通实时账户快照读取，返回净值、可用现金、股票持仓数量和平均成本
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
- [ ] 评估卖 put 所需现金占用、卖 covered call 对现有仓位的影响（待 Phase 4 期权数据打通后补充）
- [ ] 为期权建议增加账户级限制：现金充足度、单标的上限、到期日分散度（同上）

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
│   └── formatter.py        # Telegram 文本格式化
│
├── agent/                  # AI 层
│   ├── tools.py            # 工具注册表（含报表/新闻/期权扫描工具）
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
```

### Realtime Account Snapshot

通过 IB Gateway 可读取实时账户快照，包含：

- 总净值
- 可用现金
- 当前股票持仓
- 持仓数量
- 平均成本

该能力用于实时账户状态查询，不替代 Flex Query 报表。

### Oracle 上运行 IB Gateway

推荐生产形态：

- `ib-gateway` 跑在 Oracle 的 Docker 容器里，由 `gnzsnz/ib-gateway:stable` 提供 IB Gateway + IBC。
- `FinanceBro` 通过 Docker 内网连接 `ib-gateway:4002`（paper）或 `ib-gateway:4001`（live）。
- `READ_ONLY_API=yes`，Gateway 侧限制 API 只读；FinanceBro 当前实时账户快照工具也只读取账户和持仓，不下单。
- `AUTO_RESTART_TIME=03:45 AM`，IBC 每日自动重启 Gateway。
- 每周人工做一次 IBKR 2FA 登录/确认；VNC 端口只绑定 Oracle 本机，需要通过 SSH tunnel 访问。

在 Oracle `/opt/financebro/.env` 中开启：

```bash
COMPOSE_PROFILES=ibkr
IBKR_TWS_HOST=ib-gateway
IBKR_TWS_PORT=4002
IBKR_TWS_CLIENT_ID=10

TWS_USERID=your_ibkr_username
TWS_PASSWORD=your_ibkr_password
TRADING_MODE=paper
READ_ONLY_API=yes
TWOFA_TIMEOUT_ACTION=restart
AUTO_RESTART_TIME=03:45 AM
RELOGIN_AFTER_TWOFA_TIMEOUT=no
IB_GATEWAY_TIME_ZONE=America/New_York
VNC_SERVER_PASSWORD=use-a-strong-password
```

启动或更新：

```bash
cd /opt/financebro
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 ib-gateway
```

首次登录和每周 2FA：

```bash
ssh -i /Users/jabin/Downloads/ssh-key-2026-04-22.key \
  -L 5900:127.0.0.1:5900 \
  ubuntu@159.13.46.242
```

保持 SSH tunnel 打开，然后用本机 VNC Viewer 连接 `127.0.0.1:5900`，输入 `VNC_SERVER_PASSWORD`，完成 IBKR 登录和手机 2FA。

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
