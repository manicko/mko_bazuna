# Phase 4 Detailed Plan: Analytics + Production Hardening

**Wave:** Infrastructure
**Depends_on:** Phases 1-3
**Files_modified:** `src/backend/apps/analytics/`, `src/backend/apps/core/management/commands/`, `docker/`, `.github/workflows/`, `docs/wiki/*.md`
**Autonomous:** Yes

> **Spec source:** `docs/wiki/01_technical_specification.md` (decision L, J; US-A5), `docs/wiki/03_structure.md` (R8 nginx),
> `docs/wiki/04_db_structure.md` (analytics_events, lifecycle indexes, erasure index).

---

## Task 1: Analytics Event Tracking (decision L)

**Goal:** Cookieless web analytics + internal product metrics.

**Acceptance Criteria:**
- Plausible JS snippet in `base.html` (cookieless, EU endpoint, <1KB, NO Python dep, NO consent banner — legitimate interest, decision L). Host configurable via env (`PLAUSIBLE_HOST`).
- `AnalyticsEvent` created on: REGISTRATION_CREATED (login), AD_PUBLISHED (auto-moderation pass), SEARCH_PERFORMED (search view), CONTACT_INITIATED (contact handler). `user_id` nullable, SET NULL on erasure.
- Admin metrics view `/admin/analytics/` + CLI `show_metrics` aggregating by `event_type`/date. No PII beyond already-collected `telegram_id`.

**Artifacts:** `apps/analytics/`, middleware/integration points, `management/commands/show_metrics.py`.
**Dependencies:** Phase 1 Task 4, Phase 3 Task 1
**Risks:** Event tracking gaps in bot vs web; privacy compliance.

---

## Task 2: Lifecycle Sweeps (decision J)

**Goal:** Scheduled cleanup of ads + consent erasure.

**Acceptance Criteria:**
- `archive_sweep`: PUBLISHED → ARCHIVED when `published_at < now() - interval '2 months'`; uses `IX_ads_archive_sweep`. Idempotent.
- `delete_sweep`: ARCHIVED → DELETED when `published_at < now() - interval '4 months'`; uses `IX_ads_delete_sweep`. Idempotent.
- `consent_hard_delete`: 30 days after `consent_revoked_at` → NULL `telegram_id`/`username`, DELETE user ads+images, SET NULL `analytics_events.user_id` + `ModeratorActionLog.user_id`; uses `IX_users_erasure_sweep`. Idempotent.
- `purge_failed_ads` (Phase 2 Task 4) + `purge_rejected_ads` (Phase 2 Task 5) wired to scheduler.
- `sweep_drafts` (30-min FSM draft idle timeout, zone C8) + `cleanup_login_tokens` (expired/consumed `LoginToken` rows, zone C1) — both owned here, idempotent, locked.
- All log counts to stdout; safe to run concurrently; each wrapped in a per-job DB advisory lock so the scheduler can retry safely.

**Artifacts:** `apps/core/management/commands/archive_sweep.py`, `delete_sweep.py`, `consent_hard_delete.py`, `sweep_drafts.py`, `cleanup_login_tokens.py`.
**Dependencies:** Phase 1 Task 6, Phase 3 Task 4, Phase 2 Tasks 4-5
**Risks:** FK cascade on hard delete; sweep/edit concurrency.

---

## Task 3: Lifecycle Index Verification (zone C4)

**Goal:** Confirm `IX_ads_archive_sweep` + `IX_ads_delete_sweep` exist; add only if missing.

**Acceptance Criteria:**
- Inspects existing migrations/DB state. These two partial indexes are defined in `Ad.Meta.indexes` (Phase 1 Task 6) and created by Phase 1 migrations, so in the normal flow they already exist.
- Migration adds them ONLY if absent (guard against duplicate-index migration); verifies against `04_db_structure.md`:
  - `IX_ads_archive_sweep`: `fields=['status','published_at']`, `condition=Q(status=AdStatus.PUBLISHED)`.
  - `IX_ads_delete_sweep`: `fields=['status','published_at']`, `condition=Q(status=AdStatus.ARCHIVED)`.
- `uv run manage.py migrate` succeeds.

**Artifacts:** `apps/ads/migrations/000X_lifecycle_indexes.py` (guarded) or a no-op verification note.
**Dependencies:** Phase 1 Task 6
**Risks:** Accidental duplicate index if Phase 1 already created them (hence the guard).

---

## Task 4: nginx Security Hardening (R8)

**Goal:** Production media + rate limiting.

**Acceptance Criteria:**
- `X-Content-Type-Options: nosniff` on all responses.
- `/media/`: whitelist `image/jpeg`, default `application/octet-stream`, `Content-Disposition: inline`; block script exec `location ~* /media/.*\.(php|py|cgi)$ { deny all; }`.
- Rate limiting on `/login/` and `/search/` (limit-req zones; avoid false positives).
- `USE_X_FORWARDED_HOST=True`, `SECURE_PROXY_SSL_HEADER` set; TLS termination via nginx.
- `uv run ruff check` n/a (infra); config linted.

**Artifacts:** `docker/nginx.conf`, `docker-compose.yml` nginx service.
**Dependencies:** Phase 1 Task 8
**Risks:** Over-restrictive rate limiting; media accessibility.

---

## Task 5: CI/CD Quality Gates

**Goal:** Automated lint + types + tests.

**Acceptance Criteria:**
- `.github/workflows/ci.yml`: `uv run ruff check` (select E,F,I,B,UP), `uv run basedpyright` (`typeCheckingMode="standard"`), `uv run pytest` with coverage.
- `ruff.toml` + `basedpyright` config committed.
- All gates green before merge.

**Artifacts:** `.github/workflows/ci.yml`, `ruff.toml`, `pyproject.toml` tool config.
**Dependencies:** Phase 1 Task 12
**Risks:** Environment drift; false positives in types.

---

## Task 6: Documentation Updates

**Goal:** Final spec + deployment docs.

**Acceptance Criteria:**
- `docs/wiki/01`: decision L (analytics), decision J (lifecycle) finalized.
- `docs/wiki/03`: deployment section complete (systemd/cron examples, nginx hardening).
- `docs/wiki/04`: lifecycle indexes confirmed.

**Artifacts:** Updated wiki files (English-only).
**Dependencies:** Tasks 1-5
**Risks:** Doc drift.
