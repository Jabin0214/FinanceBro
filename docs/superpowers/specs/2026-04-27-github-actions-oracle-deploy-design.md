# GitHub Actions Oracle Auto-Deploy Design

## Goal

在 `main` 分支收到新的 `push` 后，自动将 `FinanceBro` 部署到 Oracle Cloud VM，替代当前手动 SSH 登录并执行更新命令的流程。

## Current State

- Oracle VM 已可通过 SSH 访问：`ubuntu@159.13.46.242`
- 服务器部署目录已经切换为 git clone：`/opt/financebro`
- 当前手动部署命令已验证可用：

```bash
cd /opt/financebro
git pull --ff-only
docker compose up -d --build
docker compose logs --tail=50
```

- 运行中的服务为 Docker Compose 管理的 `financebro` 容器
- 服务器本地保留文件包括：
  - `.env`
  - `docker-compose.yml`
  - `docs/DEPLOY_ORACLE.md`

## Recommended Approach

采用 GitHub Actions 通过 SSH 登录 Oracle VM，并在服务器上执行既有部署命令。

触发链路：

1. 本地提交并 `git push origin main`
2. GitHub Actions 在 `main` 分支 `push` 事件触发
3. Workflow 使用部署专用 SSH 私钥连接 Oracle VM
4. Workflow 在服务器上执行：
   - `cd /opt/financebro`
   - `git pull --ff-only`
   - `docker compose up -d --build`
   - `docker compose ps`
   - `docker compose logs --tail=50`
5. Workflow 根据命令退出码判断部署成功或失败

## Why This Approach

相比镜像仓库发布或再次回到 `rsync` 方案，这个方案最适合当前仓库状态：

- 复用已经验证通过的服务器部署路径
- 不需要额外引入容器镜像仓库
- 不需要改变服务器上的运行模型
- 故障定位简单，GitHub Actions 日志和服务器日志都可直接查看
- 后续可平滑升级到“构建镜像并拉取”的更重型方案

## Files And Responsibilities

### New Files

- `.github/workflows/deploy-oracle.yml`
  - 定义 `push` 到 `main` 时的自动部署流程
  - 负责检出代码、准备 SSH、执行远端部署命令

### Existing Files Touched

- `README.md`
  - 增加简短的发布说明，告诉维护者部署改为 GitHub Actions 自动执行

- `docs/DEPLOY_ORACLE.md`
  - 增加“自动部署”小节，记录 GitHub Secrets、触发方式和故障排查命令

### Out-Of-Band Configuration

以下配置不进入 git 仓库，但属于此设计的一部分：

- GitHub repository secrets
  - `ORACLE_HOST`
  - `ORACLE_USER`
  - `ORACLE_SSH_KEY`
  - 可选：`ORACLE_PORT`

- Oracle VM 用户 `ubuntu` 的 `~/.ssh/authorized_keys`
  - 增加一把专门给 GitHub Actions 使用的部署公钥

## Security Model

为自动部署单独生成一套 SSH key，而不是复用你本地电脑当前那把私钥。

原因：

- 可以把“本地开发登录”和“CI 自动部署”权限拆开
- 将来如果需要停用自动部署，只撤销部署公钥即可
- GitHub Secrets 中不必保存你日常手工登录用的私钥

约束：

- 私钥只保存在 GitHub Secrets
- 公钥只加入 Oracle VM 的 `ubuntu` 用户 `authorized_keys`
- Workflow 只使用这把 key 执行部署命令

## Deployment Workflow Design

Workflow 分为 4 个逻辑阶段：

### 1. Trigger

- 事件：`push`
- 分支：`main`

### 2. Prepare SSH

- 从 GitHub Secrets 读取部署私钥
- 写入 runner 临时文件
- 设置 `chmod 600`
- 预写 `known_hosts`，避免交互式 host verification

### 3. Deploy Remotely

在 Oracle VM 上执行：

```bash
cd /opt/financebro
git pull --ff-only
docker compose up -d --build
```

### 4. Health Check

在 Oracle VM 上继续执行：

```bash
docker compose ps
docker inspect financebro --format 'status={{.State.Status}} running={{.State.Running}} restart={{.RestartCount}}'
docker compose logs --tail=50
```

成功标准：

- `git pull --ff-only` 成功
- `docker compose up -d --build` 成功
- `financebro` 容器状态为 `running=true`

## Failure Handling

如果部署失败，GitHub Actions job 必须失败并保留完整日志，不尝试自动回滚。

选择不自动回滚的原因：

- 当前项目部署规模较小，人工判断更安全
- 自动回滚需要额外状态管理，容易掩盖真实问题
- 先让失败透明化，排查成本最低

人工回退路径：

1. 查看 GitHub Actions 日志
2. SSH 登录 Oracle VM
3. 在 `/opt/financebro` 手动检查：
   - `git log --oneline -n 5`
   - `docker compose ps`
   - `docker compose logs --tail=100`
4. 如需回退，再手动切回旧 commit 并重新 `docker compose up -d --build`

## Testing Plan

上线前验证分为三层：

1. 配置验证
   - 确认 GitHub Secrets 已写入
   - 确认 Oracle VM 的 `authorized_keys` 已加入部署公钥

2. Workflow 验证
   - 提交一个小变更到 `main`
   - 观察 GitHub Actions 是否自动触发
   - 确认 job 成功结束

3. Runtime 验证
   - 确认 Oracle VM 上 `financebro` 容器仍为 `Up`
   - 确认日志中出现 `Application started`
   - 确认日志持续出现 `getUpdates "HTTP/1.1 200 OK"`

## Non-Goals

本次不做以下内容：

- 不引入 Docker Hub 或 GHCR 镜像发布流程
- 不引入蓝绿部署或自动回滚
- 不将 `.env` 改为 GitHub 下发到服务器
- 不变更应用运行模式，仍保持 Docker Compose + polling bot

## Rollout Plan

1. 生成部署专用 SSH key
2. 将公钥加入 Oracle VM 的 `authorized_keys`
3. 在 GitHub 仓库中配置所需 Secrets
4. 提交 workflow 文件与文档更新
5. 推送到 `main`
6. 观察首次自动部署结果
