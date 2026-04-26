# GitHub Actions Oracle Auto-Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable automatic deployment to the Oracle VM whenever code is pushed to the `main` branch.

**Architecture:** GitHub Actions listens for `push` events on `main`, prepares a deployment-only SSH identity from repository secrets, and runs the already-verified remote deployment commands on `/opt/financebro`. The Oracle VM remains the runtime host and keeps server-local files such as `.env`, while GitHub becomes the deployment trigger.

**Tech Stack:** GitHub Actions, OpenSSH, Docker Compose, Git, Ubuntu 24.04 on Oracle Cloud

---

## File Structure

- Create: `.github/workflows/deploy-oracle.yml`
  - GitHub Actions workflow that deploys on `push` to `main`
- Modify: `README.md`
  - Brief release workflow for maintainers
- Modify: `docs/DEPLOY_ORACLE.md`
  - Auto-deploy setup, secrets, and troubleshooting
- Test: deployment validation via GitHub Actions run log and Oracle VM runtime checks

## Task 1: Add The Deployment Workflow

**Files:**
- Create: `.github/workflows/deploy-oracle.yml`
- Test: GitHub Actions run for `main`

- [ ] **Step 1: Write the failing workflow file**

Create `.github/workflows/deploy-oracle.yml` with an intentionally incomplete secret reference so the first run proves the workflow is wired up but cannot deploy yet.

```yaml
name: Deploy to Oracle

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Fail until secrets are configured
        run: |
          test -n "${{ secrets.ORACLE_SSH_KEY }}"
          test -n "${{ secrets.ORACLE_HOST }}"
          test -n "${{ secrets.ORACLE_USER }}"
```

- [ ] **Step 2: Push the workflow stub and verify it fails for the expected reason**

Run:

```bash
git add .github/workflows/deploy-oracle.yml
git commit -m "ci: add oracle deploy workflow stub"
git push origin main
```

Expected:
- GitHub Actions starts automatically on `main`
- The workflow fails only if one or more required secrets are missing
- The repository now proves the trigger wiring works

- [ ] **Step 3: Replace the stub with the real deployment workflow**

Update `.github/workflows/deploy-oracle.yml` to:

```yaml
name: Deploy to Oracle

on:
  push:
    branches:
      - main

concurrency:
  group: deploy-oracle-main
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Start ssh-agent and add key
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.ORACLE_SSH_KEY }}

      - name: Add Oracle host to known_hosts
        run: |
          mkdir -p ~/.ssh
          ssh-keyscan -p "${{ secrets.ORACLE_PORT || 22 }}" -H "${{ secrets.ORACLE_HOST }}" >> ~/.ssh/known_hosts

      - name: Deploy on Oracle VM
        env:
          ORACLE_HOST: ${{ secrets.ORACLE_HOST }}
          ORACLE_PORT: ${{ secrets.ORACLE_PORT || 22 }}
          ORACLE_USER: ${{ secrets.ORACLE_USER }}
        run: |
          ssh -p "$ORACLE_PORT" "$ORACLE_USER@$ORACLE_HOST" '
            set -e
            cd /opt/financebro
            git pull --ff-only
            docker compose up -d --build
            docker compose ps
            docker inspect financebro --format "status={{.State.Status}} running={{.State.Running}} restart={{.RestartCount}}"
            docker compose logs --tail=50
          '
```

- [ ] **Step 4: Push the real workflow and verify syntax passes**

Run:

```bash
git add .github/workflows/deploy-oracle.yml
git commit -m "ci: add oracle auto-deploy workflow"
git push origin main
```

Expected:
- GitHub Actions triggers automatically
- The workflow reaches the SSH step
- If secrets are present, deployment proceeds instead of failing during setup

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy-oracle.yml
git commit -m "ci: automate oracle deployment from main"
```

## Task 2: Create A Dedicated Deployment SSH Key

**Files:**
- Modify: Oracle VM `~/.ssh/authorized_keys` for user `ubuntu`
- Test: SSH login using the deployment-only key

- [ ] **Step 1: Generate a new deployment keypair**

Run:

```bash
ssh-keygen -t ed25519 -C "github-actions-oracle-deploy" -f /tmp/github-actions-oracle-deploy -N ""
```

Expected:
- A private key at `/tmp/github-actions-oracle-deploy`
- A public key at `/tmp/github-actions-oracle-deploy.pub`

- [ ] **Step 2: Verify the key is readable and in OpenSSH format**

Run:

```bash
ls -l /tmp/github-actions-oracle-deploy /tmp/github-actions-oracle-deploy.pub
sed -n '1,2p' /tmp/github-actions-oracle-deploy.pub
```

Expected:
- The private key file exists
- The public key starts with `ssh-ed25519`

- [ ] **Step 3: Add the public key to the Oracle VM**

Run:

```bash
ssh -i /Users/jabin/Downloads/ssh-key-2026-04-22.key ubuntu@159.13.46.242 '
  set -e
  mkdir -p ~/.ssh
  chmod 700 ~/.ssh
  touch ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
'

PUBKEY="$(cat /tmp/github-actions-oracle-deploy.pub)"
ssh -i /Users/jabin/Downloads/ssh-key-2026-04-22.key ubuntu@159.13.46.242 "grep -qxF '$PUBKEY' ~/.ssh/authorized_keys || echo '$PUBKEY' >> ~/.ssh/authorized_keys"
```

Expected:
- The deployment public key is present in `~/.ssh/authorized_keys`
- No duplicate lines are added if rerun

- [ ] **Step 4: Verify the new key can log in independently**

Run:

```bash
ssh -i /tmp/github-actions-oracle-deploy ubuntu@159.13.46.242 'echo connected && hostname'
```

Expected:
- SSH succeeds without using the existing local key
- Output contains `connected`

- [ ] **Step 5: Commit**

No repository files change in this task, so record the operational checkpoint instead:

```bash
git status --short
```

Expected:
- No new uncommitted repository changes from this task

## Task 3: Configure GitHub Repository Secrets

**Files:**
- Out-of-band: GitHub repository settings -> Secrets and variables -> Actions
- Test: Secret presence validated by the workflow

- [ ] **Step 1: Collect the secret values**

Prepare these exact values:

```text
ORACLE_HOST=159.13.46.242
ORACLE_USER=ubuntu
ORACLE_PORT=22
ORACLE_SSH_KEY=<contents of /tmp/github-actions-oracle-deploy>
```

- [ ] **Step 2: Add the secrets in GitHub**

Add these repository secrets:

```text
ORACLE_HOST
ORACLE_USER
ORACLE_PORT
ORACLE_SSH_KEY
```

Expected:
- Each secret appears in repository Actions secrets
- The private key is stored as a multi-line secret exactly as generated

- [ ] **Step 3: Verify the deployment key was copied correctly**

Run locally:

```bash
awk 'NR<=5 {print}' /tmp/github-actions-oracle-deploy
```

Expected:
- The secret content starts with `-----BEGIN OPENSSH PRIVATE KEY-----`
- The pasted GitHub secret matches the generated file exactly

- [ ] **Step 4: Trigger a workflow run to verify secret access**

Run:

```bash
git commit --allow-empty -m "chore: trigger oracle deploy workflow"
git push origin main
```

Expected:
- Workflow starts automatically
- SSH setup succeeds, which proves the secrets are usable

- [ ] **Step 5: Commit**

```bash
git log --oneline -n 1
```

Expected:
- The latest commit is the empty trigger commit for validation

## Task 4: Document The New Release Workflow

**Files:**
- Modify: `README.md`
- Modify: `docs/DEPLOY_ORACLE.md`
- Test: review rendered markdown locally

- [ ] **Step 1: Write the failing documentation expectation**

Before editing, confirm the docs do not yet mention automatic deploy on `push`:

Run:

```bash
rg -n "GitHub Actions|push.*main|auto-deploy|自动部署" README.md docs/DEPLOY_ORACLE.md
```

Expected:
- No lines describing the new automatic deployment workflow

- [ ] **Step 2: Update `README.md` with the release workflow**

Add a concise section like:

```md
## Deploy

Production deploys to Oracle Cloud happen automatically when changes are pushed to `main`.

Typical release flow:

```bash
git add .
git commit -m "your change"
git push origin main
```

After the push, GitHub Actions connects to the Oracle VM, pulls the latest code, rebuilds the Docker image, and restarts the `financebro` container.
```

- [ ] **Step 3: Update `docs/DEPLOY_ORACLE.md` with auto-deploy setup and troubleshooting**

Add sections covering:

```md
## GitHub Actions Auto-Deploy

Trigger:
- `push` to `main`

Required GitHub Secrets:
- `ORACLE_HOST`
- `ORACLE_USER`
- `ORACLE_PORT`
- `ORACLE_SSH_KEY`

Remote deploy command:

```bash
cd /opt/financebro
git pull --ff-only
docker compose up -d --build
docker compose ps
docker compose logs --tail=50
```

Troubleshooting:
- Check the latest GitHub Actions run
- SSH into the VM and re-run the remote deploy command manually
- Inspect container state with `docker inspect financebro`
```

- [ ] **Step 4: Verify the docs contain the expected guidance**

Run:

```bash
rg -n "GitHub Actions|push to `main`|ORACLE_SSH_KEY|docker compose up -d --build" README.md docs/DEPLOY_ORACLE.md
```

Expected:
- The new docs mention the trigger, secrets, and remote deploy command

- [ ] **Step 5: Commit**

```bash
git add README.md docs/DEPLOY_ORACLE.md
git commit -m "docs: document oracle auto-deploy workflow"
```

## Task 5: End-To-End Verification

**Files:**
- Test: `.github/workflows/deploy-oracle.yml`
- Test: Oracle VM runtime state

- [ ] **Step 1: Trigger a real deployment with a safe repository change**

Use the doc changes or an empty commit:

```bash
git push origin main
```

Expected:
- GitHub Actions run starts immediately for `main`

- [ ] **Step 2: Verify the workflow run succeeds**

Check the latest run in GitHub Actions and confirm:

```text
- Checkout repository: success
- Start ssh-agent and add key: success
- Add Oracle host to known_hosts: success
- Deploy on Oracle VM: success
```

- [ ] **Step 3: Verify the Oracle VM is still healthy after the automated deploy**

Run:

```bash
ssh -i /Users/jabin/Downloads/ssh-key-2026-04-22.key ubuntu@159.13.46.242 '
  set -e
  cd /opt/financebro
  docker compose ps
  docker inspect financebro --format "status={{.State.Status}} running={{.State.Running}} restart={{.RestartCount}}"
  docker compose logs --tail=50
'
```

Expected:
- `financebro` is `Up`
- `running=true`
- Recent logs include `Application started` or steady `getUpdates "HTTP/1.1 200 OK"`

- [ ] **Step 4: Verify the deployment model matches the user workflow**

Confirm the user-facing workflow is now:

```bash
git add .
git commit -m "..."
git push origin main
```

Expected:
- No manual Oracle login is required for routine deploys

- [ ] **Step 5: Commit**

```bash
git log --oneline -n 5
```

Expected:
- Recent history includes workflow and documentation commits used for rollout
