# Oracle Cloud VM Deployment

## Recommended Layout

- VM OS: Ubuntu 24.04
- App directory: `/opt/financebro`
- Runtime: Docker Engine + Docker Compose plugin
- Process model: `docker compose up -d`

## One-Time Server Setup

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
```

## Deploy

```bash
sudo mkdir -p /opt/financebro
sudo chown "$USER":"$USER" /opt/financebro
git clone https://github.com/Jabin0214/FinanceBro.git /opt/financebro
cd /opt/financebro
cp .env.example .env
# edit .env with your real tokens before starting
docker compose up -d --build
docker compose logs -f --tail=100
```

## Upgrade

```bash
cd /opt/financebro
git fetch origin main
git checkout main
git reset --hard origin/main
docker compose up -d --build
```

## GitHub Actions Auto-Deploy

自动部署触发条件：

- `push` 到 `main`

所需 GitHub Actions Secrets：

- `ORACLE_HOST`
- `ORACLE_HOST_KEY`
- `ORACLE_PORT`
- `ORACLE_SSH_KEY`
- `ORACLE_USER`

Workflow 在 Oracle VM 上执行的核心命令：

```bash
cd /opt/financebro
git fetch --depth=1 origin "$DEPLOY_SHA"
git checkout main
git reset --hard "$DEPLOY_SHA"
docker compose up -d --build
docker compose ps
docker compose logs --tail=50
```

如果自动部署失败，优先排查：

1. GitHub Actions 最近一次 workflow 日志
2. Oracle VM 上的仓库状态和容器状态

手动兜底命令：

```bash
ssh -i /Users/jabin/Downloads/ssh-key-2026-04-22.key ubuntu@159.13.46.242 '
cd /opt/financebro &&
git fetch origin main &&
git checkout main &&
git reset --hard origin/main &&
docker compose up -d --build &&
docker compose ps &&
docker compose logs --tail=50
'
```

## Useful Checks

```bash
docker compose ps
docker compose logs --tail=100
docker inspect financebro --format '{{.State.Status}}'
```
