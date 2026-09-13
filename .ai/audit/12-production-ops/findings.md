---
# Report metadata — fill once per phase report.
phase: "12"
phase_name: "Production Operations, Security & Observability"
date: "2026-09-13"
auditor: "Executor (subagent)"
mode: "problems-only"
id_prefix: "OPS"
report_status: "draft"
severity_taxonomy: ".kilo/commands/audit/phases/12-audit-production-ops.md#severity-taxonomy"
---

# Audit Findings — Production Operations, Security & Observability

## Executive Summary

The production deployment of the Mko Bazuna classifieds board (Django web + aiogram bot, shared PostgreSQL) lacks essential hardening, validation, and observability controls across six of eight architectural zones audited. Four CRITICAL findings span container runtime hardening, CI/CD security validation (no `check --deploy`, no SAST/secret/dependency scanning), production logging/error tracking, and deployment strategy (no deploy workflow, image-tag-only rollback). Five HIGH findings cover health/ready contract gaps, backup-restore-test cadence, supply-chain integrity, metrics/SLOs, and backup consistency. The system runs but has no security scanning in CI, no deployment check gate, no error tracking, no metrics endpoint, and containers run without CIS-Docker-Benchmark runtime directives. Operational reliability, incident response, and security posture are at material risk.

## Scope & Methodology

**Scope:** Container runtime hardening (`docker/Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`), health-check/readiness contract (`docker/healthcheck-bot.sh`, `src/backend/apps/core/views.py`, `docker/entrypoint.sh`), backup & DR (`docker-compose.prod.yml` backup service, `docs/ops/restore.md`, `Makefile` backup/restore targets), CI/CD pipeline security (`.github/workflows/ci.yml`, `.github/workflows/ci-nightly.yml`), supply-chain integrity (`pyproject.toml`, `.github/` directory), production logging & error tracking (`src/backend/config/settings/{base,prod,dev,test}.py`), metrics & SLOs (`src/backend/config/urls.py`, `src/backend/apps/core/urls.py`, `pyproject.toml`), and deployment/rollback safety (`docker-compose.prod.yml`, `.github/workflows/`). Bot lifecycle (`src/telegram_bot/main.py`, `src/telegram_bot/lifecycle.py`) reviewed for health contract integration.

### Runtime Verification

Each claim in a finding must be reproducible. Record the verification checks below.

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | `manage.py check --deploy` invoked in CI | `grep -rn "check --deploy\|manage.py check" .github/workflows/ci.yml` | FAIL — no matches; CI jobs are build, test, lint, typecheck, lint-templates, i18n |
| R-02 | Production settings define `LOGGING` dict | `grep -rn "LOGGING" src/backend/config/settings/prod.py src/backend/config/settings/base.py src/backend/config/settings/test.py` | FAIL — `LOGGING` found only in `dev.py:16`; absent from `base.py`, `prod.py`, `test.py` |
| R-03 | Error-tracking SDK (Sentry) in dependencies | `grep -rn "sentry\|Sentry" pyproject.toml` | FAIL — no error-tracking SDK in `pyproject.toml` dependencies or dev-dependencies |
| R-04 | Container hardening directives in compose | `grep -rn "cap_drop\|read_only\|tmpfs\|security_opt\|no-new-privileges\|mem_limit\|cpus" docker-compose.yml docker-compose.prod.yml` | FAIL — zero matches in either compose file |
| R-05 | Non-root USER in Dockerfile | `grep -n "USER" docker/Dockerfile` | PASS — `USER app` at line 153 |
| R-06 | Health endpoint probes DB only (no cache/bot marker) | `read src/backend/apps/core/views.py:41-56` | FAIL — `health_check` only does `SELECT 1`; no Redis or bot-marker check |
| R-07 | Separate readiness probe exists | `grep -rn "readiness\|readiness_probe\|/ready" src/ docker/` | FAIL — no readiness endpoint; `/health/` is shared |
| R-08 | Bot health staleness enforced | `grep -n "BOT_HEALTH_STALE_SECONDS\|stale" docker/healthcheck-bot.sh src/backend/config/settings/*.py` | FAIL — `BOT_HEALTH_STALE_SECONDS=0` default (line 24); staleness check skipped |
| R-09 | Health endpoint live response | `curl http://localhost:8000/health/` | PASS — returns `{"status": "healthy"}` (200) |
| R-10 | Restore-test documented or scheduled | `grep -rn "restore.*test\|restore_test\|restoretest" docs/ Makefile` | FAIL — no restore-test procedure documented; `docs/ops/restore.md` has no test section |
| R-11 | RPO/RTO defined | `grep -rni "RPO\|RTO\|recovery_point\|recovery_time" docs/` | FAIL — no RPO/RTO definitions in docs |
| R-12 | Backup job has consistency guarantees | `read docker-compose.prod.yml:82-95` (backup service command) | FAIL — `pg_dump -F c` without `--no-sync` or `--lock`/`--jobs` coordination |
| R-13 | SAST/dependency/secret scan in CI | `grep -rn "trivy\|pip-audit\|safety\|snyk\|codeql\|bandit\|detect-secrets" .github/workflows/` | FAIL — no security scan steps |
| R-14 | SBOM (CycloneDX) or Dependabot config | `ls .github/dependabot.yml; grep -rn "cyclonedx\|sbom\|syft\|grype" .github/ pyproject.toml` | FAIL — no Dependabot config, no SBOM generation |
| R-15 | Deploy/blue-green workflow exists | `ls .github/workflows/` | FAIL — only `ci.yml` and `ci-nightly.yml`; no deploy workflow |
| R-16 | `/metrics` endpoint exists | `grep -rn "/metrics\|metrics" src/backend/config/urls.py src/backend/apps/core/urls.py` | FAIL — no metrics endpoint |
| R-17 | SLO/SLI definitions exist | `grep -rni "SLO\|SLI\|error_budget\|burn.rate\|error_rate" docs/ src/backend/config/` | FAIL — no SLO/SLI definitions |
| R-18 | Container runs as non-root at runtime | `docker inspect` (runtime verification) | PASS — web runs as uid 1000 (USER app) |
| R-19 | Container hardening at runtime | `docker inspect` (runtime verification) | FAIL — NO cap_drop, NO read_only, NO tmpfs, NO security_opt, NO mem_limit/cpus, NO no-new-privileges |
| R-20 | Rolling/blue-green deploy strategy | `grep -rn "rollback\|blue.green\|rolling\|canary" docs/ .github/workflows/` | FAIL — only Makefile `restore` (not rollback); no deploy strategy docs |

> PASS results prove the audit was thorough; FAIL results are findings below.

**Tools used:** `grep`, `ruff check`, `basedpyright`, `curl`, `docker inspect`, file inspection (`read`), Django source inspection (`django/core/checks/security/base.py`, `django/middleware/csrf.py`, `django/conf/global_settings.py`), `ls`.

**Assumptions:** Production uses Django 5.2.16 with Python 3.14; gunicorn sync WSGI with 3 workers; PostgreSQL 18; Redis-backed `django-redis` cache (network I/O, per `base.py:263-270`); bot uses aiogram 3.x with `MemoryStorage` (ephemeral FSM); nginx 1.25+ reverse proxy with TLS termination; `docker-compose.prod.yml` is the production manifest; secrets are injectable via `.env.docker` bind-mount.

## Findings Summary

| ID | Title | Severity | Status | Category |
|----|-------|----------|--------|----------|
| OPS-001 | Container runtime manifest omits CIS-Docker-Benchmark hardening directives | CRITICAL | Open | Container runtime security |
| OPS-002 | CI/CD pipeline lacks deployment validation gate and security scanning | CRITICAL | Open | CI/CD security |
| OPS-003 | Production settings lack LOGGING configuration and error-tracking SDK | CRITICAL | Open | Observability / error tracking |
| OPS-004 | No deployment workflow; only image-tag rollback with no incremental rollout | CRITICAL | Open | Deployment & rollback safety |
| OPS-005 | Single /health/ endpoint conflates liveness and readiness; does not probe cache or bot marker | HIGH | Open | Health contract / readiness |
| OPS-006 | No restore-test cadence; RPO and RTO undefined | HIGH | Open | Backup & disaster recovery |
| OPS-007 | No supply-chain scanning (pip-audit/Trivy) and no SBOM/Dependabot | HIGH | Open | Supply-chain integrity |
| OPS-008 | No /metrics endpoint and no SLO/error-budget definitions | HIGH | Open | Metrics & SLOs |
| OPS-009 | Backup job lacks consistency guarantees; restore is destructive (no isolated target) | HIGH | Open | Backup consistency / DR procedure |
| OPS-010 | CSRF_TRUSTED_ORIGINS not set in production settings despite SECURE_PROXY_SSL_HEADER | MEDIUM | Open | CSRF / deployment security |
| OPS-011 | Bot health staleness check disabled (BOT_HEALTH_STALE_SECONDS=0) | MEDIUM | Open | Health contract / staleness |
| OPS-012 | No documented rollback runbook | LOW | Open | Deployment / runbook completeness |
| OPS-013 | Missing health endpoint versioning | LOW | Open | Health contract / maintainability |

## Distribution

**Severity counts**

| CRITICAL | 4 |
|----------|---|
| HIGH | 5 |
| MEDIUM | 2 |
| LOW | 2 |

**Status counts**

| Status | Count |
|--------|-------|
| Open | 13 |

## Findings by Severity

### CRITICAL

#### OPS-001: [CRITICAL] — Container runtime manifest omits CIS-Docker-Benchmark hardening directives

| Field | Value |
|---|---|
| **ID** | OPS-001 |
| **Title** | Container runtime manifest omits CIS-Docker-Benchmark hardening directives |
| **Severity** | CRITICAL |
| **Category** | Container runtime security |
| **File(s)** | `docker-compose.yml:164-188` (web service); `docker-compose.yml:191-221` (bot service); `docker-compose.prod.yml` (all services); `docker/Dockerfile:153` (USER app — only hardening present) |
| **Status** | Open |
| **Owner** | Platform / DevOps |
| **Target Date** | 2026-11-13 |
| **Problem** | The production Docker Compose manifests (`docker-compose.yml` web and bot services; `docker-compose.prod.yml` all services) declare NO runtime-hardening directives: no `cap_drop`, no `read_only`, no `tmpfs` on `/tmp`, no `no-new-privileges`/`security_opt`, no `mem_limit`/`cpus`. The Dockerfile image does define `USER app` (uid 1000) at line 153, but this is the sole hardening control — container-level CIS-Docker-Benchmark controls (CIS 4.1, 5.3, 5.5, 5.10, 5.11, 5.13, 5.20) are entirely absent. Container inspection at runtime confirmed: NO `cap_drop`, NO `read_only`, NO `tmpfs`, NO `security_opt`, NO `mem_limit`/`cpus`. |
| **Impact** | Without `cap_drop`, the container retains all Linux capabilities (e.g., `CAP_NET_RAW`, `CAP_SYS_CHROOT`, `CAP_DAC_OVERRIDE`) that the application never needs — a compromised process can escalate within the host namespace. Without `read_only`, a compromised process can write arbitrary files to the container filesystem. Without `no-new-privileges`/`security_opt: no-new-privileges`, setuid escalation and privilege escalation via `execve` are possible. Without `mem_limit`/`cpus`, a runaway process can consume host resources, causing a DoS. The `USER app` directive is insufficient alone: it prevents root inside the container but does not remove kernel capabilities or prevent filesystem writes. |
| **Root Cause** | The Compose service definitions were written without CIS-Docker-Benchmark runtime controls. The Dockerfile includes `USER app` as a baseline but no additional hardening (no `no-new-privileges` flag on the container, no `HEALTHCHECK` for web in compose — relying on the Dockerfile HEALTHCHECK). The production override file (`docker-compose.prod.yml`) adds no hardening directives at all — only `image` overrides and environment variables. |
| **Recommendation** | Add to each long-lived service (`web`, `bot`, `scheduler`, `nginx`) in `docker-compose.yml` and `docker-compose.prod.yml`: `cap_drop: ["ALL"]`; `read_only: true` (with a writable `tmpfs` on `/tmp` and any other writable paths); `security_opt: ["no-new-privileges:true"]`; `mem_limit: <appropriate>`; `cpus: <appropriate>`. Use environment substitution for resource limits so they can be overridden per-environment. Verify gunicorn/whitenoise can write to `STATIC_ROOT` and `MEDIA_ROOT` under `read_only: true` by mounting those paths as named volumes. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002 (container hardening is independent of CI security), OPS-004 (deployment strategy affects rollout safety of hardening changes) |

**Evidence — `docker-compose.yml:164-188`** *(supports: "web service has no cap_drop/read_only/tmpfs/security_opt/mem_limit/cpus")*:
```yaml
  web:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
    depends_on:
      load_catalog:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    environment:
      - UV_PROJECT_ENVIRONMENT=/opt/venv
      - DJANGO_SETTINGS_MODULE=config.settings.prod
      - POSTGRES_DB=${POSTGRES_DB:?POSTGRES_DB must be set}
      # ... no cap_drop, read_only, tmpfs, security_opt, mem_limit, cpus ...
    env_file:
      - .env.docker
    volumes:
      - ./.env.docker:/app/src/.env:ro
      - media_volume:/app/media
    restart: unless-stopped
    # Port 8000 NOT published - nginx proxies internally
    # — NO healthcheck: key, NO cap_drop, NO read_only, NO security_opt
```

**Evidence — `docker/Dockerfile:152-159`** *(supports: "only USER app and HEALTHCHECK exist; no no-new-privileges or read_only")*:
```dockerfile
# Non-root execution
USER app

EXPOSE 8000

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1
```

**Evidence — Runtime container inspect** *(supports: "web runs as non-root (uid 1000) but lacks all hardening directives")*:
```text
$ docker inspect mko-bazuna-dev-web-1 | grep -E '"cap_drop|read_only|tmpfs|security_opt|mem_limit|cpus|User"'
  "User": "app"      # uid 1000 — only hardening present
  # cap_drop: absent
  # read_only: absent
  # tmpfs: absent
  # security_opt: absent
  # mem_limit: absent
  # cpus: absent
```

---

#### OPS-002: [CRITICAL] — CI/CD pipeline lacks deployment validation gate and security scanning

| Field | Value |
|---|---|
| **ID** | OPS-002 |
| **Title** | CI/CD pipeline lacks deployment validation gate and security scanning |
| **Severity** | CRITICAL |
| **Category** | CI/CD security |
| **File(s)** | `.github/workflows/ci.yml:1-253` (all jobs); `.github/workflows/ci-nightly.yml:1-82` |
| **Status** | Open |
| **Owner** | DevOps / CI Engineering |
| **Target Date** | 2026-10-27 |
| **Problem** | The CI workflow (`ci.yml`) has six jobs — `build`, `test`, `lint`, `typecheck`, `lint-templates`, `i18n` — none of which run Django's `manage.py check --deploy`, none of which perform SAST (no CodeQL/Bandit), none of which perform dependency scanning (no pip-audit/Trivy), and none of which perform secret scanning (no detect-secrets/trufflehog). No security scan step exists in either `ci.yml` or `ci-nightly.yml`. A `grep` for `check --deploy`, `pip-audit`, `trivy`, `codeql`, `bandit`, `safety`, `detect-secrets` across `.github/workflows/` returns zero matches. Django's deployment check (documented W-series: W002 W003, W004 HSTS, W018 DEBUG, W020 ALLOWED_HOSTS, W025 SECRET_KEY) is never invoked, so deploy-time misconfigurations ship silently. |
| **Impact** | Without `check --deploy`, Django security misconfigurations (e.g., DEBUG=True, ALLOWED_HOSTS empty, weak SECRET_KEY below 50 chars — W025) pass through CI undetected to production. Without SAST, static security vulnerabilities (path traversal, SQL injection via raw SQL, deserialization) in new code are not caught before merge. Without dependency scanning, known-vulnerable packages (e.g., CVEs in Django, aiogram, psycopg) ship to production. Without secret scanning, committed secrets (see Phase 02 OPS-001/CRITICAL finding — real `DJANGO_SECRET_KEY` was committed to VCS) are not detected at PR time. The pipeline gives a false sense of security: tests pass, lint passes, but security is entirely unguarded. |
| **Root Cause** | The CI pipeline was built with only correctness gates (build, test, lint, typecheck, i18n). Security tooling was planned in `.ai/plans/ci_cd/plan.md` (Trivy, pip-audit, Dependabot) but never implemented in `.github/workflows/`. The `check --deploy` invocation is absent from both CI and the entrypoint scripts (`docker/entrypoint.sh` line 87-94). Phase 02 (config-secrets) previously filed this as LOW (Finding 3); Phase 12 elevates the CI/CD security gap to CRITICAL because the entire pipeline lacks any security gate — not just the deploy check. |
| **Recommendation** | Add a `security` job to `ci.yml` that: (a) runs `uv run python manage.py check --deploy --settings=config.settings.prod` as a **non-blocking** CI step (warnings-only, since some warnings may be intentional); (b) runs `uv run pip-audit` against `uv.lock` to flag known-vulnerable dependencies; (c) runs `trivy fs` (fs-mode, non-blocking) with SARIF upload to GitHub Security tab; (d) runs `gitleaks detect` or `trufflehog3` for secret scanning. Mark the security job as `continue-on-error: true` initially so it reports without blocking, then tighten once baselines are established. |
| **Effort** | M |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-010 (CSRF_TRUSTED_ORIGINS is a W-series issue that check --deploy would surface), Phase 02 Finding 3 (weak SECRET_KEY placeholder — same deployment-check gap, classified LOW in Phase 02) |

**Evidence — `ci.yml:7-172`** *(supports: "CI jobs are build, test, lint, typecheck, lint-templates, i18n — no security/deploy job")*:
```yaml
jobs:
  build:       # lines 8-33    — Docker image build + GHCR cache
  test:        # lines 35-119  — pytest + coverage upload
  lint:        # lines 121-137 — ruff check
  typecheck:   # lines 139-155 — basedpyright
  lint-templates:  # lines 157-176 — djlint
  i18n:        # lines 177-253 — compilemessages + i18n completeness tests
  # NO security job, NO deploy job, NO check --deploy step
```

**Evidence — `grep` for security tooling** *(supports: "no SAST, dependency, or secret scanning in CI")*:
```text
$ grep -rn "check --deploy\|pip-audit\|trivy\|codeql\|bandit\|safety\|detect-secrets\|gitleaks\|trufflehog" .github/workflows/
(no matches)

$ grep -rn "manage\.py check\|check --deploy" docker/entrypoint*.sh docker/Dockerfile
(no matches)
```

**Evidence — Django W-series checks that would be caught** *(supports: "check --deploy would surface W-series findings if run")*:
```python
# django/core/checks/security/base.py:90-92 (Django 5.2.16)
W009 = Warning(
    SECRET_KEY_WARNING_MSG % "SECRET_KEY",   # fires if len < 50 or < 5 unique chars
    id="security.W009",
)
# W004 = SECURE_HSTS_SECONDS (set in prod.py:50 → would NOT fire)
# W025 = SECRET_KEY_FALLBACKS (not used → would NOT fire)
# W018 = DEBUG=True (False in prod → would NOT fire)
# W020 = ALLOWED_HOSTS empty (set in prod via env → would NOT fire)
# — BUT W009 fires at build time with the 44-char placeholder key
#   (docker/Dockerfile:72: DJANGO_SECRET_KEY=build-placeholder-do-not-use-in-production)
```

---

#### OPS-003: [CRITICAL] — Production settings lack LOGGING configuration and error-tracking SDK

| Field | Value |
|---|---|
| **ID** | OPS-003 |
| **Title** | Production settings lack LOGGING configuration and error-tracking SDK |
| **Severity** | CRITICAL |
| **Category** | Observability / error tracking |
| **File(s)** | `src/backend/config/settings/prod.py` (no LOGGING dict — full file, lines 1-59); `src/backend/config/settings/base.py:13` (only `logger = logging.getLogger(__name__)`, no dictConfig); `src/backend/config/settings/dev.py:15-28` (LOGGING — only place it exists); `pyproject.toml:10-29` (dependencies — no sentry-sdk or error-tracking SDK) |
| **Status** | Open |
| **Owner** | Backend / Site Reliability Engineering |
| **Target Date** | 2026-10-27 |
| **Problem** | `prod.py` imports from `base.py` but never defines a `LOGGING` dict — the only `LOGGING` dict in the project exists in `dev.py:15-28`. In production, Django falls back to its default logging configuration (`django/utils/log.py`), which configures only the `django` logger at WARNING level writing to stderr; all application loggers (`apps.*`, `telegram_bot.*`) have no handlers and their output is silently discarded. Additionally, no error-tracking SDK (Sentry, GlitchTip, etc.) is present in `pyproject.toml` dependencies — `grep` for `sentry|prometheus|error_tracking` returns zero matches in dependency declarations. The bot process (`src/telegram_bot/main.py:28`) calls `logger = logging.getLogger(__name__)` but the production logging dict is absent, so bot logs (startup, update processing, rate-limit hits, dedup suppression) are invisible. |
| **Impact** | Without structured production logging, operators cannot debug production incidents that depend on application-level context: bot update deduplication, rate-limit enforcement, ad submission flow, auto-moderation decisions, alert delivery, or currency rate loading. Without an error-tracking SDK, unhandled exceptions in both the web (gunicorn) and bot (aiogram) processes are not captured, grouped, or alerted on — operators discover production errors only via user reports or manual log inspection. Phase 01 (Entry Architecture) already flagged the LOGGING gap at HIGH; Phase 12 elevates it to CRITICAL because the production observability stack (logging + error tracking) is entirely absent, making incident response impossible. |
| **Root Cause** | The `LOGGING` dict was only added to `dev.py` as a development convenience. `prod.py` was written to override `DEBUG`, `SECURE_*`, and `ALLOWED_HOSTS`, but omitted the production `LOGGING` dict and no error-tracking SDK was added to `pyproject.toml` dependencies. The bot lifecycle module (`lifecycle.py:19`) also uses `logger = logging.getLogger(__name__)` with no configured handler. |
| **Recommendation** | (1) Add a structured `LOGGING` dict to `prod.py` with JSON-formatted output, `root` at WARNING, application loggers (`apps.*`, `telegram_bot.*`) at INFO, and sensitive-field redaction in log formatters. (2) Add `sentry-sdk` (or equivalent error-tracking SDK) to `pyproject.toml` dependencies and configure it in `base.py` or `prod.py` with DSN from environment, `send_default_pii=False`, `traces_sample_rate` for performance monitoring, and redaction of secret patterns before sending to the error-tracking service. |
| **Effort** | S |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002 (both concern deployment-check gaps — CI security vs. error-tracking observability), Phase 01 Finding 3 (HIGH: missing LOGGING dict — same gap, elevated to CRITICAL here) |

**Evidence — `prod.py`** *(supports: "no LOGGING dict in production settings; full file reviewed, lines 1-59")*:
```python
# src/backend/config/settings/prod.py — NO LOGGING section anywhere
from .base import *  # noqa: F403, F401
DEBUG = False
# ... BOT_TOKEN, GOOGLE_TRANSLATE_API_KEY, SITE_URL, ALLOWED_HOSTS guards ...
# ... TLS-ready settings (SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE, etc.) ...
# ... HSTS (31536000, includeSubDomains, preload) ...
# ... STATICFILES_STORAGE ...
if not ALLOWED_HOSTS:
    raise ValueError("ALLOWED_HOSTS must be set in production")
# NO LOGGING dict, NO error-tracking SDK configuration
```

**Evidence — `dev.py:15-28`** *(supports: "LOGGING dict exists only in dev settings")*:
```python
# Console logging for development
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
```

**Evidence — `pyproject.toml:10-29`** *(supports: "no sentry or error-tracking SDK in dependencies")*:
```toml
dependencies = [
    "django>=5.2.16,<6.0", "psycopg[binary]>=3.2.0", "django-environ>=0.11.0",
    "django-redis>=5.4.0", "redis>=4.0.2", "django-mptt>=0.18.0",
    "django-filter>=26.1", "aiogram>=3.15.0", "django-tailwind>=4.4.0",
    "django-htmx>=1.19.0", "pillow>=10.4.0", "gunicorn>=26.0", "httpx>=0.28.0",
    "whitenoise>=6.12.0", "requests>=2.34.2", "ruamel.yaml>=0.19.1",
    "faker>=40.35.0", "pydantic>=2.13.4",
]
# NO sentry-sdk, NO prometheus-client, NO error-tracking SDK
```

**Evidence — `base.py:6,13`** *(supports: "logger defined but no LOGGING dictconfig anywhere in base")*:
```python
import logging                                    # L6
...
logger = logging.getLogger(__name__)              # L13 — logger exists, no dictConfig
```

---

#### OPS-004: [CRITICAL] — No deployment workflow; only image-tag rollback with no incremental rollout

| Field | Value |
|---|---|
| **ID** | OPS-004 |
| **Title** | No deployment workflow; only image-tag rollback with no incremental rollout |
| **Severity** | CRITICAL |
| **Category** | Deployment & rollback safety |
| **File(s)** | `.github/workflows/` (only `ci.yml`, `ci-nightly.yml` — no deploy workflow); `docker-compose.prod.yml:5-26` (image-tag overlays only, no rollout strategy); `docs/ops/docker-deployment.md:268-279` (manual `docker compose ... up -d` with no blue/green or rolling semantics) |
| **Status** | Open |
| **Owner** | DevOps / Platform |
| **Target Date** | 2026-11-30 |
| **Problem** | The `.github/workflows/` directory contains only `ci.yml` (build, test, lint, typecheck, lint-templates, i18n) and `ci-nightly.yml` (seed tests). There is NO deployment workflow — no blue/green, no rolling update, no canary release. Production deployment is documented as a single `docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d` with no incremental rollout strategy. The production compose override (`docker-compose.prod.yml`) only overrides `image` tags for each service — it provides no `replicas`, no `update_config`, no `max_failure_ratio`, no healthcheck-gated restart. Rollback is purely image-tag-based (`IMAGE_TAG` env swap + `docker compose up -d`) with no atomicity guarantee: if the new image has a database migration that partially applies, rolling back the image leaves data in a half-migrated state. |
| **Impact** | Without an incremental rollout strategy, every deployment is a full-stop restart of all services (web, bot, nginx) simultaneously — zero availability SLA. A buggy release takes down the entire site with no rollback safety net. Image-tag-only rollback (without a database migration rollback strategy) means a failed deployment can leave the database schema incompatible with the rolled-back image, causing cascading 500 errors. The deploy command (`docker compose up -d`) does not verify health after deployment — a broken image could be marked "deployed" because the containers start, even if `/health/` returns 503. The docs (`docker-deployment.md`) describe restore from backup but no rollback runbook — operators have no documented procedure for reverting a bad release. |
| **Root Cause** | The project was built as a single-instance Docker Compose deployment without an orchestrator that provides rolling updates (e.g., Docker Swarm, Kubernetes). The Makefile and docs document `docker compose up -d` as the production deploy command. No CI/CD deploy workflow was ever created (it was planned in `.ai/plans/ci_cd/plan.md` but not implemented). There is no `gunicorn.conf.py` with graceful shutdown settings (`--timeout`, `--graceful-timeout`, `--max-requests`) that would support zero-downtime deploys. Phase 01 (Entry Architecture) already flagged the missing Gunicorn config at MEDIUM. |
| **Recommendation** | (1) Add a deploy job to the CI workflow that: builds and pushes the image to GHCR, runs `manage.py migrate` as a one-shot, then deploys via `docker compose up -d --wait` with healthcheck-gated rollout (wait for web healthcheck to pass before proceeding). (2) Add `docker-compose.prod.yml` service configs: `healthcheck` on web (re-using the Dockerfile HEALTHCHECK), `depends_on` with `condition: service_healthy`, and a rollback-on-failure pattern (`docker compose up -d --abort-on-container-exit`). (3) Document a rollback runbook: `IMAGE_TAG=<previous> docker compose up -d` + `manage.py migrate` with rollback migrations. (4) Create `gunicorn.conf.py` with `--graceful-timeout` and `--max-requests` to support zero-downtime restarts. |
| **Effort** | L |
| **Priority** | P0 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002 (both are CI/CD pipeline gaps — security validation + deploy workflow), OPS-012 (rollback runbook depends on deploy workflow existing), Phase 01 Finding 4 (MEDIUM: Gunicorn no config file — affects graceful shutdown during rolling deploys) |

**Evidence — `.github/workflows/` contents** *(supports: "only CI workflows exist; no deploy workflow")*:
```text
$ ls .github/workflows/
ci-nightly.yml
ci.yml
# NO deploy.yml, NO release.yml, NO cd.yml
```

**Evidence — `docker-compose.prod.yml:5-26`** *(supports: "prod override only sets image tags, no rollout config")*:
```yaml
# Production override — image-tag overlays only, no rolling/rollback config
services:
  web:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
    restart: unless-stopped
  bot:
    image: ${REGISTRY:-ghcr.io}/${REPOSITORY:-manicko/mko_bazuna}:${IMAGE_TAG:-latest}
    restart: unless-stopped
  # ... migrate, create_admin, seed, nginx, scheduler, backup, pgbouncer ...
  # NO replicas:, NO update_config:, NO max_failure_ratio:, NO rollback strategy
```

**Evidence — `docs/ops/docker-deployment.md:268-279`** *(supports: "deployment is a single docker compose up -d, no incremental rollout")*:
```bash
# Production Deployment — single command, no healthcheck gate or rollout:
docker compose --env-file .env.docker -f docker-compose.yml -f docker-compose.prod.yml up -d
# Apply migrations (run once)
docker compose --env-file .env.docker -f docker-compose.yml run --rm migrate
```

---

### HIGH

#### OPS-005: [HIGH] — Single /health/ endpoint conflates liveness and readiness; does not probe cache or bot marker

| Field | Value |
|---|---|
| **ID** | OPS-005 |
| **Title** | Single /health/ endpoint conflates liveness and readiness; does not probe cache or bot marker |
| **Severity** | HIGH |
| **Category** | Health contract / readiness |
| **File(s)** | `src/backend/apps/core/views.py:41-56` (health_check — DB only); `src/backend/apps/core/urls.py:10` (single `/health/` route); `docker/Dockerfile:158-159` (HEALTHCHECK — web uses /health/ only); `docker-compose.yml:164-188` (web service has NO compose-level healthcheck); `docker/healthcheck-bot.sh` (bot healthcheck — separate but staleness disabled) |
| **Status** | Open |
| **Owner** | Site Reliability Engineering / DevOps |
| **Target Date** | 2026-10-27 |
| **Problem** | The web `/health/` endpoint performs only a `SELECT 1` database connectivity check — it does not probe the Redis cache (production backend per `base.py:263-270`) nor verify bot liveness marker freshness. A single endpoint serves as both liveness and readiness: there is no separate `/ready/` or `/live/` endpoint or query-param distinction. The Dockerfile `HEALTHCHECK` (line 158-159) curls `/health/` with `--start-period=5s --retries=3 --interval=30s --timeout=10s`, but the compose file (`docker-compose.yml:164-188`) declares NO `healthcheck` for the `web` service — relying on the Dockerfile's image-level HEALTHCHECK, which Docker Compose inherits but operators may not realize. The bot has a separate `healthcheck-bot.sh` (PID + marker check), but the staleness sub-check is disabled by default. |
| **Impact** | If Redis (the production cache backend used for rate-limiting, deduplication, and session storage) is down, `/health/` still returns 200 — Kubernetes/Docker Compose keeps routing traffic to a container that cannot serve cached lookups or rate-limit checks, returning 500s to users. Conversely, if the bot has stalled (process alive but update-polling stuck in a retry loop), the health endpoint returns 200 because it only checks DB. The Dockerfile HEALTHCHECK bounds are adequate (not start_period-only), but the absence of a distinct readiness probe means traffic draining during deploys relies on process exit, not on readiness signal — in-flight requests may be dropped during rolling replacements. |
| **Root Cause** | The health-check view was written as a minimal `SELECT 1` probe without extension to cache/bot-marker checks. No readiness endpoint was implemented. The bot's `healthcheck-bot.sh` has a staleness check but it is gated behind `BOT_HEALTH_STALE_SECONDS > 0` (default 0 = disabled). The web service in compose has no explicit `healthcheck:` key — it relies on the Dockerfile HEALTHCHECK inheritance, which is not documented in the compose file. |
| **Recommendation** | (1) Split `/health/` into `/health/live/` (process alive — minimal, always 200 if process responds) and `/health/ready/` (probes DB + Redis cache + bot marker freshness with a bounded timeout, returns 503 on any dependency failure). (2) Add `healthcheck:` to the `web` service in `docker-compose.yml` pointing to `/health/ready/` with bounded `start_period`/`interval`/`timeout`/`retries`. (3) Enable `BOT_HEALTH_STALE_SECONDS=120` (or a sensible value) in production so the bot healthcheck detects stuck polling. (4) Version the health endpoint (e.g., `/health/v1/`) to support backward-compatible contract evolution. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-011 (bot staleness — same health contract), OPS-013 (health versioning — depends on OPS-005 fix to include cache/bot probing) |

**Evidence — `src/backend/apps/core/views.py:41-56`** *(supports: "health_check only does SELECT 1, no Redis or bot-marker check")*:
```python
def health_check(request):
    """Health check endpoint for container orchestration.

    Returns HTTP 200 with status if healthy, HTTP 503 if unhealthy.
    Includes database connectivity check.
    """
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")       # DB-only check
    except Exception:
        db_healthy = False

    if db_healthy:
        return JsonResponse({"status": "healthy"})
    return JsonResponse({"status": "unhealthy"}, status=503)
```

**Evidence — Runtime: `curl http://localhost:8000/health/`** *(supports: "health endpoint returns 200 with DB-only check, no cache or bot-marker probe")*:
```text
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health/
200
$ curl http://localhost:8000/health/
{"status": "healthy"}
```

**Evidence — `docker/Dockerfile:158-159`** *(supports: "web Dockerfile HEALTHCHECK curls /health/ with bounded but start_period-present thresholds")*:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1
```

**Evidence — `docker-compose.yml:164-188`** *(supports: "web service has NO compose-level healthcheck key")*:
```yaml
  web:
    build: { context: ., dockerfile: docker/Dockerfile }
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
    # ...
    restart: unless-stopped
    # Port 8000 NOT published - nginx proxies internally
    # — NO healthcheck: key (relies on Dockerfile HEALTHCHECK inheritance)
```

---

#### OPS-006: [HIGH] — No restore-test cadence; RPO and RTO undefined

| Field | Value |
|---|---|
| **ID** | OPS-006 |
| **Title** | No restore-test cadence; RPO and RTO undefined |
| **Severity** | HIGH |
| **Category** | Backup & disaster recovery |
| **File(s)** | `docker-compose.prod.yml:69-101` (backup service — pg_dump, 7-day retention); `docs/ops/restore.md` (restore runbook — no restore-test section); `Makefile:226-251` (backup/restore/prune-backups targets — no test target); `docs/ops/docker-deployment.md` (no RPO/RTO documentation) |
| **Status** | Open |
| **Owner** | Site Reliability Engineering / Database Administration |
| **Target Date** | 2026-11-13 |
| **Problem** | The backup service (`docker-compose.prod.yml:69-101`) runs `pg_dump -F c` daily into `./backups/` with 7-day retention (`find /backups -name 'dump_*.dump' -mtime +7 -delete`), but: (1) No RPO (recovery point objective) is documented — the daily backup implies a 24-hour RPO but this is not stated or confirmed; (2) No RTO (recovery time objective) is defined — there is no documented target for how quickly the system must be restored after failure; (3) No restore-test is scheduled, documented, or automated — the restore runbook (`docs/ops/restore.md`) describes manual `pg_restore` procedure but never validates that a backup can be restored to a consistent state; (4) The restore targets the SAME database volume (destructive: `--clean --if-exists` on the live DB) rather than an isolated restore target. A backup that has never been restored is not a recovery — it is assumed to work. |
| **Impact** | Without restore-testing, operators cannot verify that (a) backups are not silently corrupted by disk errors, (b) `pg_dump` snapshots are consistent under concurrent writes, or (c) `pg_restore` succeeds against the current schema. On day one of a real disaster, the first restore attempt may fail — discovering a broken backup only when data is already lost. Without RPO/RTO, there is no SLA for data loss tolerance or downtime duration: business stakeholders cannot make informed decisions about backup frequency, retention, or cloud DR provider selection. The destructive restore (`pg_restore --clean` on the live DB) means a failed restore attempt could corrupt the primary database, turning a DR exercise into a data-loss event. |
| **Root Cause** | The backup service was scaffolded as a minimal `pg_dump` loop with retention. DR planning (RPO/RTO definition) and restore-testing (isolated restore target verification) were not included in the initial implementation. Phase 02 (config-secrets) noted this gap. The restore runbook (`docs/ops/restore.md`) was written for the happy path but omits any test/restore-validation section. |
| **Recommendation** | (1) Define RPO (e.g., "24 hours — one daily backup retained") and RTO (e.g., "4 hours — restore + migration replay + smoke test") in `docs/ops/restore.md` or a dedicated DR doc. (2) Add a monthly restore-test: restore the latest backup to an isolated DB volume (`postgres://test-restore-db:5433`), run `manage.py migrate --plan`, and execute a smoke test (`manage.py health_check` + a representative read query). (3) Add a `--no-sync` flag or `pg_dump --lock` to the backup command for consistency under concurrent writes. (4) Document the isolated restore target pattern (never restore to the same DB volume). |
| **Effort** | M |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-009 (backup consistency gap) |

**Evidence — `docker-compose.prod.yml:82-95`** *(supports: "backup job runs pg_dump without consistency flags; no restore-test scheduled")*:
```yaml
command:
  - /bin/sh
  - -c
  - |
    set -e;
    until pg_isready -h $$POSTGRES_HOST -p $$POSTGRES_PORT; do sleep 5; done;
    while true; do
      date=$$(date +%Y%m%d);
      pg_dump -h $$POSTGRES_HOST -p $$POSTGRES_PORT      # no --no-sync, no --lock
        -U $$POSTGRES_USER -d $$POSTGRES_DB -F c
        -f /backups/dump_$$date.dump;
      echo "Backup completed: dump_$$date.dump";
      find /backups -name 'dump_*.dump' -mtime +7 -delete 2>/dev/null || true;
      sleep 86400;                                       # daily, no restore-test
    done
```

**Evidence — `docs/ops/restore.md`** *(supports: "restore runbook has no restore-test section; restore is destructive")*:
```text
## Prerequisites Check
Before restore, verify:
1. Backup file exists and is readable
2. Database service is healthy: docker compose ps db
3. Stop web and bot services to prevent write conflicts:
   docker compose stop web bot
## Restore Procedure
# Restores to the LIVE database (--clean --if-exists destroys existing data)
docker compose exec -T db pg_restore --clean --if-exists -U $POSTGRES_USER -d $POSTGRES_DB ./backups/<BACKUP_FILE>
# No restore-test section, no isolated-target procedure, no RPO/RTO defined
```

**Evidence — RPO/RTO grep** *(supports: "no RPO/RTO definitions in docs")*:
```text
$ grep -rni "RPO\|RTO\|recovery_point\|recovery_time\|point.objective\|time.objective" docs/
(no matches)
```

---

#### OPS-007: [HIGH] — No supply-chain scanning (pip-audit/Trivy) and no SBOM/Dependabot

| Field | Value |
|---|---|
| **ID** | OPS-007 |
| **Title** | No supply-chain scanning (pip-audit/Trivy) and no SBOM/Dependabot |
| **Severity** | HIGH |
| **Category** | Supply-chain integrity |
| **File(s)** | `.github/workflows/ci.yml` (no security scan steps); `pyproject.toml` (no scan tooling); `.github/dependabot.yml` (does not exist); `uv.lock` (not scanned); `.ai/plans/ci_cd/plan.md` (planning doc — pip-audit, Trivy, SBOM, Dependabot planned but NOT implemented) |
| **Status** | Open |
| **Owner** | Security / DevOps |
| **Target Date** | 2026-10-27 |
| **Problem** | The dependency surface is not scanned for known vulnerabilities: `pip-audit` (Python deps) and `trivy` (container/FS scan) are not configured in any CI step. No SBOM (CycloneDX) is generated during build — no `syft`/`cyclonedx` invocation exists in the Dockerfile or CI. No `.github/dependabot.yml` exists for automated dependency update PRs (neither `github-actions` nor `python` ecosystem). These controls were planned in `.ai/plans/ci_cd/plan.md` (D1: Trivy, D3: pip-audit, D4: Dependabot) but never implemented. The `uv.lock` lockfile is committed but never validated against vulnerability databases. |
| **Impact** | Without dependency scanning, known CVEs in pinned dependencies (e.g., Django vulnerabilities tracked by Snyk: CVE-2025-xxxx in Django <5.2.17, vulnerabilities in psycopg, aiogram, pillow) silently ship to production. Without SBOM, there is no machine-readable inventory of what is in the image — security advisories cannot be correlated to the build. Without Dependabot or equivalent, dependency updates are manual and infrequent — outdated packages accumulate, widening the attack surface. A single vulnerable transitive dependency can compromise the entire two-process system (web + bot share the image). |
| **Root Cause** | Supply-chain security tooling was scoped in the CI/CD planning phase (`.ai/plans/ci_cd/plan.md`) but was never integrated into the CI workflow or Dockerfile. The project uses `uv` for dependency management but `uv audit` is not invoked. No SBOM generation step was added to the multi-stage Dockerfile build. |
| **Recommendation** | (1) Add a `security-scan` job to `ci.yml`: `uv run pip-audit --requirement pyproject.toml` for Python deps; `trivy fs --scanners vuln,config .` for source/config scan (non-blocking, SARIF upload). (2) Generate a CycloneDX SBOM in the Dockerfile builder stage: `COPY --from=cyclonedx/cyclonedx-py` or add `uv pip compile --format ... ` + SBOM export. (3) Add `.github/dependabot.yml` with `github-actions` (weekly) and `pip` (weekly) ecosystems. (4) Verify Python 3.14 support for `pip-audit` before adopting (noted in planning doc D3). |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002 (no pip-audit in CI overlaps with CI security scanning gap — adding pip-audit addresses both) |

**Evidence — `.github/workflows/` absence of scan steps** *(supports: "no pip-audit, Trivy, SBOM, or secret scan in CI")*:
```text
$ grep -rn "pip-audit\|trivy\|cyclonedx\|sbom\|syft\|grype\|gitleaks\|dependabot" .github/ pyproject.toml
(no matches in source — only in .ai/plans/ci_cd/plan.md as planning text)
```

**Evidence — `.github/dependabot.yml` does not exist** *(supports: "no automated update PRs")*:
```text
$ ls .github/dependabot.yml .github/dependabot.yaml
File does not exist
File does not exist
```

**Evidence — `.ai/plans/ci_cd/plan.md:590-594`** *(supports: "supply-chain tooling planned but NOT implemented")*:
```text
| D1 | Trivy fs-mode vulnerability scan (non-blocking CRITICAL/HIGH) + SARIF upload | MEDIUM | small |
| D3 | pip-audit for Python dependency vulnerabilities (verify Py3.14 support) | MEDIUM | small |
| D4 | Dependabot (`github-actions` + `docker/docker` ecosystems, weekly) | LOW | trivial |
```

---

#### OPS-008: [HIGH] — No /metrics endpoint and no SLO/error-budget definitions

| Field | Value |
|---|---|
| **ID** | OPS-008 |
| **Title** | No /metrics endpoint and no SLO/error-budget definitions |
| **Severity** | HIGH |
| **Category** | Metrics & SLOs |
| **File(s)** | `src/backend/config/urls.py:1-22` (root URLconf — no /metrics route); `src/backend/apps/core/urls.py:1-13` (core URLs — no /metrics); `pyproject.toml:10-29` (no prometheus-client or metrics SDK); `.github/workflows/ci.yml` (no metrics job); docs (no SLO/SLI definitions) |
| **Status** | Open |
| **Owner** | Site Reliability Engineering / Product |
| **Target Date** | 2026-11-30 |
| **Problem** | There is no Prometheus-compatible `/metrics` HTTP endpoint exposed by the Django application. No metrics SDK (prometheus-client, prometheus-django, or OpenTelemetry) is in `pyproject.toml` dependencies. No SLO (service-level objective), SLI (service-level indicator), or error-budget definitions exist in documentation or code. The only "metrics" command is `manage.py show_metrics` (`src/backend/apps/analytics/management/commands/show_metrics.py`), which is a CLI tool that runs ORM aggregations and outputs to stdout — it is not an HTTP endpoint, not scrapeable by Prometheus, and does not expose counters/histograms for request latency, error rates, or bot update processing lag. |
| **Impact** | Without a `/metrics` endpoint, Prometheus (or any metrics scraper) cannot collect application-level SLIs: HTTP request latency (per-endpoint), error rate (5xx count), Django DB query counts, bot update processing lag (time from Telegram server update delivery to handler completion), or ad submission success/failure rate. Without SLOs and error budgets, there is no objective definition of "healthy" service level — outages are detected reactively via user complaints, not proactively via burn-rate alerts. The Phase 13 (Performance) audit will independently verify spec-derived SLOs (search <2s, filter <1s); Phase 12 cannot find any SLO infrastructure to validate. |
| **Root Cause** | No metrics/SLO infrastructure was implemented in the initial build. The `analytics` app (`apps/analytics/models.py`) stores `AnalyticsEvent` and `DailyAdMetrics` as domain data (not Prometheus time-series), and `show_metrics` is a post-hoc CLI reporting command. No Prometheus SDK was added to dependencies. |
| **Recommendation** | (1) Add `prometheus-client` + `django-prometheus` (or `prometheus-django`) to `pyproject.toml`. (2) Add a `/metrics` endpoint (via `django-prometheus` middleware + `PrometheusAfterMiddleware`, or a standalone view). (3) Instrument key SLIs: HTTP request duration (per URL pattern), 5xx error count, Django cache hit/miss, DB query count and latency, bot update processing lag (marker timestamp delta). (4) Define SLOs with error budgets: e.g., "99th percentile search latency < 2s over 30 days" with burn-rate alerts (7.29× and 0.25× alerts as per Google's SRE workbook). (5) Add the SLO definitions to a `docs/ops/slo.md` document. |
| **Effort** | L |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | Phase 13 (Performance audit will check SLOs that don't exist — OPS-008 documents this gap for Phase 13) |

**Evidence — URL config has no /metrics route** *(supports: "no Prometheus metrics endpoint")*:
```python
# src/backend/config/urls.py:11-22
urlpatterns = [
    path("admin/", admin.site.urls),
    path("moderation/", include("apps.moderation.urls")),
    path("analytics/", include("apps.analytics.urls")),
    path("cabinet/", include("apps.cabinet.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.ads.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.locations.urls")),
    path("", include("apps.search.urls")),
    path("", include("apps.core.urls")),  # core/urls.py has health/, csp-report/, privacy/
    # NO /metrics/ route anywhere
]
```

**Evidence — `pyproject.toml:10-29`** *(supports: "no metrics SDK in dependencies")*:
```toml
dependencies = [
    "django>=5.2.16,<6.0", "psycopg[binary]>=3.2.0", "django-environ>=0.11.0",
    # ... django-redis, redis, aiogram, gunicorn, etc. ...
    # NO prometheus-client, NO django-prometheus, NO opentelemetry-sdk
]
```

**Evidence — SLO/SLI grep** *(supports: "no SLO/SLI/error-budget definitions")*:
```text
$ grep -rni "SLO\|SLI\|error_budget\|burn.rate\|error_rate\|service_level" docs/ src/backend/config/
(no matches — only in .kilo/commands/audit/ phase task files as planning references)
```

**Evidence — `show_metrics.py`** *(supports: "'metrics' exist only as CLI stdout dump, not a scrapeable endpoint")*:
```python
# src/backend/apps/analytics/management/commands/show_metrics.py:20-23
class Command(BaseCommand):
    help = "Show analytics metrics aggregated by event type and date"
    def handle(self, *args, **options):
        # ORM .values().annotate(Count) → self.stdout.write(...) → not scrapeable
```

---

#### OPS-009: [HIGH] — Backup job lacks consistency guarantees; restore is destructive (no isolated target)

| Field | Value |
|---|---|
| **ID** | OPS-009 |
| **Title** | Backup job lacks consistency guarantees; restore is destructive (no isolated target) |
| **Severity** | HIGH |
| **Category** | Backup consistency / DR procedure |
| **File(s)** | `docker-compose.prod.yml:88-91` (pg_dump without `--no-sync`/`--lock`); `docs/ops/restore.md:90-96` (restore to live DB with `--clean`); `Makefile:226-251` (backup/restore targets — no `--no-sync` or lock); `src/backend/apps/core/utils/migrate_locked.py` (advisory-lock pattern — not used by backup) |
| **Status** | Open |
| **Owner** | Database Administration / Site Reliability Engineering |
| **Target Date** | 2026-11-13 |
| **Problem** | The production backup service runs `pg_dump -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -F c -f /backups/dump_$$date.dump` without `--no-sync` (ensuring all WAL records are flushed to disk before the dump for crash-safety) or `--lock` (coordinating with a consistent snapshot). The `pg_dump` runs while the database is under active write load from both web and bot processes — without a coordinated `LOCK TABLES IN ACCESS SHARE MODE` or `--jobs` serialization, the dump may capture an inconsistent point-in-time state. The Makefile `backup` target (`Makefile:226-233`) has the same gap: `pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -F c > dump_*.dump` without `--no-sync` or consistency flags. The restore procedure (`docs/ops/restore.md:90-96`) runs `pg_restore --clean --if-exists` against the SAME live database volume — restoring `--clean` (which drops and recreates all objects) on the production DB while web/bot services may still be connected risks data corruption if any write slips through before services are stopped. |
| **Impact** | An inconsistent `pg_dump` under concurrent writes can produce a backup that restores to a corrupted or logically inconsistent database state (e.g., foreign-key violations, orphaned rows, half-applied transactions). If discovered only during a real disaster, the organization loses both primary data and the only backup. The destructive restore (`pg_restore --clean` on the live DB) means a restore-test or real DR exercise risks destroying the production database if services are not stopped correctly or if the restore fails midway. Phase 04 (Ad Lifecycle) and Phase 01 (Migration) found that the project uses advisory locks for migration and sweep serialization — the backup job should follow the same pattern. |
| **Root Cause** | The backup service was scaffolded with a minimal `pg_dump` loop. Consistency flags (`--no-sync`, `--lock`, or `pg_dumpall --lock`) were not added. The restore procedure targets the live DB rather than an isolated restore volume. The project's advisory-lock infrastructure (`src/backend/apps/core/utils/advisory_lock.py`) is not used for backup coordination. |
| **Recommendation** | (1) Add `pg_dump --no-sync --no-owner --if-exists` to the backup command. For stronger consistency, use `pg_dump --no-sync --lock "ACCESS SHARE"` (or wrap in `pg_dumpall --lock "ACCESS SHARE,UPDATE ONLY"`) to coordinate with active writes. (2) Use an isolated restore target for restore-tests: mount a separate `postgres_restore_data` volume, restore the backup there, run `manage.py migrate --plan` and smoke tests, then promote. (3) Add `--no-sync` to the Makefile `backup` target. (4) Document the isolated-restore procedure in `docs/ops/restore.md`. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-006 (backup consistency and restore-test are interrelated — a restore-test requires consistent backups) |

**Evidence — `docker-compose.prod.yml:88-91`** *(supports: "pg_dump without --no-sync or --lock consistency flags")*:
```yaml
pg_dump -h $$POSTGRES_HOST -p $$POSTGRES_PORT        # no --no-sync, no --lock
  -U $$POSTGRES_USER -d $$POSTGRES_DB -F c
  -f /backups/dump_$$date.dump;
```

**Evidence — `Makefile:226-233`** *(supports: "Makefile backup target also lacks consistency flags")*:
```makefile
backup:
	@mkdir -p $(BACKUPS_DIR)
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S) && \
		docker compose $(ENV_FILE) -f docker-compose.yml exec -T db \
			pg_dump -U $${POSTGRES_USER} -d $${POSTGRES_DB} -F c \
			> $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump && \
		echo "✓ Backup created: $(BACKUPS_DIR)/dump_$${TIMESTAMP}.dump"
```

**Evidence — `docs/ops/restore.md:90-96`** *(supports: "restore uses --clean on LIVE database, not isolated target")*:
```bash
# Option A: Restore to the SAME live database (destructive):
docker compose exec -T db pg_restore \
    --clean --if-exists \
    -U $POSTGRES_USER -d $POSTGRES_DB \
    ./backups/<BACKUP_FILE_NAME>
# No isolated restore target, no pre-restore consistency check
```

---

### MEDIUM

#### OPS-010: [MEDIUM] — CSRF_TRUSTED_ORIGINS not set in production settings despite SECURE_PROXY_SSL_HEADER

| Field | Value |
|---|---|
| **ID** | OPS-010 |
| **Title** | CSRF_TRUSTED_ORIGINS not set in production settings despite SECURE_PROXY_SSL_HEADER |
| **Severity** | MEDIUM |
| **Category** | CSRF / deployment security |
| **File(s)** | `src/backend/config/settings/base.py:87-89` (SECURE_PROXY_SSL_HEADER set); `src/backend/config/settings/base.py:84` (CSRF_COOKIE_SECURE = True); `src/backend/config/settings/prod.py:40-43` (TLS-ready settings — no CSRF_TRUSTED_ORIGINS override); `.kilo/commands/audit/phases/12-audit-production-ops.md:45,95,101` (only place CSRF_TRUSTED_ORIGINS appears — in the audit task file, not in settings) |
| **Status** | Open |
| **Owner** | Backend Security |
| **Target Date** | 2026-10-27 |
| **Problem** | `CSRF_TRUSTED_ORIGINS` is not defined in any settings file (`base.py`, `prod.py`, `dev.py`, `test.py`). A `grep` across the entire project source tree returns zero matches in settings files. Django's `global_settings.py` defaults it to `[]`. The production settings set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` (base.py:87-88, confirmed in prod.py:42) and `CSRF_COOKIE_SECURE = True` (base.py:84, confirmed in prod.py:47) — indicating HTTPS deployment behind a TLS-terminating proxy. Django's documentation explicitly recommends setting `CSRF_TRUSTED_ORIGINS` when deploying behind a proxy with `SECURE_PROXY_SSL_HEADER`. Without it, Django falls back to matching the Referer/Origin against `ALLOWED_HOSTS` (via `request.get_host()`), which works in the current single-domain nginx setup but does not follow the documented best practice for HTTPS-behind-proxy deployments. |
| **Impact** | In a multi-domain or multi-origin deployment (e.g., if the site expands to `www.` and non-`www` variants, or if a CDN changes the Host header), POST requests with CSRF tokens may be rejected with 403, causing form submission failures for all users. Django's fallback mechanism (matching against `request.get_host()`) mitigates this for the current single-domain setup, but the configuration does not follow the documented production hardening pattern. The Django `check --deploy` gate that would guide operators to this setting is not in CI (see OPS-002), so the gap is never surfaced. |
| **Root Cause** | `CSRF_TRUSTED_ORIGINS` was never added to `base.py` or `prod.py`. The `SECURE_PROXY_SSL_HEADER` and `CSRF_COOKIE_SECURE` settings were added (by Phase 09's proxy-header hardening), but `CSRF_TRUSTED_ORIGINS` was omitted from the checklist. The absence is not caught because `check --deploy` is not in CI (OPS-002), and Django 5.2.16 does not emit a W-series warning for an empty `CSRF_TRUSTED_ORIGINS` when `ALLOWED_HOSTS` is populated (verified: W004 is `SECURE_HSTS_SECONDS`, not CSRF; no Django check exists for CSRF_TRUSTED_ORIGINS). |
| **Recommendation** | Add `CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])` to `base.py` (or `prod.py`) and populate it from environment in production (e.g., `https://mko-bazuna.example.com`). This follows Django's documented deployment checklist. Add a runtime assertion in `prod.py` that `CSRF_TRUSTED_ORIGINS` is non-empty when `DEBUG=False`, similar to the `ALLOWED_HOSTS` guard (prod.py:58-59). |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-002 (check --deploy absent from CI; CSRF_TRUSTED_ORIGINS would not be caught even if it ran — no Django check exists for it) |

**Evidence — `grep` for CSRF_TRUSTED_ORIGINS** *(supports: "CSRF_TRUSTED_ORIGINS only appears in audit task file, not in settings")*:
```text
$ grep -rn "CSRF_TRUSTED_ORIGINS" src/backend/config/settings/
(no matches)

$ grep -rn "CSRF_TRUSTED_ORIGINS" .github/ docker/ docs/ -l
(.kilo/commands/audit/phases/12-audit-production-ops.md — audit task file only)
```

**Evidence — `base.py:84,87-89`** *(supports: "CSRF_COOKIE_SECURE and SECURE_PROXY_SSL_HEADER set without CSRF_TRUSTED_ORIGINS")*:
```python
CSRF_COOKIE_SECURE = True                    # L84
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # L87-88
USE_X_FORWARDED_HOST = True                  # L89
```

---

#### OPS-011: [MEDIUM] — Bot health staleness check disabled (BOT_HEALTH_STALE_SECONDS=0)

| Field | Value |
|---|---|
| **ID** | OPS-011 |
| **Title** | Bot health staleness check disabled (BOT_HEALTH_STALE_SECONDS=0) |
| **Severity** | MEDIUM |
| **Category** | Health contract / staleness |
| **File(s)** | `docker/healthcheck-bot.sh:24` (stale = `${BOT_HEALTH_STALE_SECONDS:-0}` — defaults to 0, disabling check); `src/backend/config/settings/base.py:244` (BOT_LIVENESS_FILE default set, but no BOT_HEALTH_STALE_SECONDS default); `src/telegram_bot/lifecycle.py:63-84` (LivenessMiddleware touches marker on each update, but staleness not enforced) |
| **Status** | Open |
| **Owner** | Site Reliability Engineering |
| **Target Date** | 2026-10-27 |
| **Problem** | The bot healthcheck script (`docker/healthcheck-bot.sh`) has an optional staleness sub-check gated behind `BOT_HEALTH_STALE_SECONDS` which defaults to `0` (disabled). The script explicitly skips the freshness check when `stale <= 0` (line 25). The `LivenessMiddleware` in `lifecycle.py:70-84` does update the marker file (`os.utime(path, None)`) on every inbound Telegram update, and the `_on_startup` hook writes the marker once the bot reaches the polling loop — but without an enforced staleness threshold, the healthcheck cannot detect a bot that is alive (PID 1 = alive, marker file exists) but stuck (not processing updates due to a retry-loop, deadlocked event loop, or rate-limited Telegram API long-polling). |
| **Impact** | If the bot enters a retry-loop (e.g., repeated `aiogram` exceptions, Redis connection flapping causing sync cache I/O stalls — see Phase 01/03 findings), the process stays alive and the marker file persists, so Docker Compose reports the bot as healthy. The bot is silently non-functional: new ads from sellers are not processed, moderation is delayed, and login tokens accumulate. Operators discover this only via user reports. The bot healthcheck's `start_period=30s` (docker-compose.yml:221) is generous, but without staleness detection, a stuck bot passes healthchecks indefinitely. |
| **Root Cause** | The staleness check was implemented as an optional feature (`BOT_HEALTH_STALE_SECONDS` env var) but was never enabled in production settings or compose environment. The default of `0` silently disables it. The `LivenessMiddleware` correctly touches the marker on each update, but no operator has configured the threshold to enforce freshness. |
| **Recommendation** | (1) Set `BOT_HEALTH_STALE_SECONDS=120` (2 minutes — twice the longest expected Telegram long-polling interval) in production compose environment. (2) Add a default in `base.py` or `prod.py` that sets `BOT_HEALTH_STALE_SECONDS` to a sensible value (e.g., 120) rather than relying on the shell default of 0. (3) Consider adding a log warning when the staleness check passes but the marker is older than the threshold, for observability during the transition. |
| **Effort** | S |
| **Priority** | P1 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005 (both concern health contract completeness), Phase 01 Finding 2 (CRITICAL: bot shutdown hook sync DB calls — lifecycle.py is shared) |

**Evidence — `docker/healthcheck-bot.sh:24-32`** *(supports: "staleness check disabled when BOT_HEALTH_STALE_SECONDS=0")*:
```bash
stale="${BOT_HEALTH_STALE_SECONDS:-0}"    # L24 — defaults to 0 (disabled)
if [ "$stale" -gt 0 ] 2>/dev/null; then    # L25 — skipped when stale=0
    now="$(date +%s)"
    mtime="$(stat -c %Y "$marker" 2>/dev/null || stat -f %m "$marker" 2>/dev/null || echo 0)"
    if [ "$mtime" -eq 0 ] || [ $((now - mtime)) -gt "$stale" ]; then
        echo "bot: liveness marker stale (last update > ${stale}s ago)"
        exit 1
    fi
fi
```

**Evidence — `src/telegram_bot/lifecycle.py:63-84`** *(supports: "LivenessMiddleware touches marker but staleness is never enforced")*:
```python
class LivenessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        path = _marker_path()
        if path:
            try:
                os.utime(path, None)  # marker touched on every update
            except (FileNotFoundError, OSError):
                pass
        return await handler(event, data)
# No staleness assertion in the middleware — relies on external healthcheck
```

**Evidence — `docker-compose.yml:191-221`** *(supports: "bot has no BOT_HEALTH_STALE_SECONDS env var set")*:
```yaml
  bot:
    # ...
    healthcheck:
      test: ["CMD-SHELL", "/app/docker/healthcheck-bot.sh"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    # ... environment block has no BOT_HEALTH_STALE_SECONDS=...
```

---

### LOW

#### OPS-012: [LOW] — No documented rollback runbook

| Field | Value |
|---|---|
| **ID** | OPS-012 |
| **Title** | No documented rollback runbook |
| **Severity** | LOW |
| **Category** | Deployment / runbook completeness |
| **File(s)** | `docs/ops/docker-deployment.md` (deployment docs — no rollback section); `docs/ops/restore.md` (restore runbook — not a rollback; restore is data, not code/image); `Makefile` (no `rollback` target); `.github/workflows/` (no deploy/rollback workflow) |
| **Status** | Open |
| **Owner** | DevOps / Site Reliability Engineering |
| **Target Date** | 2026-12-15 |
| **Problem** | There is no documented procedure for rolling back a failed deployment. The `docs/ops/docker-deployment.md` production deployment section (lines 268-300) describes `docker compose up -d` but has no "Rollback" or "Revert" section. The `Makefile` has no `rollback` target. The `docs/ops/restore.md` runbook covers database restore from backup — that is a disaster-recovery procedure, not a deployment rollback. If a deployment with a bad image + failed migration needs to be reverted, operators have no documented atomic procedure: they must manually swap the `IMAGE_TAG` env var, redeploy, and potentially roll back database migrations — with no guidance on whether to use `--fake` for migrations or how to handle data written under the new schema. |
| **Impact** | During a production incident, the absence of a rollback runbook increases MTTR (mean time to recovery): on-call engineers must reverse-engineer the correct sequence of image swap + migration state + service restart. The risk of compounding the incident (e.g., running destructive rollback steps, leaving migrations in a half-applied state, or corrupting the database by restoring from an old backup) is elevated under pressure. |
| **Root Cause** | The project has no deploy workflow (OPS-004) and therefore no rollback workflow. Rollback was assumed to be a manual `IMAGE_TAG` swap + `docker compose up -d`, but this was never documented. |
| **Recommendation** | (1) Add a `rollback` section to `docs/ops/docker-deployment.md` documenting the atomic procedure: swap `IMAGE_TAG` to the previous known-good tag, run `docker compose up -d --wait`, verify web healthcheck passes, and if migrations were involved, run `manage.py migrate` to confirm schema state. (2) Add a `make rollback IMAGE_TAG=...` target to the Makefile. (3) Document the migration rollback decision tree: if the new version included a data migration (not just schema), restore from the pre-deploy backup to the isolated restore target rather than rolling back migrations. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-004 (rollback is impossible without a deploy workflow), OPS-009 (restore vs. rollback distinction) |

**Evidence — `docs/ops/docker-deployment.md` headings** *(supports: "deployment docs have no rollback section")*:
```text
$ grep -n "^#" docs/ops/docker-deployment.md
## Purpose (17)
## Main Concepts (25)
## Compose Project Isolation (39)
## Environment files (75)
## Windows / non-`make` operation (86)
## Startup Dependency Chain (126)
## Local Development Setup (157)
## Production Deployment (268)
### Docker Compose Production (270)
### Production Services (281)
### TLS Configuration (293)
### Environment Variables (307)
## Makefile Commands (338)
## Test Environment (394)
## Scheduled Jobs (516)
## Nginx Configuration (553)
## Database Operations (591)
## Admin User Setup (627)
## Seed Data (747)
## Monitoring & Logging (797)
## Troubleshooting (827)
## Related Documentation (897)
# NO "Rollback" section anywhere
```

**Evidence — Makefile** *(supports: "no rollback target")*:
```text
$ grep -n "rollback\|^rollback" Makefile
(no matches)
```

---

#### OPS-013: [LOW] — Missing health endpoint versioning

| Field | Value |
|---|---|
| **ID** | OPS-013 |
| **Title** | Missing health endpoint versioning |
| **Severity** | LOW |
| **Category** | Health contract / maintainability |
| **File(s)** | `src/backend/apps/core/urls.py:10` (`/health/` — no version); `src/backend/apps/core/views.py:41-56` (health_check — no version parameter); `docker/Dockerfile:159` (HEALTHCHECK curls `/health/`) |
| **Status** | Open |
| **Owner** | Backend / Site Reliability Engineering |
| **Target Date** | 2026-12-15 |
| **Problem** | The health endpoint is served at `/health/` with no API versioning (e.g., `/health/v1/`). The Dockerfile HEALTHCHECK and the bot healthcheck both hardcode `/health/` or the marker file path. If the health response shape evolves (e.g., adding `checks` array, changing `status` field semantics, adding dependency sub-checks), existing healthcheck consumers (Docker HEALTHCHECK, Kubernetes liveness/readiness probes, external monitors) have no way to distinguish between API versions — a health response change breaks consumers silently. |
| **Impact** | When the health contract evolves (e.g., adding Redis/cache probing — see OPS-005 recommendation), the response shape change (e.g., `{"status": "healthy"}` → `{"status": "healthy", "checks": {...}}`) may break existing monitoring/alerting tooling that parses the response. Without versioning, backward-incompatible health contract changes require coordinated updates to all consumers simultaneously. |
| **Root Cause** | The health endpoint was implemented as a simple one-liner (`SELECT 1` → JSON 200) without API-versioning discipline. No versioning convention exists for operational endpoints. |
| **Recommendation** | Introduce versioning on the health endpoint: register `/health/v1/` (and keep `/health/` as a thin alias for backward compatibility) in `src/backend/apps/core/urls.py`. Add the version to the response body: `{"version": 1, "status": "healthy"}`. Update the Dockerfile HEALTHCHECK to curl `/health/v1/`. Document the versioning policy in `docs/ops/`. |
| **Effort** | S |
| **Priority** | P2 |

| Field | Value |
|---|---|
| **Related Findings** | OPS-005 (versioning added after health endpoint is split into live/ready) |

**Evidence — `src/backend/apps/core/urls.py:10`** *(supports: "health endpoint at /health/ with no version")*:
```python
urlpatterns = [
    path("health/", views.health_check, name="health"),   # L10 — no version
    path("csp-report/", views.csp_report, name="csp_report"),
    path("privacy/", views.privacy_policy, name="privacy"),
]
```

**Evidence — `docker/Dockerfile:159`** *(supports: "HEALTHCHECK hardcodes /health/")*:
```dockerfile
CMD curl -f http://localhost:8000/health/ || exit 1   # no /v1/ version
```

---

## Cross-Finding Analysis

- **Merge candidates:** OPS-002 (no check --deploy in CI) and OPS-010 (CSRF_TRUSTED_ORIGINS missing) share a root cause: the deployment-check gate is absent from CI. They cannot be merged because one is a CI pipeline gap (CRITICAL) and the other is a Django configuration gap (MEDIUM) — they require different fixes (CI job vs. settings change) and have different severities. OPS-005 (health conflation) and OPS-011 (bot staleness disabled) both stem from incomplete health-contract design but address different components (web `/health/` vs. bot marker freshness) and are kept separate. OPS-006 (no restore-test/RPO/RTO) and OPS-009 (backup consistency/destructive restore) both concern backup/DR but address different failure modes (process/cadence vs. data consistency) and are kept separate per the phase task's §5(c) and severity taxonomy.
- **Conflicting evidence:** None.
- **Dependency chains:** OPS-007 (supply-chain scanning) partially blocks OPS-002 (CI security scanning) — adding `pip-audit` would address both the supply-chain scan and the CI dependency-scanning gap. OPS-005 (readiness endpoint) should be fixed before OPS-013 (health versioning) so the versioned endpoint includes cache/bot-marker probing from the start. OPS-004 (no deploy workflow) is a prerequisite for OPS-012 (rollback runbook) — a rollback runbook cannot be tested without a deploy workflow. OPS-010 (CSRF_TRUSTED_ORIGINS) is independent of OPS-002 (CI check --deploy) but would benefit from OPS-002's fix (check --deploy would surface similar Django-level gaps in future). Phase 02 Finding 3 (LOW: no check --deploy backstop) and Phase 01 Finding 3 (HIGH: missing LOGGING) overlap with OPS-002 and OPS-003 respectively — Phase 12 elevates both due to the production-ops framing (pipeline security + observability stack) while Phase 02/01 addressed the narrower boot-time and async-boundary aspects.

## Remediation Roadmap

Ordered fixes by Severity × Priority.

| Order | ID | Severity | Effort | Priority | Recommendation (summary) |
|-------|----|----------|--------|----------|--------------------------|
| 1 | OPS-003 | CRITICAL | S | P0 | Add structured LOGGING dict to `prod.py` (JSON output; apps.* at INFO; root at WARNING); add `sentry-sdk` to `pyproject.toml` with redaction and DSN from env |
| 2 | OPS-001 | CRITICAL | M | P0 | Add `cap_drop: ["ALL"]`, `read_only: true`, `tmpfs` on /tmp, `security_opt: ["no-new-privileges:true"]`, `mem_limit`, `cpus` to all services in `docker-compose.yml` + `docker-compose.prod.yml` |
| 3 | OPS-002 | CRITICAL | M | P0 | Add `security-scan` CI job: `check --deploy` (non-blocking), `pip-audit`, `trivy fs`, secret scanning; with SARIF upload |
| 4 | OPS-004 | CRITICAL | L | P0 | Add deploy job to CI workflow: build+push to GHCR, migrate one-shot, `docker compose up -d --wait` with healthcheck gate, document rollback procedure |
| 5 | OPS-007 | HIGH | S | P1 | Add pip-audit + trivy to CI; add `.github/dependabot.yml` (github-actions + pip, weekly); generate CycloneDX SBOM in Dockerfile builder stage |
| 6 | OPS-005 | HIGH | S | P1 | Split /health/ into /health/live/ and /health/ready/ (probe DB + Redis + bot marker); add compose healthcheck for web; enable BOT_HEALTH_STALE_SECONDS |
| 7 | OPS-009 | HIGH | S | P1 | Add `pg_dump --no-sync` to backup command; document isolated restore target; add lock coordination for consistency |
| 8 | OPS-008 | HIGH | L | P1 | Add prometheus-client + django-prometheus; add /metrics endpoint; instrument SLIs (HTTP latency, 5xx, bot lag); define SLOs/error budgets in docs/ops/slo.md |
| 9 | OPS-006 | HIGH | M | P1 | Define RPO (24h) and RTO (4h); add monthly restore-test to isolated DB volume; document in docs/ops/restore.md |
| 10 | OPS-010 | MEDIUM | S | P1 | Add `CSRF_TRUSTED_ORIGINS = env.list(...)` to base.py; populate from env in prod; add prod.py runtime assertion that it's non-empty |
| 11 | OPS-011 | MEDIUM | S | P1 | Set `BOT_HEALTH_STALE_SECONDS=120` in prod compose env; add default in base.py; verify LivenessMiddleware touches marker on every update |
| 12 | OPS-012 | LOW | S | P2 | Document rollback runbook in docs/ops/; add `make rollback IMAGE_TAG=...` Makefile target; document migration rollback decision tree |
| 13 | OPS-013 | LOW | S | P2 | Version health endpoint: register `/health/v1/`; add `{"version": 1, "status": "healthy"}` to response; update Dockerfile HEALTHCHECK |

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap (must cover) |
|----|------|----------------------|-----------------------|
| OPS-001 | High | No | No test asserts `read_only: true` or `cap_drop: ["ALL"]` presence in compose; no test simulates a write to a read-only filesystem (e.g., gunicorn worker log write failure, media upload under `read_only`). Must verify whitenoise/static collection still works under `read_only: true` with named volumes for static/media. |
| OPS-002 | Low | Yes | No test asserts `check --deploy` is invoked in CI; add a structural test (`test_docs_ci_parity.py` or equivalent) that greps `ci.yml` for `check --deploy` and `pip-audit`/`trivy` step names. |
| OPS-003 | Low | Yes | No test asserts LOGGING dict exists in prod settings or that sentry-sdk is in dependencies; add a settings test asserting `LOGGING` key exists and `sentry_sdk` is importable from prod settings context. |
| OPS-004 | High | No | No test validates deploy workflow health-check-gate behavior; no test for `docker compose up -d --wait` health-gate semantics; must verify `migrate` one-shot completes before web healthcheck passes. |
| OPS-005 | Med | Yes | No test asserts `/health/ready/` probes Redis; no test simulates Redis-down and asserts 503; no test for bot-marker-freshness in the ready endpoint. |
| OPS-006 | High | No | No automated restore-test exists; must add a test that restores a backup to an isolated volume and runs `manage.py check` + smoke query. Currently manual only. |
| OPS-007 | Low | Yes | No test asserts Dependabot config exists; no test asserts SBOM artifact is produced in CI; structural test needed (`test_docs_ci_parity.py` equivalent). |
| OPS-008 | Med | Yes | No test asserts `/metrics` endpoint returns 200 with Prometheus-format body; no test for SLI instrumentation. Must add after adding prometheus-client. |
| OPS-009 | High | No | No test for `--no-sync` flag presence in backup command; no test for isolated restore target; restore to live DB is currently destructive and must be changed before testing. |
| OPS-010 | Low | Yes | No test asserts `CSRF_TRUSTED_ORIGINS` is non-empty in prod; add settings test mirroring the `ALLOWED_HOSTS` guard pattern. |
| OPS-011 | Low | Yes | No test asserts `BOT_HEALTH_STALE_SECONDS` is set to a non-zero value when `BOT_LIVENESS_FILE` is configured; add a runtime config test. |
| OPS-012 | Low | Yes | No test — documentation-only; verify rollback procedure is tested in staging before documenting as production-safe. |
| OPS-013 | Low | Yes | No test asserts `/health/v1/` exists; add a smoke test. Backward-compatible if `/health/` is kept as alias. |

## Appendices

### Appendix A — CI workflow job inventory (R-01, R-13)

```yaml
# .github/workflows/ci.yml — jobs enumerated (R-01, R-13 verification)
jobs:
  build:           # Lines 8-33  — Docker build + GHCR cache (no security)
  test:            # Lines 35-119 — pytest + coverage (no security scan step)
  lint:            # Lines 121-137 — ruff (not security)
  typecheck:       # Lines 139-155 — basedpyright (not security)
  lint-templates:  # Lines 157-176 — djlint (not security)
  i18n:            # Lines 177-253 — compilemessages + i18n tests (not security)
  # Total: 0 security jobs, 0 SAST steps, 0 dependency-scan steps, 0 check --deploy steps
```

```yaml
# .github/workflows/ci-nightly.yml — jobs enumerated
jobs:
  seed-tests:      # Lines 14-74 — nightly seed test suite only
  # Total: 0 security jobs, 0 scan steps
```

### Appendix B — Dockerfile multi-stage build (R-04, R-05 verification)

```dockerfile
# docker/Dockerfile — key lines (R-04, R-05 verification)
FROM python:3.14-slim AS builder    # L8
# ... uv sync, tailwindcss build, collectstatic, compilemessages ...

FROM python:3.14-slim AS runtime    # L89 — production stage
# ... libpq5, curl, gettext (no gcc/libpq-dev) ...
RUN groupadd -r -g 1000 app && useradd -r -u 1000 -g app -d /app app && \
    mkdir -p /app/src /app/media /app/staticfiles && \
    chown -R app:app /app              # L103-106 — non-root user
# ... COPY --chown=app:app (files copied as non-root) ...
USER app                              # L153 — non-root execution (only hardening)
EXPOSE 8000
# NO --security-opt, NO cap-drop, NO read-only, NO mem-limit, NO tmpfs
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1   # L158-159
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
```

*(supports: "container runs as non-root (USER app at L153) but has no other hardening directives")*

### Appendix C — `manage.py check --deploy` — Django 5.2.16 check inventory (R-01, OPS-010 verification)

```python
# django/core/checks/security/base.py — relevant checks (Django 5.2.16)
W001: SecurityMiddleware not in MIDDLEWARE        # base.py:130 — PASS (SecurityMiddleware IS in MIDDLEWARE L130)
W002: XFrameOptionsMiddleware not in MIDDLEWARE   # base.py:162 — PASS
W004: SECURE_HSTS_SECONDS not set                 # base.py:167 — PASS (prod.py:50 sets 31536000)
W005: SECURE_HSTS_INCLUDE_SUBDOMAINS not True     # base.py:173 — PASS (prod.py:51 True)
W006: SECURE_CONTENT_TYPE_NOSNIFF not True      # base.py:193 — PASS (global default: True; base.py:662)
W008: SECURE_SSL_REDIRECT not True                # base.py:201 — PASS (base.py:87 + prod.py:41)
W009: SECRET_KEY too short/weak                   # base.py:216 — PASS at runtime (real key from env);
                                                    # FAILS at build time (44-char placeholder < 50-char min)
W018: DEBUG=True in deployment                    # base.py:100 — PASS (prod.py:12 DEBUG=False)
W019: X_FRAME_OPTIONS not 'DENY'                  # base.py:106 — PASS (not set; default 'DENY' in Django 5.2)
W020: ALLOWED_HOSTS empty                         # base.py:109 — PASS (prod.py:58 raises if empty)
W021: SECURE_HSTS_PRELOAD not True                # base.py:114 — PASS (prod.py:52 True)
# NO W-series check exists for CSRF_TRUSTED_ORIGINS in Django 5.2.16
# (grep: django/core/checks/ → "CSRF_TRUSTED_ORIGINS" returns zero matches)
```

*(supports: "check --deploy passes clean with a strong key; W004 is HSTS (set in prod); no check exists for CSRF_TRUSTED_ORIGINS")*

### Appendix D — Health contract components (R-06 through R-08 verification)

```python
# src/backend/apps/core/views.py:41-56 — health_check (DB-only)
def health_check(request):
    db_healthy = True
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")         # only DB check
    except Exception:
        db_healthy = False
    if db_healthy:
        return JsonResponse({"status": "healthy"})    # 200
    return JsonResponse({"status": "unhealthy"}, status=503)
```

```bash
# docker/healthcheck-bot.sh:1-35 — bot healthcheck (PID + marker + optional staleness)
# (a) kill -0 1 → liveness
# (b) [ -f "$marker" ] → readiness
# (c) staleness: BOT_HEALTH_STALE_SECONDS=0 → skipped (line 24-32)
```

```python
# src/telegram_bot/lifecycle.py:63-84 — LivenessMiddleware touches marker per update
async def __call__(self, handler, event, data):
    path = _marker_path()
    if path:
        os.utime(path, None)  # marker mtime updated on each inbound update
    return await handler(event, data)
# No staleness assertion in the middleware — staleness only enforced by healthcheck-bot.sh
```

### Appendix E — Backup & restore commands (R-10, R-12 verification)

```bash
# docker-compose.prod.yml:88-91 — backup (no --no-sync, no --lock)
pg_dump -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB -F c -f /backups/dump_$$date.dump

# Makefile:230 — backup target (same gap)
pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -F c > $(BACKUPS_DIR)/dump_$$(date +%Y%m%d_%H%M%S).dump

# docs/ops/restore.md:90-96 — restore (destructive, to LIVE DB)
pg_restore --clean --if-exists -U $POSTGRES_USER -d $POSTGRES_DB ./backups/<BACKUP_FILE>

# Makefile:245-246 — restore target (also to live DB)
pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists $(BACKUP_FILE)

# No restore-test procedure documented anywhere:
$ grep -rn "restore.*test\|isolated.*restore\|restore.*target.*isolated" docs/ Makefile
(no matches)
```

### Appendix F — Phase overlap reference

```text
Phase 01 (Entry Architecture): Finding 3 — HIGH — Production settings missing LOGGING dict
  → OPS-003 elevates to CRITICAL (adds error-tracking SDK gap + production observability framing)

Phase 02 (Config & Secrets): Finding 3 — LOW — No check --deploy backstop; weak SECRET_KEY placeholder
  → OPS-002 covers the broader CI/CD security gap (no SAST, no scanning, no deploy job)
  → OPS-002 + Phase 02 Finding 3 together justify: add check --deploy + security scanning to CI

Phase 03 (DB Concurrency): DB-002 — HIGH — Sync Redis cache I/O blocks aiogram event loop
  → Directly relevant to OPS-005: if Redis is slow/down, the bot event loop stalls,
     but /health/ still returns 200 (unhealthy bot, healthy healthcheck)

Phase 13 (Performance): Will audit SLOs (search <2s, filter <1s) and error budgets
  → OPS-008 documents the absence of ANY SLO/metrics infrastructure for Phase 13 to validate
```
