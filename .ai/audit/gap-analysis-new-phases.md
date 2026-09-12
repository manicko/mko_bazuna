---
title: Audit Phase Gap Analysis — Recommendation for New Phases
status: draft
date: 2026-09-12
owner: audit-orchestrator
---

# Audit Phase Gap Analysis

## Summary

After reviewing the existing 11 audit phases (01–11) against modern best-practice
audit frameworks for Django, PostgreSQL, Docker/CI, and SRE/observability, **several
critical assurance domains are either missing or only partially covered**.

## Findings (A) — Gaps Between Existing Phases and Modern Best Practice

| Gap | Evidence | Existing Phase (if partial) |
|---|---|---|
| **G1. Dependency & Supply Chain Security** | CI plan lists Trivy, pip-audit, gitleaks, Dependabot, zizmor as "TO BE BUILT" — not yet implemented. No `requirements-audit.txt` lock. No SBOM generation (CycloneDX). | None |
| **G2. Container Image & Runtime Hardening** | Dockerfile uses non-root uid 1000 and multi-stage — good. But `docker-compose.prod.yml` has **no** `security_opt`, `cap_drop`, `read_only: true`, `tmpfs` for `/tmp`, or `user: 1000` enforcement. No `no-new-privileges`. | Phase 01 (partial: mentions non-root but not CIS runtime hardening) |
| **G3. Django Production Deployment Checklist** | `manage.py check --deploy` is **not invoked in any CI job or entrypoint**. `CSRF_TRUSTED_ORIGINS` is missing in `prod.py`. `SECURE_CONTENT_TYPE_NOSNIFF` and `SECURE_BROWSER_XSS_FILTER` are missing. `X_FRAME_OPTIONS` not set in Django (nginx handles it). | Phase 02 (config/secrets — partial) |
| **G4. Logging, Monitoring & Observability** | `LOGGING` is **only defined in `dev.py`**, not in `base.py` or `prod.py`. No Sentry, no Prometheus metrics, no OpenTelemetry, no health-check endpoint. No structured logging (`structlog` not present). | Phase 09 (external integrations — mentions uptime monitoring but not app-level observability) |
| **G5. Backup & Disaster Recovery** | Research document exists (`docs/97-plans/phase-01-detailed-deployment.md`) but there is **no audit phase** verifying backup/restore procedures, RPO/RTO definitions, or restore-test cadence. | None |
| **G6. Internationalization (i18n) Compliance** | CI has an i18n completeness test (`test_i18n_completeness.py`) and translation pipeline, but **no audit phase** to verify: `<title>` translation completeness, plural form correctness, `{% trans %}` coverage beyond the test gate. | None |
| **G7. Business Logic & Data Integrity** | PostgreSQL has row-level constraints; but no audit verifies **ad state transition guards** (e.g., cannot edit a `PUBLISHED` → `ARCHIVED` ad back to `DRAFT`), no check for **soft-delete consistency** (`is_deleted` flags + query filter enforcement), no check for **concurrent edit protection** (optimistic locking on `Ad` rows during bot edits). | Phase 05 (ad lifecycle — partial: covers statuses but not guardrails) |
| **G8. API & Bot Input Validation (Pydantic at Boundaries)** | Bot uses raw `aiogram` types for input; no Pydantic v2 validation layer at the bot boundary (rule #11 requires this). Web-side uses Django Forms (HTMX) but no Pydantic DTOs at API-like boundaries. | Phase 08 (bot ad dialog — partial: covers dialog flow but not input sanitization) |

## Evidence (B) — Supporting Observations

- **CI/CD plan** (`.ai/plans/ci_cd/plan.md_updated.md`):
  - D1: Trivy filesystem + image scanning — NOT IMPLEMENTED in `ci.yml`
  - D3: pip-audit — NOT IMPLEMENTED
  - D4: Dependabot — NOT CONFIGURED (`.github/dependabot.yml` absent)
  - D5: gitleaks — NOT IMPLEMENTED
  - D6: zizmor (GitHub Actions hardening) — NOT IMPLEMENTED
- **Production settings** (`src/backend/config/settings/prod.py`):
  - `CSRF_TRUSTED_ORIGINS` — **missing**
  - `SECURE_CONTENT_TYPE_NOSNIFF` — **missing**
  - `SECURE_BROWSER_XSS_FILTER` — **missing**
  - `LOGGING` — **not defined** (inherits from base, which is also undefined)
- **Docker Compose** (`docker-compose.prod.yml`):
  - **No** `security_opt`, `cap_drop`, `read_only`, `tmpfs`, `user:` overrides
- **Health checks**: No `/healthz` or `/readyz` endpoint in `urls.py` or `wsgi.py`
- **Bot input validation**: No Pydantic v2 models in `src/telegram_bot/bot/handlers/`
- **Ad state transitions**: No model-level guard in `apps.ads.models.Ad` preventing invalid status transitions
- **Backup verification**: `docs/ops/restore.md` exists (restore procedure documented) but **no audit phase** validates backup integrity or tests restores

## Recommendation (C) — Proposed New Phases

### Phase 12: Dependency & Supply Chain Security Audit
**Scope**: Verify that all dependencies (Python, Docker base images, system packages) are scanned for known vulnerabilities on every CI run. Confirm no hardcoded secrets in repository.

**Key checks**:
- [ ] `pip-audit` runs in CI against `requirements-*.txt`
- [ ] `trivy image` runs in CI against built Docker image
- [ ] `gitleaks` runs in CI as a pre-merge gate
- [ ] Dependabot config exists and is enforced
- [ ] SBOM is generated (CycloneDX format) and archived as CI artifact
- [ ] `requirements.in` is pinned (`requirements-audit.txt` or equivalent lock file exists)

### Phase 13: Container Runtime Hardening Audit
**Scope**: Verify Docker production deployment follows CIS Docker Benchmark runtime hardening controls.

**Key checks**:
- [ ] `docker-compose.prod.yml` services run as non-root user
- [ ] `security_opt: no-new-privileges` is set
- [ ] `cap_drop: ALL` or explicit capability whitelist is present
- [ ] `read_only: true` is set for all service containers
- [ ] `tmpfs` is mounted for `/tmp` and application temp directories
- [ ] Docker image is scanned with Trivy (ties to Phase 12)
- [ ] Base image tags are pinned (not `:latest`)

### Phase 14: Production Observability & Logging Audit
**Scope**: Verify structured logging, error tracking, metrics collection, and health-check endpoints are production-ready.

**Key checks**:
- [ ] `LOGGING` is defined in `prod.py` (not inherited from dev)
- [ ] Structured JSON logging or `structlog` is configured
- [ ] Sentry (or equivalent) SDK is initialized and DSN is injected via env var
- [ ] Metrics endpoint (`/metrics`) is exposed and scraped by Prometheus
- [ ] Health-check endpoints exist: `/healthz` (liveness), `/readyz` (readiness)
- [ ] Request duration, error rate, and saturation metrics are instrumented

### Phase 15: Backup & Disaster Recovery Audit
**Scope**: Verify backup procedures are defined, tested, and RPO/RTO are documented and met.

**Key checks**:
- [ ] PostgreSQL base backup + WAL archiving strategy is documented (cronjob or `pgBackRest`)
- [ ] Media files (`/media/`) are backed up to object storage (S3-compatible) with versioning
- [ ] RPO (≤ 1 hour) and RTO (≤ 4 hours) are defined for DB + media
- [ ] Restore procedure is documented in `docs/ops/restore.md` and linked from architecture docs
- [ ] A quarterly restore test is scheduled and recorded in CI or a runbook

### Phase 16: Internationalization (i18n) Compliance Audit
**Scope**: Verify complete i18n coverage beyond the automated test gate — including SEO tags, title tags, and locale switching.

**Key checks**:
- [ ] All user-visible strings in Python are wrapped in `gettext`/`gettext_lazy`
- [ ] All template strings are wrapped in `{% trans %}` or `{% blocktrans %}`
- [ ] `<title>` tags are translated per-page
- [ ] `hreflang` tags are present and correct in page `<head>`
- [ ] Plural form rules are correct for `ru`, `bs`, `en` (Django's built-in plural forms)
- [ ] Language switcher sets cookie/session correctly (HTMX swap verified)

### Phase 17: Business Logic Integrity Audit
**Scope**: Verify ad state transition guards, soft-delete consistency, and concurrent-edit protection.

**Key checks**:
- [ ] `Ad.status` transitions are validated in `models.Ad.clean()` or a state machine
  - [ ] `DRAFT → PUBLISHED` allowed; `PUBLISHED → DRAFT` rejected
  - [ ] `PUBLISHED → ARCHIVED` allowed; `ARCHIVED → DRAFT` rejected
- [ ] Soft-delete (`is_deleted`) is enforced via a custom manager that filters
  `is_deleted=False` on all querysets
- [ ] Concurrent edits to `Ad` rows by the bot use optimistic locking
  (`select_for_update` or version/timestamp check)
- [ ] `Ad.price` and `Ad.area` have database-level range constraints (CHECK ≥ 0)

### Phase 18: Bot Input Validation & Sanitization Audit
**Scope**: Verify all external input into the bot (via Telegram messages) is validated with Pydantic v2 models before being persisted or processed.

**Key checks**:
- [ ] Telegram webhook payload is validated against a Pydantic v2 model (message text, callback data)
- [ ] Ad title, description, price, area, city — all user-entered fields — pass through
  Pydantic validation (type, length, regex, range) before reaching the ORM
- [ ] HTML/markdown in user-entered text is sanitized on output (no XSS via Telegram → web)
- [ ] Callback query data (`callback.query.data`) is validated against expected schemas
- [ ] Bot FSM transitions are guarded by validation (no invalid input advances the dialog)

## Rationale (D) — Why These Phases Are Needed

1. **Dependency security (G1)** is a top-10 OWASP Risk and a requirement for any
   production Django app. The CI/CD plan explicitly defers it — it must be an audit
   gate, not a TODO.

2. **Container hardening (G2)** follows the CIS Docker Benchmark — a defacto standard
   for production container deployments. The current setup uses non-root but omits
   read-only filesystems, capability dropping, and `no-new-privileges`.

3. **Observability (G4)** is an SRE fundamental. Without `LOGGING` in prod, Sentry,
   metrics, and health checks, the app cannot be monitored or debugged in production.
   Phase 09 only covers external uptime monitoring (cron-based), not application-level
   observability.

4. **Backup/DR (G5)** is a business-critical domain with an existing research doc
   and restore guide but **zero audit coverage**. This is unacceptable for a system
   handling user-generated classifieds.

5. **i18n compliance (G6)** has a CI test gate (`test_i18n_completeness.py`) but no
   audit phase to verify the test itself is comprehensive (title tags, hreflang,
   plural forms, locale switching correctness).

6. **Business logic integrity (G7)** covers state machine correctness,
   soft-delete discipline, and concurrency — none of which are verified by the
   existing 11 phases. This is especially relevant for the Ad model, which has
   5 statuses and multiple actors (bot, web admin, buyer views).

7. **Bot input validation (G8)** is a direct requirement of project rule #11
   ("Pydantic v2 + type hints at system boundaries"). Currently the bot accepts
   raw `aiogram` types with no validation layer.

## Conclusion

**Recommendation**: Adopt 6 new audit phases (12–17) covering:
- Dependency & supply chain security (Phase 12)
- Container runtime hardening (Phase 13)
- Production observability & logging (Phase 14)
- Backup & disaster recovery (Phase 15)
- Internationalization compliance (Phase 16)
- Business logic integrity (Phase 17)
- Bot input validation & sanitization (Phase 18)

These phases close critical assurance gaps that are either absent or only partially
covered by the existing 11 phases, and many stem from explicitly deferred work
in the CI/CD plan.
