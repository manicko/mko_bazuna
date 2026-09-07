# CI/CD Preparation Guide — Mko Bazuna (Updated)

**Date:** 2026-09-01
**Author:** Kilo (Planner Agent)
**Status:** Draft
**Based on:** `.ai/plans/ci_cd/plan.md` (2026-07-28), `.ai/plans/ci_cd/plan.md_updated.md`, `.ai/plans/ci_cd/preparation-guide.md` (2026-07-28)
**Companion:** [`plan.md_updated.md`](./plan.md_updated.md)
**Architecture reference:** [`docs/99-agent/architecture.md`](../../docs/99-agent/architecture.md)
**CI contract:** [`src/backend/tests/test_docs_ci_parity.py`](../../src/backend/tests/test_docs_ci_parity.py)
**Operations runbook:** [`docs/ops/docker-deployment.md`](../../docs/ops/docker-deployment.md)

---

## Table of Contents

0. [Stage 0 — Local Development Machine (Windows)](#0-stage-0--local-development-machine-windows)
1. [Repository Structure](#1-repository-structure)
2. [What Lives Where](#2-what-lives-where)
3. [SSH Key Pairs](#3-ssh-key-pairs)
4. [Stage A — One-time Server Preparation](#4-stage-a--one-time-server-preparation)
5. [Stage B — GitHub Configuration](#5-stage-b--github-configuration)
6. [Stage C — GitHub Actions Workflow](#6-stage-c--github-actions-workflow)
7. [Stage E — Rollback Procedure](#7-stage-e--rollback-procedure)
8. [Stage F — Verification Checklist](#8-stage-f--verification-checklist)
9. [Stage G — Daily Release Process](#9-stage-g--daily-release-process)
10. [Forward-looking Recommendations](#10-forward-looking-recommendations)
11. [Quick Reference](#11-quick-reference)

---

> **Core principle:** Separate one-time server preparation (Stage A) from the daily release process (Stage G). One-time work is done once after buying a VPS; the daily process is repeated on every release.

---

## 0. Stage 0 — Local Development Machine (Windows)

**When:** Execute once on your Windows development machine. This is the starting point — everything else builds on this.

**Goal:** A Windows machine with Git, Docker Desktop, Python 3.14, uv, and the repository cloned locally.

### 0.1 Install Git, Docker Desktop, Python, uv

```powershell
winget install Git.Git
winget install Docker.DockerDesktop
winget install Python.Python.3.14
pip install uv
```

Verify:
```powershell
git --version
docker --version
docker compose version
python --version
uv --version
```

### 0.2 Configure SSH for GitHub

Generate an SSH key for GitHub authentication (this is **different** from the VPS deploy SSH key — see [SSH Key Pairs](#3-ssh-key-pairs)):

```powershell
ssh-keygen -t ed25519 -f ~/.ssh/github_bazuna -C "your-email@example.com"
```

Add the public key to GitHub:
1. Go to **GitHub → Settings → SSH and GPG keys → New SSH key**.
2. Title: `Windows Dev Machine`
3. Key: contents of `~/.ssh/github_bazuna.pub`
4. Click **Add SSH key**.

### 0.3 Clone the repository

```powershell
git clone git@github.com:manicko/mko_bazuna.git
cd mko_bazuna
```

### 0.4 First local build

**Local development** uses the dev override (`docker-compose.dev.override.yml`) with hot-reload on port 8000. Run via the Makefile (or `Makefile.ps1` on Windows):

```powershell
make up            # Linux / macOS (uses docker-compose.yml + docker-compose.dev.override.yml)
# Or on Windows:
.\Makefile.ps1 up
```

Verify:
```powershell
curl http://localhost:8000/health/
```

Expected: `{"status": "ok"}`

**Running tests** requires a separate PostgreSQL test database in Docker on port 5433 (mapped by `docker-compose.test.yml:23`). Start it first, then run the fast gate:

```powershell
make test-db          # starts test PostgreSQL (port 5433), idempotent
make test             # fast gate: skips nightly seed suite, reuses DB
# Or on Windows:
.\Makefile.ps1 test-db
.\Makefile.ps1 test
```

> **Never run `uv run pytest` locally** without the Docker test DB — it will fail (DB unreachable on `localhost:5432`). The test infra lives in Docker, not in the local Python environment.

---

## 1. Repository Structure

Before setting up CI/CD, understand what lives in the Git repository:

```
mko_bazuna/
├── .github/
│   └── workflows/
│       ├── ci.yml                    # CI: 6 parallel jobs + coverage upload
│       ├── ci-nightly.yml            # Nightly: serial seed suite (cron + manual)
│       └── deploy.yml                # CD: to be created (build → push → deploy)
├── docker/
│   ├── Dockerfile                    # 3-stage: builder / runtime / test-runtime
│   ├── entrypoint.sh                 # Main entrypoint (shared functions, 3,472 bytes)
│   ├── entrypoint-test.sh            # Test runner (2,702 bytes)
│   ├── entrypoint-catalog.sh         # One-shot: load categories (493 bytes)
│   ├── entrypoint-create-admin.sh    # One-shot: create admin user (838 bytes)
│   ├── entrypoint-seed.sh            # One-shot: seed demo data (1,376 bytes)
│   ├── entrypoint-scheduler.sh       # Periodic task loop (2,066 bytes)
│   └── nginx/
│       └── nginx.conf                # Reverse proxy (TLS, rate limits, health)
├── src/
│   ├── backend/                      # Django project (manage.py, config/, apps/)
│   ├── theme/                        # Tailwind CSS source
│   └── telegram_bot/                 # aiogram bot code
├── docker-compose.yml                # Base: db, redis, migrate, load_catalog, web, bot, nginx
├── docker-compose.dev.override.yml   # Dev overrides (hot-reload, bind mounts, seed auto-run)
├── docker-compose.prod.yml           # Prod overrides (GHCR image overrides + scheduler/backup/pgbouncer profiles)
├── docker-compose.test.yml           # Ephemeral test DB (port 5433)
├── pyproject.toml                    # uv project + pytest config (--import-mode=importlib, xdist>=3.8)
├── Makefile                          # GNU Make targets (Linux/macOS)
├── Makefile.ps1                      # PowerShell equivalent (Windows)
├── .env.docker.example               # Production env template (23 variables, committed)
├── .env.example                      # Local dev env template (committed)
├── .env.dev.example                  # Dev env template (committed)
├── .gitignore                        # .env.docker at line 148
└── README.md

⚠️ Dead files (pending cleanup): Four 0-byte stubs at the repo root shadow the real
   scripts in docker/ and serve no purpose. They are NOT referenced by any compose
   file (which mounts docker/entrypoint*.sh) and should be investigated before removal.
   Do NOT delete docker/entrypoint*.sh.

   ├── entrypoint.sh          (0 bytes, shadows docker/entrypoint.sh: 3,472 bytes)
   ├── entrypoint-test.sh     (0 bytes, shadows docker/entrypoint-test.sh: 2,702 bytes)
   ├── entrypoint-catalog.sh  (0 bytes, shadows docker/entrypoint-catalog.sh: 493 bytes)
   └── entrypoint-seed.sh     (0 bytes, shadows docker/entrypoint-seed.sh: 1,376 bytes)
```

**Naming convention:** All compose files use the legacy `docker-compose.*.yml` naming. **Do NOT rename** — every Makefile target, compose override, CI workflow, and operational doc depends on these names (`Makefile:10-11`, `docker-compose.dev.override.yml`, `docs/ops/docker-deployment.md`, `.kilo/rules/commands.md`).

**Key files used by CI/CD:**
- `.github/workflows/ci.yml` — CI pipeline (6 jobs)
- `.github/workflows/ci-nightly.yml` — Nightly seed suite (serial)
- `.github/workflows/deploy.yml` — CD pipeline (**to be created**, §C4 below)
- `docker-compose.yml` + `docker-compose.prod.yml` — Used on VPS for deployment
- `docker/Dockerfile` — 3-stage build (builder / runtime / test-runtime)
- `docker/nginx/nginx.conf` — Reverse proxy configuration

---

## 2. What Lives Where

### In Git Repository (committed)

```
.github/workflows/ci.yml            # CI: 6 parallel jobs
.github/workflows/ci-nightly.yml    # Nightly seed suite
.github/workflows/deploy.yml         # CD: to be created
docker/Dockerfile                   # 3-stage build
docker/entrypoint*.sh               # 6 entrypoint scripts (all >0 bytes)
docker/nginx/nginx.conf             # Reverse proxy config
docker-compose.yml                  # Base services
docker-compose.dev.override.yml     # Dev overrides (hot-reload, bind mounts)
docker-compose.prod.yml             # Production overrides + profiles
docker-compose.test.yml             # Test override (port 5433)
.env.example                        # Local dev template
.env.dev.example                    # Dev env template
.env.docker.example                 # Production env template (23 variables)
pyproject.toml                      # uv + pytest config
Makefile                            # GNU Make targets
Makefile.ps1                        # Windows PowerShell equivalent
.gitignore
```

### Only on VPS (never committed)

```
.env.docker          # Production secrets (DJANGO_SECRET_KEY, BOT_TOKEN, etc.)
media/               # User-uploaded images (Telegram ad photos)
backups/             # Database dumps (7-day retention + pre-deploy backups)
certs/               # TLS certificates (fullchain.pem, privkey.pem)
```

### Never committed (local only)

```
.env                  # Local development env (gitignored via .gitignore:145)
.env.dev
.env.local
~/.ssh/github_bazuna  # SSH key for GitHub (Windows → GitHub)
~/.ssh/vps_deploy_bazuna  # SSH key for VPS (GitHub Actions → VPS)
```

### Reconciliation note — secrets strategy

The original audit listed 8 GitHub Secrets including app secrets (`DJANGO_SECRET_KEY`, `BOT_TOKEN`, `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`). **This is stale and contradicts both the code and the audit.** Current reality: only **5 server-access secrets** live in GitHub; all application secrets exist **only** in `.env.docker` on the VPS. This is enforced by code:

- `config/settings/prod.py:18-22` — fails fast if `BOT_TOKEN` is empty (non-build mode)
- `config/settings/prod.py:26-30` — fails fast if `SITE_URL` is unset
- `config/settings/prod.py:50-51` — fails fast if `ALLOWED_HOSTS` is empty
- `config/settings/base.py:52` — `DJANGO_SECRET_KEY = env("DJANGO_SECRET_KEY")` (required, no default)
- `.gitignore:148` — `.env.docker` is ignored

**GitHub Secrets (5 only):** `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`, `SERVER_PORT`, `SERVER_FINGERPRINT`. No workflow reads app secrets from GitHub Actions secrets. App secrets come solely from `.env.docker` on the VPS.

> **GHCR pull authentication (VPS → GHCR):** The VPS must authenticate to GHCR separately from GitHub Actions. The built-in `GITHUB_TOKEN` is a **GitHub App installation token** valid only for the duration of a workflow job — it **cannot** be passed to or reused by the VPS. Instead, create a **Personal Access Token (PAT)** with **only the `read:packages` scope** and run `docker login ghcr.io` on the VPS. This credential lives **only on the VPS** (in `~/.docker/config.json`), separate from `.env.docker`. See [A11. Authenticate to GHCR on the VPS (one-time)](#a11-authenticate-to-ghcr-on-the-vps-one-time).

> **Non-secret configuration:** `SERVER_HOST`, `SERVER_USER`, and `SERVER_PORT` are not secrets — they are public configuration values (e.g., `deploy`, `22`, a public IP). They *can* be stored as GitHub Actions **Variables** (referenced via `${{ vars.SERVER_HOST }}`) instead of Secrets. Keeping them as Secrets remains acceptable for organizational simplicity; the key distinction is that only `SERVER_SSH_KEY` and `SERVER_FINGERPRINT` carry confidentiality risk.

> **Secret drift avoidance (best practice):** This separation of CI/CD access credentials (GitHub Secrets) from application runtime secrets (`.env.docker` on the VPS) follows OWASP guidance: runtime secrets should be managed at the deployment lifecycle, not in the CI/CD pipeline. Storing app secrets only on the VPS eliminates the "secret drift" risk — a single source of truth per secret with no second copy to diverge.

---

## 3. SSH Key Pairs

There are **two separate SSH key pairs** — do not confuse them:

| Key Pair | Purpose | Used By |
|----------|---------|---------|
| `~/.ssh/github_bazuna` | Authenticate to GitHub (clone, push) | Your Windows machine → GitHub |
| `~/.ssh/vps_deploy_bazuna` | Authenticate to VPS for deployment | GitHub Actions → VPS |

> **Naming:** The key is named `vps_deploy_bazuna` (not `deploy_bazuna`) to unambiguously convey that this is a **VPS access key** for GitHub Actions, **not** a GitHub Deploy Key (which grants repo read access to the VPS). See [§0.2](#02-configure-ssh-for-github) and [A4](#a4-generate-vps-deploy-ssh-key-github-actions--vps) for the distinction.

**Key 1 — GitHub access (Windows → GitHub):**
- Generated in [0.2](#02-configure-ssh-for-github)
- Public key added to GitHub **Settings → SSH and GPG keys**
- Private key stays on your Windows machine

**Key 2 — VPS deploy access (GitHub Actions → VPS):**
- Generated in [A4](#a4-generate-vps-deploy-ssh-key-github-actions--vps)
- Public key copied to VPS `~/.ssh/authorized_keys`
- Private key stored as the `SERVER_SSH_KEY` GitHub Secret
- Used by `appleboy/ssh-action` in the deploy workflow (with `fingerprint:` from [A4b](#a4b-capture-the-ssh-host-fingerprint-security-hardening))

---

## 4. Stage A — One-time Server Preparation

**When:** Execute once, immediately after purchasing the VPS. Never repeat unless the server is destroyed.

**Goal:** A hardened Linux server with Docker, a deploy user, directory structure, and an initial `.env.docker` file. After this stage, the server is ready to receive images from GHCR.

### A0. Prerequisites Checklist

| Item | What you need | How to obtain |
|------|--------------|---------------|
| **VPS** | 4 CPU, 8 GB RAM, Ubuntu 24.04 LTS | DigitalOcean, Hetzner, AWS EC2, etc. |
| **Root access** | Password or SSH key for `root` | Provided by VPS provider |
| **Domain name** (recommended) | e.g., `bazuna.com` | Domain registrar |
| **GitHub account** | Admin access to `mko_bazuna` repo | Existing or create new |
| **Telegram BotFather token** | Bot token string | Message `@BotFather` → `/newbot` → copy token |
| **Your Telegram user ID** | Numeric ID | Message `@userinfobot` → copy ID |

### A1. Provision the VPS

1. Create a VPS instance (Ubuntu 24.04 LTS recommended).
2. Note the **public IP address** — you will need it for `SERVER_HOST`.
3. SSH into the server as root:
   ```bash
   ssh root@<YOUR_VPS_IP>
   ```

### A2. Install Docker and Docker Compose

On the VPS, as root:

```bash
apt-get update
apt-get install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

docker --version
docker compose version
```

### A3. Create the deploy user

```bash
useradd -m -s /bin/bash deploy
usermod -aG docker deploy
```

### A4. Generate VPS deploy SSH key (GitHub Actions → VPS)

> **Terminology note:** This key pair (`vps_deploy_bazuna`) is **NOT** a GitHub Deploy Key. A GitHub Deploy Key is a *repository-specific* key that grants the VPS read access to a single GitHub repo. This key is a **VPS SSH access key**: the public key goes into the VPS `~/.ssh/authorized_keys`, and the private key becomes the `SERVER_SSH_KEY` GitHub Secret so that GitHub Actions can SSH into the VPS. The direction is reversed: GitHub Actions → VPS, not VPS → GitHub.

On your **local Windows machine**, generate an SSH key pair:

```powershell
ssh-keygen -t ed25519 -f ~/.ssh/vps_deploy_bazuna -C "vps-deploy@bazuna"
```

Copy the public key to the VPS. **Note:** `ssh-copy-id` is a Linux/macOS utility and does **not** exist in Windows OpenSSH. Use this PowerShell equivalent instead:

```powershell
# Windows PowerShell equivalent of: ssh-copy-id -i ~/.ssh/vps_deploy_bazuna.pub deploy@<YOUR_VPS_IP>
Get-Content $HOME\.ssh\vps_deploy_bazuna.pub |
  ssh deploy@<YOUR_VPS_IP> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

> **Alternative** (if the `deploy` user cannot yet accept password login but `root` can):
> ```powershell
> Get-Content $HOME\.ssh\vps_deploy_bazuna.pub |
>   ssh root@<YOUR_VPS_IP> "mkdir -p /home/deploy/.ssh && chmod 700 /home/deploy/.ssh && cat >> /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys && chown -R deploy:deploy /home/deploy/.ssh"
> ```

Verify the key works:

```bash
ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP>
```

The **private key** (`~/.ssh/vps_deploy_bazuna`) becomes the `SERVER_SSH_KEY` GitHub Secret. Keep it secure — never commit it to the repo.

### A4b. Capture the SSH host fingerprint (security hardening)

To prevent man-in-the-middle attacks, pin the VPS's SSH host public key fingerprint. This value is passed as the `fingerprint:` parameter to `appleboy/ssh-action` in the deploy workflow, enabling strict host-key verification.

On the VPS (or via an already-trusted SSH session), retrieve the SHA256 fingerprint:

```bash
# Retrieve the fingerprint of the VPS SSH host key
ssh deploy@<YOUR_VPS_IP> ssh-keygen -l -f /etc/ssh/ssh_host_ed25519_key.pub | cut -d ' ' -f2
```

This outputs a value like `SHA256:abcdefghijklmnopqrstuvwxyz1234567890=`. Copy that exact string and store it as the `SERVER_FINGERPRINT` GitHub Secret (see [B2](#b2-add-github-secrets--server-access-only-5-secrets)).

> **If the VPS uses RSA host keys only** (no `ed25519` key), substitute `ssh_host_rsa_key.pub`:
> ```bash
> ls /etc/ssh/ssh_host_*_key.pub   # list available host keys
> ```
> Then use the appropriate key file in the `ssh-keygen -l -f` command above.

### A5. Create directory structure

On the VPS, as the deploy user:

```bash
sudo mkdir -p /opt/mko_bazuna/{backups,certs,media}
sudo chown -R deploy:deploy /opt/mko_bazuna
```

Directory layout after this step:

```
/opt/mko_bazuna/
├── backups/           # Database dumps (7-day retention + pre-deploy backups)
├── certs/             # TLS: fullchain.pem, privkey.pem
├── media/             # User-uploaded images (Telegram ad photos)
├── docker-compose.yml         # Copied from repo (§A6)
├── docker-compose.prod.yml    # Copied from repo (§A6)
├── docker/
│   └── nginx/
│       └── nginx.conf        # Copied from repo (§A6)
├── .env.docker                # Created in A6 (chmod 600)
└── .docker/                   # GHCR auth config (created in A11)
    └── config.json            # docker login ghcr.io credential (read-only PAT)
```

> **GHCR auth** (`.docker/config.json`) is created in [A11](#a11-authenticate-to-ghcr-on-the-vps-one-time). It is **not** part of `.env.docker` — it is a registry credential, not an application secret.

### A6. Copy compose files and nginx config to VPS

**The source code is NOT needed on the VPS** — it is already baked into the Docker images pulled from GHCR. Only the Docker Compose files and nginx config are required to define service orchestration.

From your local machine, copy the files using the full real names:

```bash
scp -i ~/.ssh/vps_deploy_bazuna \
  docker-compose.yml \
  docker-compose.prod.yml \
  docker/nginx/nginx.conf \
  deploy@<YOUR_VPS_IP>:/opt/mko_bazuna/

ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP> \
  "mkdir -p /opt/mko_bazuna/docker/nginx"

scp -i ~/.ssh/vps_deploy_bazuna \
  docker/nginx/nginx.conf \
  deploy@<YOUR_VPS_IP>:/opt/mko_bazuna/docker/nginx/
```

### A7. Create `.env.docker` on the VPS

Create `.env.docker` on the VPS using all 23 variables from the real `.env.docker.example` template:

```bash
ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna

cat > .env.docker << 'ENVEOF'
# ====================== Django ======================
DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>
DEBUG=False
ALLOWED_HOSTS=<your-domain.com>,localhost,127.0.0.1

# ====================== PostgreSQL Database ======================
POSTGRES_USER=bazuna_user
POSTGRES_DB=bazuna_db
POSTGRES_PASSWORD=<generate-with-openssl-rand-base64-32>

# ====================== Redis ======================
REDIS_URL=redis://redis:6379/0

# ====================== Telegram Bot ======================
BOT_USERNAME=<your-bot-username>
BOT_TOKEN=<YOUR-BOT-TOKEN-FROM-BOTFATHER>

# ====================== Public site ======================
SITE_URL=https://your-domain.com
IMMEDIATE_ALERTS_ENABLED=false

# ====================== TLS Certificates ======================
TLS_CERT_PATH=/etc/nginx/certs

# ====================== Analytics ======================
PLAUSIBLE_HOST=

# ====================== Admin ======================
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generate-with-openssl-rand-base64-24>
ADMIN_TELEGRAM_ID=<your-telegram-user-id>

# ====================== Seed (demo data) ======================
SEED_USERS=10
SEED_ADS=600

# ====================== Production image / registry ======================
# GHCR auth is NOT stored here — it is handled via `docker login ghcr.io` on the
# VPS using a read-only PAT (see §A11). These vars only identify the registry/location.
REGISTRY=ghcr.io
REPOSITORY=manicko/mko_bazuna
IMAGE_TAG=<your-sha-tag-or-version>

# ====================== Container runtime ======================
FIX_PERMISSIONS=0
SKIP_ENV_CHECK=
ENVEOF
```

**Generating secure values:**

```bash
# Django secret key
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# PostgreSQL / admin passwords
openssl rand -base64 32
openssl rand -base64 24
```

### A8. Set file permissions

On the VPS:

```bash
chmod 600 .env.docker
chown -R deploy:deploy /opt/mko_bazuna
chmod 700 /opt/mko_bazuna/certs
```

### A9. (Optional) Set up TLS certificates

If you have a domain and want HTTPS:

```bash
sudo apt-get install -y certbot
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem /opt/mko_bazuna/certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem /opt/mko_bazuna/certs/
sudo chown deploy:deploy /opt/mko_bazuna/certs/*
sudo chmod 600 /opt/mko_bazuna/certs/privkey.pem
```

### A10. (Optional) Initial manual deployment

Before GHCR images exist (i.e., before the deploy workflow is built), you can do a manual test deploy that builds images locally:

```bash
cd /opt/mko_bazuna
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The `--build` flag forces a local build since no GHCR image exists yet. Once the deploy workflow is operational (§C4), future deploys will use `docker compose pull` to fetch pre-built images from GHCR instead.

### A11. Authenticate to GHCR on the VPS (one-time)

The VPS must authenticate to GHCR to pull private container images. The built-in `GITHUB_TOKEN` (used by GitHub Actions to push) is a **GitHub App installation token** valid only for the duration of a workflow job — it **cannot** be passed to or reused by the VPS. Instead, create a **Personal Access Token (PAT)** with **only the `read:packages` scope** and log in on the VPS.

1. **Create a PAT on GitHub:**
   - Go to **Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token**.
   - Give it a descriptive name (e.g., `vps-ghcr-read`).
   - Select **only** the `read:packages` scope (minimal privilege).
   - *(Optional)* Set an expiration date.
   - Click **Generate token** and copy the token.

2. **On the VPS**, as the `deploy` user, log in to GHCR:
   ```bash
   echo "<YOUR_PAT>" | docker login ghcr.io -u <YOUR_GH_USERNAME> --password-stdin
   ```
3. **Verify** the login works:
   ```bash
   docker pull ghcr.io/manicko/mko_bazuna:sha-<SOME_TAG>
   ```

4. The credential is stored in `/home/deploy/.docker/config.json` on the VPS and persists across reboots. **Never** put this PAT in `.env.docker` — it is a registry access credential, not an application secret. It is also **never** stored in GitHub Secrets; the VPS authenticates to GHCR independently from the CI/CD pipeline.

---

## 5. Stage B — GitHub Configuration

**When:** One-time setup in GitHub. Done alongside Stage A.

### B1. Create the `production` environment

1. Go to your GitHub repository → **Settings → Environments**.
2. Click **New environment**.
3. Name: `production`.
4. (Optional) Add required reviewers for manual approval gates.
5. Click **Configure environment**.

### B2. Add GitHub Secrets — Server Access Only (5 secrets)

**Critical design decision:** Only server-access secrets go in GitHub Secrets. All application secrets (DJANGO_SECRET_KEY, BOT_TOKEN, POSTGRES_PASSWORD, ADMIN_PASSWORD, etc.) exist **only** in `.env.docker` on the VPS. This eliminates the risk of secret drift between two locations.

Go to **Settings → Secrets and variables → Actions → New repository secret**.

Add **only 5 secrets**:

| Secret Name | Value | How to obtain |
|-------------|-------|---------------|
| `SERVER_HOST` | VPS public IP or hostname | From VPS provider dashboard |
| `SERVER_USER` | `deploy` | The deploy user created in A3 |
| `SERVER_SSH_KEY` | Contents of `~/.ssh/vps_deploy_bazuna` (private key) | Generated in A4 — **the private key, not the .pub file** |
| `SERVER_PORT` | `22` (or your custom SSH port) | Default is 22 unless you changed it |
| `SERVER_FINGERPRINT` | SHA256 fingerprint of VPS SSH host key (e.g., `SHA256:abcd…`) | Captured in [A4b](#a4b-capture-the-ssh-host-fingerprint-security-hardening) |

#### SERVER_SSH_KEY format

The `SERVER_SSH_KEY` must be the **entire private key file contents**, including the `-----BEGIN OPENSSH PRIVATE KEY-----` and `-----END OPENSSH PRIVATE KEY-----` lines.

```bash
# On your local machine:
cat ~/.ssh/vps_deploy_bazuna | clip    # Windows
cat ~/.ssh/vps_deploy_bazuna | pbcopy  # macOS
```

### B3. Verify secrets are set

After adding all secrets, verify they appear in the list (values are hidden):

```
SERVER_HOST         ••••••••••
SERVER_USER         ••••••••••
SERVER_SSH_KEY      ••••••••••
SERVER_PORT         ••••••••••
SERVER_FINGERPRINT  ••••••••••
```

---

## 6. Stage C — GitHub Actions Workflow

**When:** One-time file creation / verification. After this, CI runs automatically on every push/PR; CD runs on manual `workflow_dispatch`.

> **⚠️ Correction:** The original prep-guide §C1 proposed creating a **single** `ci-cd.yml`. This is stale. CI was already split into **`ci.yml`** (6-job parallel gate) + **`ci-nightly.yml`** (serial seed suite). The only file still to be created is **`deploy.yml`** (CD). See §C4 below.

### C1. CI workflow split — already implemented ✅

The repository currently contains two CI workflow files:

```
.github/workflows/
├── ci.yml            # 6 parallel jobs (build, test, lint, typecheck, lint-templates, i18n)
├── ci-nightly.yml    # Serial seed suite (cron 03:00 UTC + manual workflow_dispatch)
└── deploy.yml        # CD pipeline — TO BE CREATED (§C4)
```

### C2. `ci.yml` — CI baseline (6 jobs, already live ✅)

The current `ci.yml` runs on every push to `main` / `develop` and on pull requests. It has **6 parallel jobs**:

| Job | Purpose | Status |
|-----|---------|--------|
| `build` | Docker build with GHCR registry cache (`push: false`); validates image builds | ✅ Live (`ci.yml:8-33`) |
| `test` | PostgreSQL 18 service + pytest with coverage | ✅ Live (`ci.yml:35-119`) |
| `lint` | Ruff check | ✅ Live |
| `typecheck` | Basedpyright | ✅ Live |
| `lint-templates` | Djlint on Django templates | ✅ Live (`ci.yml:157-173`) |
| `i18n` | compilemessages `--locale ru --locale bs --locale en` + `test_i18n_completeness.py` | ✅ Live (`ci.yml:177-253`) |

**Important — CI contract enforced by `test_docs_ci_parity.py`:** The test job uses the following exact flags (`ci.yml:111`):

```
uv run pytest -m "not seed" -n auto --dist loadgroup --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

This contract is **enforced** by `src/backend/tests/test_docs_ci_parity.py:45-175`, which asserts that `ci.yml`, the `Makefile`/`Makefile.ps1`, and `pyproject.toml` all agree on:
- `--dist loadgroup` (intentional — bot FSM tests share state and must pin to the same xdist worker)
- `-m "not seed"` (fast gate — nightly seed suite runs separately)
- `--reuse-db` (test DB schema persists between runs)
  - `--import-mode=importlib` in `pyproject.toml:169` addopts

**Nightly seed suite (`ci-nightly.yml:73`)** runs the slow tests serially:

```
uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
```

> **⚠️ Advisory only:** `pytest-xdist>=3.8.0` (`pyproject.toml:214`) technically supports `--dist worksteal` for better load balancing. However, `loadgroup` is intentionally used because bot tests share FSM-pinned state. Switching to `worksteal` would require updating `test_docs_ci_parity.py` to enforce the new flag. Do NOT adopt blindly.

**Two small CI hardening tasks remain (Stage B in plan.md_updated.md §B1/B3):**
- **B1:** Add a `concurrency:` group to `ci.yml` to cancel superseded runs.
- **B3:** Add `paths-ignore` to `ci.yml` to skip docs-only changes.

These do **not** change the test command contract and do not require updating the parity test.

### C3. `ci-nightly.yml` — nightly seed suite (already live ✅)

```yaml
# .github/workflows/ci-nightly.yml — daily at 03:00 UTC + manual trigger
name: Nightly Seed Tests

on:
  schedule:
    - cron: "0 3 * * *"
  workflow_dispatch:

concurrency:
  group: nightly-seed-tests
  cancel-in-progress: false  # do not cancel — seed tests must complete

jobs:
  seed-tests:
    runs-on: ubuntu-latest
    env:
      PYTHONPATH: ${{ github.workspace }}/src:${{ github.workspace }}/src/backend
    services:
      db:
        image: postgres:18-alpine
        # ...env + healthcheck identical to ci.yml test job...
    steps:
      - uses: actions/checkout@v4
      - name: Setup uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --frozen --no-install-project --group dev
        working-directory: src/backend
      # ...wait-for-db, migrate...
      - name: Run seed tests with coverage
        run: uv run pytest -m "seed" --tb=short --cov --durations=10 --cov-report=term --cov-report=xml --reuse-db
        working-directory: src/backend
      - name: Upload coverage report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: nightly-coverage-report
          path: src/backend/coverage.xml
          retention-days: 7
```

### C4. `deploy.yml` — CD pipeline (TO BE CREATED)

**Status:** Not started. No `deploy.yml` exists. The CI build job uses `push: false`, so no image is ever published.

Create `.github/workflows/deploy.yml` with:
- `workflow_dispatch` trigger with a **required** `commit_sha` input — the user enters a commit SHA; the workflow checks out that exact commit (`ref:`), derives an immutable `sha-<short>` tag from the checked-out SHA, and tags the image with it. **Never** trust the raw input as the image tag; always derive the tag from `git rev-parse --short HEAD` after checkout. See [Rationale §10](#10-rationale-commit_sha-vs-image_tag-why-checkout-must-pin-to-the-requested-sha) for why this matters.
- GHCR auth using the built-in `GITHUB_TOKEN` (**GitHub App installation token**) — used only for pushing from the runner. No PAT stored as a secret. The VPS authenticates to GHCR separately with a read-only PAT (see [A11. Authenticate to GHCR on the VPS (one-time)](#a11-authenticate-to-ghcr-on-the-vps-one-time)).
- `docker/metadata-action@v5` with `context: git` for SHA + raw tags derived from the checked-out commit
- `docker/build-push-action@v7` with `push: true`
- Deploy job: SSH via `appleboy/ssh-action@v1` using the 5 GitHub Secrets → VPS (with `fingerprint` pinning for MITM protection). GHCR auth via `docker/login-action` with the built-in `GITHUB_TOKEN` (GitHub App installation token) — used only for **pushing** from the runner.

**Full YAML template (corrected — uses `docker-compose.*.yml` names, `GITHUB_TOKEN` (GitHub App installation token), `commit_sha` input, `fingerprint` pinning, and `docker compose ps` for rollback):**

```yaml
name: Deploy

on:
  workflow_dispatch:
    inputs:
      commit_sha:
        description: 'Commit SHA to deploy (full 40-char SHA or unambiguous short SHA)'
        required: true
        type: string

env:
  REGISTRY: ghcr.io

jobs:
   build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ inputs.commit_sha }}
          fetch-depth: 0

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          token: ${{ secrets.GITHUB_TOKEN }}   # built-in GitHub App installation token; no PAT

      - name: Resolve immutable IMAGE_TAG from the checked-out SHA
        id: vars
        run: |
          SHORT_SHA=$(git rev-parse --short HEAD)
          echo "IMAGE_TAG=sha-${SHORT_SHA}" >> "$GITHUB_OUTPUT"

      - name: Extract metadata (tags, labels)
        id: meta
        uses: docker/metadata-action@v5
        with:
          context: git
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=raw,value=${{ steps.vars.outputs.IMAGE_TAG }}

      - name: Build and push image
        uses: docker/build-push-action@v7
        with:
          context: .
          file: docker/Dockerfile
          push: true
          platforms: linux/amd64
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

    outputs:
      IMAGE_TAG: ${{ steps.vars.outputs.IMAGE_TAG }}

  deploy:
    needs: [build-and-push]
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
    concurrency:
      group: deploy-${{ github.ref }}
      cancel-in-progress: false
    steps:
      - name: Deploy to VPS (pull → backup → migrate → up → prune → health → rollback)
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          port: ${{ secrets.SERVER_PORT || '22' }}
          fingerprint: ${{ secrets.SERVER_FINGERPRINT }}
          envs: |
            IMAGE_TAG=${{ needs.build-and-push.outputs.IMAGE_TAG }}
            REPOSITORY=${{ github.repository }}
          script: |
            set -e
            DEPLOY_DIR="/opt/mko_bazuna"
            cd "$DEPLOY_DIR"

            export REGISTRY="ghcr.io"
            export REPOSITORY="$REPOSITORY"
            export IMAGE_TAG="$IMAGE_TAG"

            # Authenticate to GHCR for image pulls (VPS uses a read-only PAT, see §A11).
            # The PAT must already be configured via `docker login` on the VPS.
            mkdir -p "$DEPLOY_DIR/backups"

            # Save current image tag for rollback (E1 — image-only rollback, NOT DB rollback)
            CURRENT_IMAGE=$(docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml \
              ps --format "{{.Image}}" web 2>/dev/null || echo "")
            PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | rev | cut -d: -f1 | rev || echo "")
            echo "$PREVIOUS_TAG" > /opt/mko_bazuna/.previous_tag
            echo "Previous tag saved: $PREVIOUS_TAG"

            # Pull latest images from GHCR
            echo "Pulling images from GHCR..."
            docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml pull

            # Pre-deploy database backup — host-side redirect to persisted ./backups/.
            # Container env vars (POSTGRES_USER/POSTGRES_DB) are resolved via --env-file;
            # the dump file lands in /opt/mko_bazuna/backups/ for §E3b restore.
            echo "Backing up database..."
            docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml \
              exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c \
              > "$DEPLOY_DIR/backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump"

            # Pre-deploy migrations via one-shot service.
            # NOTE: migrations are FORWARD ONLY. The automatic rollback below
            # reverts the container image only — database migrations are NOT reversed.
            # See §E3 for the manual DB restore procedure from the pre-deploy backup.
            echo "Running pre-deploy migrations..."
            docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

            # Start new containers (image override already in docker-compose.prod.yml:7-26)
            echo "Starting new containers..."
            docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d

            # Clean up old images
            docker image prune -f

            echo "Deployment complete"

      - name: Health check with automatic rollback
        if: always() && !cancelled()
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          port: ${{ secrets.SERVER_PORT || '22' }}
          fingerprint: ${{ secrets.SERVER_FINGERPRINT }}
          script: |
            DEPLOY_DIR="/opt/mko_bazuna"
            cd "$DEPLOY_DIR"

            echo "Waiting for services to stabilize..."
            sleep 10

            # Health check: run curl inside the web container via docker compose exec
            # (web:8000 is not published on the host; "web" DNS only resolves inside
            #  the compose network, so curl must execute within docker compose)
            for i in $(seq 1 30); do
              STATUS=$(docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml \
                exec -T web curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/ 2>/dev/null || echo "000")
              if [ "$STATUS" = "200" ]; then
                echo "Health check passed"
                exit 0
              fi
              echo "Waiting for service (attempt $i)..."
              sleep 5
            done

            # IMAGE-ONLY ROLLBACK — does NOT revert database migrations.
            # Migrations are forward-only; DB rollback requires restoring the
            # pre-deploy backup (see §E3 manual rollback via SSH).
            echo "Health check failed — initiating automatic rollback..."
            PREVIOUS_TAG=$(cat /opt/mko_bazuna/.previous_tag 2>/dev/null || echo "")
            if [ -n "$PREVIOUS_TAG" ]; then
              echo "Rolling back to previous tag: $PREVIOUS_TAG"
              export REGISTRY="ghcr.io"
              export REPOSITORY="${REPOSITORY}"
              export IMAGE_TAG="$PREVIOUS_TAG"
              docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml pull web
              docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps web
              echo "Rollback completed — verify manually"
            else
              echo "No previous tag available for rollback — check VPS manually"
            fi
            exit 1
```

> **C9 advisory:** For production-grade rollback, consider image-digest pinning (immutable digests) instead of tag-based rollback. Tags can be mutated; digests cannot. See `plan.md_updated.md` §13 for the full Stage C breakdown (C1–C10).

### C5. Compose file name corrections

**⚠️ All compose references must use the real legacy names.** The original prep guide used `compose.yaml` / `compose.prod.yaml` / `compose.dev.yaml` / `compose.test.yaml` — these are **stale and do not exist**:

| Stale name (DO NOT USE) | Correct name (use this) |
|------|------|
| `compose.yaml` | `docker-compose.yml` |
| `compose.dev.yaml` | `docker-compose.dev.override.yml` |
| `compose.prod.yaml` | `docker-compose.prod.yml` |
| `compose.test.yaml` | `docker-compose.test.yml` |

Every Makefile target, VPS deploy command, and verification step in this guide uses the corrected `docker-compose.*.yml` names. **Do not rename the files** — all tooling depends on the legacy names.

### C6. Verify `.env.docker` is NOT committed ✅ Done

```bash
git check-ignore .env.docker
# Should output: .env.docker
```

`.env.docker` is gitignored at `.gitignore:148`. The tracked template is `.env.docker.example` (23 variables). Three tracked templates exist: `.env.example`, `.env.dev.example`, `.env.docker.example`.

### C7. Health endpoint

The project includes a `/health/` endpoint (`docker/Dockerfile:154-155` HEALTHCHECK). The deploy workflow verifies it via `docker compose exec` (the host cannot resolve the compose-internal `web` hostname or reach port 8000, which is not published):

```bash
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml exec -T web curl -sf http://localhost:8000/health/
```

Expected response:
```json
{"status": "ok"}
```

---

## 7. Stage E — Rollback Procedure

**When:** Used when a deployment breaks the production site.

> **⚠️ Rollback scope — image only, NOT database migrations:** The automatic rollback reverts the **container image** (the `web` service) to the previous GHCR tag. It does **NOT** reverse database migrations, which are applied forward-only. A pre-deploy database backup (see §[A7](#a7-create-envdocker-on-the-vps)) is the ultimate fallback for catastrophic schema issues. See [E3b. Manual DB restore](#e3b-manual-db-restore-from-backup-image-only-rollback-is-insufficient) for the manual recovery procedure.

> **Note:** Automatic rollback is **part of the unbuilt `deploy.yml`** (§C4). It is not yet live. Manual rollback via SSH is always available.

### E1. Automatic rollback (image-only, TO BE IMPLEMENTED)

Once `deploy.yml` is created, the health-check step (30 attempts × 5s = 150s) will automatically roll back on failure. This is an **image-only** rollback:

1. The workflow reads the previous tag from `/opt/mko_bazuna/.previous_tag` (captured via `docker compose ps` before deploy).
2. It pulls the previous image from GHCR (the VPS authenticates via its read-only GHCR PAT — see §A11).
3. It restarts the `web` container with the previous image (`up -d --no-deps web`).
4. The workflow exits with an error — you must verify manually.

> **Database migrations are NOT reverted by this step.** Migrations are forward-only (`migrate --noinput`). If the rollback to the previous image fails due to a schema incompatibility, follow [E3b. Manual DB restore](#e3b-manual-db-restore-from-backup-image-only-rollback-is-insufficient) to restore the pre-deploy database backup.

### E2. Manual rollback via GitHub Actions

Once `deploy.yml` exists:

1. Go to **Actions** tab in GitHub.
2. Select the **Deploy** workflow.
3. Click **Run workflow** (dropdown).
4. In the `commit_sha` input, enter the commit SHA of the known-good version.
   - Find the SHA on the **Commits** tab or in the **Actions** run history.
5. Click **Run workflow**.

The workflow will:
- Check out that specific commit (via `ref:`).
- Build the image from that commit.
- Derive the immutable tag `sha-<short>`.
- Push it to GHCR.
- Deploy it to the VPS.

### E3. Manual rollback via SSH

If GitHub Actions is unavailable:

```bash
ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP>

cd /opt/mko_bazuna

# List available images
docker images | grep ghcr.io

# Down current containers
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml down

# Set the image tag to the known-good version
# (IMAGE_TAG is derived as sha-<COMMIT_SHA> from git rev-parse)
export IMAGE_TAG="sha-<COMMIT_SHA>"

# Pull and start
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### E3b. Manual DB restore from backup (image-only rollback is insufficient)

Use this procedure when the previous image won't work with the current database schema (e.g., a destructive migration was applied, then the image was rolled back but the schema changed). This is an **image-only fallback** — it does not reverse migrations.

**Prerequisites:** Locate the pre-deploy backup dump in `/opt/mko_bazuna/backups/`. It was created automatically by the deploy workflow before migrations ran (see §C4 deploy script, "Pre-deploy database backup").

```bash
ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna

# Stop all containers
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml down

# Restore the pre-deploy database backup
# Find the latest pre_deploy_*.dump file:
LATEST_BACKUP=$(ls -t /opt/mko_bazuna/backups/pre_deploy_*.dump | head -1)
echo "Restoring from: $LATEST_BACKUP"

# Restore using exec -T (runs in existing container; host file piped to stdin)
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  < "$LATEST_BACKUP"

# Start fresh DB container (pg_restore wrote to the running container's volume)
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d db

# Pull and start the known-good image
export IMAGE_TAG="sha-<KNOWN_GOOD_COMMIT_SHA>"
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> **Warning:** `pg_restore --clean` drops existing tables before restoring. Ensure you are restoring the correct backup — the most recent pre-deploy dump is almost always the right one.

> The rollback procedure is documented in this guide (§Stage E above). `docs/ops/docker-deployment.md` does **not** contain a rollback section — do not reference it for rollback; all rollback steps live here.

---

## 8. Stage F — Verification Checklist

**When:** Run after initial setup (once) and after each major change.

### F1. CI Verification

| Test | Expected Result | Status |
|------|----------------|--------|
| Push to `develop` branch | CI runs (6 jobs): build, test, lint, typecheck, lint-templates, i18n — no deploy | ✅ Live |
| Push to `main` branch | All 6 CI jobs run in parallel | ✅ Live |
| Open PR to `main` | CI runs with same behavior as push | ✅ Live |
| CI test command | `-m "not seed" -n auto --dist loadgroup --reuse-db --cov` (enforced by parity test) | ✅ Enforced |
| `ci-nightly.yml` runs | Daily at 03:00 UTC serial seed suite (`-m "seed"`) | ✅ Live |
| Parity test passes | `test_docs_ci_parity.py` asserts CI contract on `ci.yml` / `Makefile` / `pyproject.toml` | ✅ Enforced |

### F2. CD Verification (after `deploy.yml` is created)

| Test | Expected Result | Status |
|------|----------------|--------|
| Run `workflow_dispatch` with `commit_sha` (a commit SHA) | That commit's image deploys as `sha-<short-sha>` | ⬜ To verify |
| GHCR image pushed with SHA tag | Check `ghcr.io/manicko/mko_bazuna` package, tag `sha-<short-sha>` | ⬜ To verify |
| `docker compose pull` runs | Images fetched from GHCR (check deploy logs) | ⬜ To verify |
| Pre-deploy backup created | `.dump` file in `/opt/mko_bazuna/backups/` | ⬜ To verify |
| Pre-deploy migrations run | `migrate` one-shot service runs, exits 0 | ⬜ To verify |
| Health check passes | `docker compose exec -T web curl -sf http://localhost:8000/health/` returns 200 | ⬜ To verify |
| Containers running | `docker compose ps` shows all services `Up` | ⬜ To verify |
| Docker cleanup runs | `docker image prune -f` executed | ⬜ To verify |
| Rollback on failure | Deploy broken image → automatic **image-only** rollback to previous tag (DB migrations NOT reverted) | ⬜ To verify |
| VPS → GHCR authentication | `docker pull ghcr.io/manicko/mko_bazuna:sha-<tag>` succeeds (PAT with `read:packages` configured via §A11) | ⬜ To verify |
| SSH host fingerprint pinned | Deploy workflow includes `fingerprint: ${{ secrets.SERVER_FINGERPRINT }}` (captured in §A4b) | ⬜ To verify |

### F3. Server Health Verification (on VPS)

```bash
ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna

# Check all containers
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml ps

# Check web health
curl -s http://localhost:8000/health/

# Check logs
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml logs web --tail 20
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml logs bot --tail 20

# Check disk space
df -h

# Check backups
ls -la /opt/mko_bazuna/backups/
```

### F4. Local test verification (before deploying)

```powershell
# Start test DB (port 5433)
make test-db
# Or: .\Makefile.ps1 test-db

# Run fast gate (skips nightly seed suite)
make test
# Or: .\Makefile.ps1 test
```

> Local tests require the Docker test DB — never run `uv run pytest` directly without it.

---

## 9. Stage G — Daily Release Process

**When:** Every time you want to deploy a new version to production. This is the **only** stage you repeat regularly.

> **⚠️ Prerequisite:** `deploy.yml` must be created (§C4) before this process works. CI is already live and runs on every push/PR.

### G1. Prerequisites (verified daily)

Before each release, confirm:

1. **CI is green** on `main` branch (all 6 jobs pass in `ci.yml`).
2. **Your VPS is running** and accessible via SSH.
3. **You have the commit SHA** you want to deploy.

### G2. The release flow (5 minutes, no SSH needed)

#### Step 1. Merge to `main`

Ensure your changes are merged to the `main` branch:

```bash
git checkout main
git pull origin main
```

CI will automatically run on the push. Wait for all 6 jobs to pass.

#### Step 2. Trigger the deployment

1. Go to the **Actions** tab in GitHub.
2. Select the **Deploy** workflow (requires `deploy.yml` to exist — §C4).
3. Click the **Run workflow** dropdown → **Run workflow**.
4. In the `commit_sha` input, enter the **commit SHA** to deploy:
   - Find the SHA on the **Commits** tab or in the **Actions** run history.
5. Click **Run workflow**.

> **Important:** The `commit_sha` input is **required** — the workflow checks out that exact commit via `ref:`, derives the immutable `IMAGE_TAG=sha-<short>` from `git rev-parse --short HEAD`, and builds the image from that commit's source. This ensures every deployment is traceable to a specific commit and enables precise rollback. Never use `latest`.

The workflow will:
- Build the Docker image with the specified commit SHA (GITHUB_TOKEN — a GitHub App installation token — to GHCR).
- Push to GHCR.
- SSH into the VPS.
- Pull the new image.
- **Backup the database** (pre-migration safety net).
- Run migrations (advisory lock, ID 100).
- Restart containers.
- Clean up old Docker images.
- Run health check (30 attempts × 5s).
- Rollback automatically if health check fails.

#### Step 3. Monitor the deployment

Watch the workflow run in the GitHub Actions UI. It takes 2–5 minutes.

**Success indicators:**
- All steps show green checkmarks.
- Health check step shows "Health check passed".
- Deploy step shows "Deployment complete".

**Failure indicators:**
- Any step shows a red X.
- Health check step shows "Health check failed — initiating automatic rollback".
- The workflow attempts automatic rollback to the previous tag.

#### Step 4. Verify on the server (recommended)

```bash
ssh -i ~/.ssh/vps_deploy_bazuna deploy@<YOUR_VPS_IP>
cd /opt/mko_bazuna
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml ps
curl -s http://localhost:8000/health/
```

### G3. Rollback (if something goes wrong)

If the deployment fails or the site is broken:

1. **Automatic:** If the health check fails, `deploy.yml`'s rollback step (§E1) automatically redeploys the previous tag.
2. **Manual via Actions:** Go to **Actions** → **Deploy** workflow → **Run workflow** dropdown → enter the `commit_sha` of the known-good version.
3. **Manual via SSH:** See [§E3](#e3-manual-rollback-via-ssh).

### G4. What NOT to do during release

- **Do not** SSH into the VPS and run `docker compose up -d` manually (use the workflow) — the workflow handles the full sequence (pull → backup → migrate → up → prune → health).
- **Do not** edit `.env.docker` on the VPS during deploy — the workflow doesn't touch it, but manual edits can cause confusion.
- **Do not** merge to `main` without CI passing.
- **Do not** use `workflow_dispatch` on the `develop` branch — deploy only from `main`.
- **Do not** leave `commit_sha` empty — always specify a real commit SHA.

---

## 10. Forward-looking Recommendations

These are **advisory** improvements that can be implemented later. None change the core Docker + GHCR + manual-`workflow_dispatch` + single-VPS model.

1. **GitHub Releases for deployment triggers** — Instead of manually entering a tag in `workflow_dispatch`, create a GitHub Release → automatically triggers deploy. Creates a clear audit trail of all releases.

2. **Add a staging environment** — Even with one VPS, run a staging instance using a separate compose project name:
   ```bash
    # Staging
    docker compose --env-file .env.docker -p stage -f docker-compose.yml -f docker-compose.prod.yml up -d
    # Production
    docker compose --env-file .env.docker -p prod -f docker-compose.yml -f docker-compose.prod.yml up -d
   ```

3. **Trivy fs-mode vulnerability scan** — Add as a non-blocking CI job (scan source tree, report CRITICAL/HIGH as SARIF). See `plan.md_updated.md` §Stage D (D1).

4. **pip-audit for Python dependency vulnerabilities** — Add as a CI job scanning `uv.lock`. Verify Python 3.14 support first. See `plan.md_updated.md` §Stage D (D3).

5. **gitleaks + `.gitleaks.toml`** — Secret detection in CI to catch accidental commits. See `plan.md_updated.md` §Stage D (D5).

6. **zizmor workflow linting** — GitHub Actions workflow security linting. See `plan.md_updated.md` §Stage D (D6).

7. **Dependabot** — Weekly auto-updates for `github-actions` + `docker` ecosystems. See `plan.md_updated.md` §Stage D (D4).

8. **`--dist worksteal` (if xdist ≥ 3.8)** — Better test load balancing. ⚠️ **Requires updating `test_docs_ci_parity.py`** — `loadgroup` is intentional for FSM-pinned bot tests. See `plan.md_updated.md` §13 (Modern Best Practices #7).

9. **GitHub Actions build cache** — Add `cache-from: type=gha` alongside the existing GHCR registry cache in the CI build job. See `plan.md_updated.md` §Stage B (B1).

> **Do NOT rename compose files.** The original prep-guide §Forward-looking §3 proposed renaming `docker-compose.*.yml` → `compose.*.yaml`. This is **stale and should not be done** — all existing tooling (Makefile, overrides, CI, docs) depends on the legacy names. See `plan.md_updated.md` §12.4 (Architecture Constraints) and the [Compose Name Corrections](#c5-compose-file-name-corrections) section above.

---

## 11. Quick Reference

### GitHub Secrets (5 secrets — server access + host verification only)

| Name | Source |
|------|--------|
| `SERVER_HOST` | VPS IP address |
| `SERVER_USER` | `deploy` |
| `SERVER_SSH_KEY` | Private key from `~/.ssh/vps_deploy_bazuna` |
| `SERVER_PORT` | `22` |
| `SERVER_FINGERPRINT` | SSH host key SHA256 fingerprint (captured in §[A4b](#a4b-capture-the-ssh-host-fingerprint-security-hardening)) |

> **Note:** `SERVER_HOST`, `SERVER_USER`, and `SERVER_PORT` are not secrets (public configuration). They *can* be stored as GitHub Actions **Variables** instead of Secrets for better audit transparency; keeping them as Secrets is also acceptable. Only `SERVER_SSH_KEY` and `SERVER_FINGERPRINT` are genuinely sensitive.

### VPS `.env.docker` variables (23 variables — app secrets live here only)

| Variable | Source |
|----------|--------|
| `DJANGO_SECRET_KEY` | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | Your domain + localhost |
| `POSTGRES_USER` | `bazuna_user` |
| `POSTGRES_DB` | `bazuna_db` |
| `POSTGRES_PASSWORD` | `openssl rand -base64 32` |
| `REDIS_URL` | `redis://redis:6379/0` (Docker internal) |
| `BOT_USERNAME` | Your bot's username (without @) |
| `BOT_TOKEN` | From `@BotFather` |
| `SITE_URL` | Your production URL (no trailing slash) |
| `IMMEDIATE_ALERTS_ENABLED` | `false` |
| `TLS_CERT_PATH` | `/etc/nginx/certs` (or `/opt/mko_bazuna/certs`) |
| `PLAUSIBLE_HOST` | Empty to disable, or your Plausible instance |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | `openssl rand -base64 24` |
| `ADMIN_TELEGRAM_ID` | Your numeric Telegram ID |
| `SEED_USERS` | `10` (demo data) |
| `SEED_ADS` | `600` (demo data) |
| `REGISTRY` | `ghcr.io` |
| `REPOSITORY` | `manicko/mko_bazuna` |
| `IMAGE_TAG` | Derived as `sha-<COMMIT_SHA>` at build time via `git rev-parse --short HEAD` (see §C4, `deploy.yml` template) |
| `FIX_PERMISSIONS` | `0` (auto-on when `DEBUG=True`) |
| `SKIP_ENV_CHECK` | Empty (skip env-file validation) |

### SSH key pairs

| File | Location | Purpose |
|------|----------|---------|
| Private key | `~/.ssh/github_bazuna` (local) | GitHub authentication (clone, push) |
| Public key | `~/.ssh/github_bazuna.pub` (local) | GitHub → Settings → SSH and GPG keys |
| Private key | `~/.ssh/vps_deploy_bazuna` (local) | Becomes `SERVER_SSH_KEY` GitHub Secret |
| Public key | `~/.ssh/vps_deploy_bazuna.pub` (local) | Copied to VPS `~/.ssh/authorized_keys` |
| Host key fingerprint | VPS SSH host `SHA256:…` (captured in §A4b) | Becomes `SERVER_FINGERPRINT` GitHub Secret |

### Directory structure on VPS

```
/opt/mko_bazuna/
├── backups/                       # DB dumps (7-day retention + pre-deploy backups)
├── certs/                         # TLS: fullchain.pem, privkey.pem
├── media/                         # User-uploaded images
├── docker-compose.yml             # Copied from repo
├── docker-compose.prod.yml        # Copied from repo
├── docker/
│   └── nginx/
│       └── nginx.conf            # Copied from repo
├── .env.docker                    # Created in A7 (chmod 600)
└── .docker/                       # GHCR auth (created in §A11)
    └── config.json                # docker login ghcr.io credential (read-only PAT)
```

### Local development commands

| Command | Purpose |
|---------|---------|
| `make up` (or `.\Makefile.ps1 up`) | Start dev environment (hot-reload, port 8000) |
| `make test-db` (or `.\Makefile.ps1 test-db`) | Start test PostgreSQL (port 5433) |
| `make test` (or `.\Makefile.ps1 test`) | Run fast gate (skips nightly seed suite) |
| `make test-all` | Run full suite (includes seed, ~35 min) |
| `make test-recreate` | Fresh schema (`--create-db`) |
| `make lint` | Ruff check |
| `make typecheck` | Basedpyright |

### Deploy commands (run on VPS by deploy.yml)

```bash
set -e
DEPLOY_DIR="/opt/mko_bazuna"
cd "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR/backups"

export REGISTRY="ghcr.io"
export REPOSITORY="${REPOSITORY}"
export IMAGE_TAG="${IMAGE_TAG}"   # derived as sha-<COMMIT_SHA> from git rev-parse; e.g., sha-a913bc2

# Note: GHCR pull auth is via `docker login ghcr.io` (read-only PAT) configured on
# the VPS in §A11 — NOT via GITHUB_TOKEN. The GITHUB_TOKEN is runner-ephemeral.

# Save current tag for rollback
CURRENT_IMAGE=$(docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml ps --format "{{.Image}}" web 2>/dev/null || echo "")
PREVIOUS_TAG=$(echo "$CURRENT_IMAGE" | rev | cut -d: -f1 | rev || echo "")
echo "$PREVIOUS_TAG" > /opt/mko_bazuna/.previous_tag

# Pull latest images from GHCR
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml pull

# Backup database before migrations (host-side redirect to ./backups/ for §E3b restore)
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -F c \
  > "$DEPLOY_DIR/backups/pre_deploy_$(date +%Y%m%d_%H%M%S).dump"

# Run pre-deploy migrations (advisory lock, ID 100)
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate

# Start new containers (uses GHCR images via docker-compose.prod.yml:7-26 image overrides)
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d

# Clean up old images
docker image prune -f

echo "Deployment complete"
```

### Language support

The project supports three languages — **Russian / Bosnian / English** (Bosnian, not Montenegrin):

| StrEnum name | Locale code | Evidence |
|--------------|-------------|----------|
| `RUSSIAN` | `ru` | `base.py:69-73`; `Dockerfile:83` |
| `BOSNIAN` | `bs` | `apps/core/enums.py:192`; `Dockerfile:83` |
| `ENGLISH` | `en` | `base.py:69-73`; `Dockerfile:83` |

The launch **geography** is Montenegro, but the UI **language code** is Bosnian (`bs`). Updated docs use `ru`/`bs`/`en` consistently.

---

## 10. Rationale: `commit_sha` vs `image_tag` — why checkout must pin to the requested SHA

The original plan accepted an arbitrary `image_tag` input (e.g., `sha-a913bc2`) and used it to tag the built image. **This is a security and traceability hazard:**

1. **`actions/checkout@v4` checks out the workflow's trigger ref by default** — the branch selected at `workflow_dispatch` time (=`GITHUB_SHA`). It does **not** read the `image_tag` input and look up that commit.
2. If a user enters `sha-a913bc2` while triggering from a different commit, the workflow builds from the **wrong commit** but tags the image as `sha-a913bc2`.
3. The mismatched tag propagates to the VPS via `IMAGE_TAG=${{ github.event.inputs.image_tag }}`, so `docker compose pull` fetches an image labeled with one commit's SHA but built from another. Traceability is broken; rollback to a "known-good SHA" can redeploy the wrong binary.

**The fix** (implemented in §C4):
- The `workflow_dispatch` input is renamed `commit_sha` (the actual commit to build, not a tag label).
- `actions/checkout@v4` uses `ref: ${{ inputs.commit_sha }}` + `fetch-depth: 0` to fetch exactly that commit.
- The `IMAGE_TAG` is **derived** from the checked-out SHA via `git rev-parse --short HEAD` (step output), not trusted from user input.
- `docker/metadata-action@v5` uses `context: git` so both the `type=sha` tag and the `type=raw` tag reflect the actual checked-out commit.
- The deploy job reads `IMAGE_TAG` from `needs.build-and-push.outputs.IMAGE_TAG`, never from `github.event.inputs.*`.

This produces an ironclad chain: `commit A → checkout A → build A → GHCR sha-A → deploy sha-A`.

---

*End of `preparation-guide.md_updated.md`. This is a planning document — it does not modify any production code, workflows, or configuration. The only file to be created is `.github/workflows/deploy.yml` (§C4). All already-implemented items are marked ✅ Done.*
