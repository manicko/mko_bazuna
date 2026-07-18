# Phase 4 Detailed Plan: Analytics + Production Hardening

**Wave:** Infrastructure  
**Depends_on:** Phases 1-3  
**Files_modified:** `src/backend/apps/`, `docker/`, `docs/wiki/*.md`  
**Autonomous:** Yes

---

## Task 1: Analytics Event Tracking
**Goal:** Internal + Plausible metrics.
**Acceptance Criteria:**
- `AnalyticsEvent` created on: registration (REGISTRATION_CREATED), ad publish (AD_PUBLISHED), search (SEARCH_PERFORMED), contact (CONTACT_INITIATED)
- Plausible JS snippet in base template, cookieless mode, EU endpoint
- `/admin/analytics/` dashboard shows event counts over time
**Artifacts:** `apps/analytics/`, middleware, admin view
**Dependencies:** Phase 1 Task 4, Phase 3 Task 1

---

## Task 2: Archive + Delete Sweeps
**Goal:** Scheduled cleanup.
**Acceptance Criteria:**
- `archive_sweep`: 2 months → ARCHIVED (US-A5)
- `delete_sweep`: 4 months → DELETED (US-A5, ad lifecycle)
- `consent_hard_delete`: 30 days after consent revocation (R1, GDPR erasure)
- All commands log to stdout, safe to run concurrently
**Artifacts:** Management commands in `apps/core/management/commands/`
**Dependencies:** Phase 1 Task 6, Phase 3 Task 4

---

## Task 3: Security Headers + Rate Limiting
**Goal:** Production security.
**Acceptance Criteria:**
- nginx: `X-Content-Type-Options: nosniff`, script execution blocked in /media/
- nginx: rate-limited endpoints (`/login/`, `/search/`)
- `django.middleware.security.SecurityMiddleware` with appropriate settings
**Artifacts:** `docker/nginx.conf`, security settings
**Risks:** Overly restrictive rate limiting, false positives

---

## Task 4: CI/CD Configuration
**Goal:** Automated quality gates.
**Acceptance Criteria:**
- `.github/workflows/ci.yml`: ruff check, basedpyright, pytest with coverage
- ruff: `select=["E", "F", "I", "B", "UP"]`
- basedpyright: `typeCheckingMode="standard"`
**Artifacts:** GitHub Actions workflow
**Dependencies:** Phase 1 Task 12

---

## Task 5: Documentation Updates
**Goal:** Final spec + deployment docs.
**Acceptance Criteria:**
- `docs/wiki/01`: Decision L (analytics), Decision J (lifecycle)
- `docs/wiki/03`: Deployment section complete (systemd/cron examples)
**Artifacts:** Wiki updates