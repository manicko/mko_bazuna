---
name: audit-final-report
description: Merged, validator-approved audit findings across all 11 phases
validated: true
---

# Mko Bazuna — Multi-Agent Audit Final Report

**Date:** 2026-07-20
**Model (executor/validator):** `poolside/laguna-m.1:free`
**Phases executed:** 11 / 11 (all)
**Mode:** problems-only (passing checks omitted)
**Validation:** every phase finding reviewed by a validator agent; rejected/merged findings removed from the merged set.

---

## Executive Summary

The audit found the project **cannot currently run in production and has no working web authentication**, plus pervasive consistency, PII, and concurrency gaps. The single most important theme: **the documented two-process (web + bot) architecture is not actually wired together** — the web-side auth/issuance, the bot-side shared-service delegation, and atomic transaction boundaries are all missing or bypassed.

**79 validated findings** (after removing 7 rejected/merged findings):

| Severity | Count |
|----------|-------|
| CRITICAL | 15 |
| HIGH | 23 |
| MEDIUM | 26 |
| LOW | 15 |
| **Total** | **79** |

---

## Per-Phase Results

| # | Phase | Critical | High | Medium | Low | Validated |
|---|-------|----------|------|--------|-----|-----------|
| 1 | entry-architecture | 2 | 2 | 0 | 1 | 5 |
| 2 | config-secrets | 0 | 1 | 3 | 1 | 6 |
| 3 | db-concurrency | 1 | 1 | 1 | 1 | 4 |
| 4 | auth-login | 1 | 2 | 1 | 1 | 5 |
| 5 | ad-lifecycle | 1 | 0 | 2 | 0 | 3 |
| 6 | pii-consent | 2 | 3 | 5 | 1 | 11 |
| 7 | media | 2 | 2 | 2 | 1 | 7 |
| 8 | search-fts | 0 | 3 | 3 | 3 | 9 |
| 9 | external-api | 1 | 3 | 4 | 2 | 10 |
| 10 | code-quality | 0 | 2 | 2 | 2 | 6 |
| 11 | test-coverage | 3 | 4 | 3 | 2 | 12 |
| | **Total** | **15** | **23** | **26** | **15** | **79** |

**Rejected/merged during validation (excluded from above):** ENT-005, ENT-006→ENT-001, CFG-004, AD-002, AD-005, AUT-005, MED-007.
**Reclassified during validation (kept, type changed):** ENT-007 (SPEC-DEVIATION), CFG-001 (DOC-UPDATE), AUT-004 (DOC-UPDATE), PII-006 (DOC-UPDATE), SRH-004 (DOC-UPDATE), SRH-008 (DOC-UPDATE).

---

## Complete Findings Index (validator-approved)

### Phase 1 — Entry Points & Process Architecture
- **ENT-001** [CRITICAL, SPEC-DEVIATION] Container cannot boot — missing `PYTHONPATH`/`--no-install-project`/package-discovery mismatch.
- **ENT-002** [CRITICAL, SPEC-DEVIATION] Bot imports Django models before `django.setup()` → `AppRegistryNotReady`.
- **ENT-003** [HIGH, SPEC-DEVIATION] `save_photo()` does blocking file I/O on the async event loop.
- **ENT-004** [HIGH, SPEC-DEVIATION] `translate_to_russian()` blocking network call on event loop.
- **ENT-007** [LOW, SPEC-DEVIATION] `pyproject.toml` package discovery does not match source layout.

### Phase 2 — Configuration & Secrets
- **CFG-003** [HIGH, SPEC-DEVIATION] Bot loads `BOT_TOKEN` via raw `os.getenv` with silent exit-0 on missing — divergent from web fail-fast.
- **CFG-002** [MEDIUM, SPEC-DEVIATION] `POSTGRES_PASSWORD` silently defaults to `""`.
- **CFG-001** [MEDIUM, DOC-UPDATE] Orphaned `src/backend/.env` (SQLite + duplicate keys) misleads operators.
- **CFG-005** [MEDIUM, BEST-PRACTICE] No tests for settings/secret-loading.
- **CFG-006** [LOW, DOC-UPDATE] Weak placeholder values in `.env.dev.example`.

### Phase 3 — Database & Concurrency
- **DB-002** [CRITICAL, SPEC-DEVIATION] No `transaction.atomic` anywhere — multi-row domain writes can partially commit.
- **DB-001** [HIGH, SPEC-DEVIATION] Transaction-scoped advisory lock released between `count()` and `delete()` under autocommit; sweep idempotency not guaranteed.
- **DB-003** [MEDIUM, BEST-PRACTICE] `sync_to_async` + `CONN_MAX_AGE=0` connection churn under bot burst.
- **DB-004** [LOW, BEST-PRACTICE] Unguarded `get_or_create` race in `get_or_create_user`.

### Phase 4 — Authentication & Login Token
- **AUT-001** [CRITICAL, SPEC-DEVIATION] Web-side token issuance entirely missing — no `/login/`, no `LoginToken` creation in production.
- **AUT-002** [HIGH, SPEC-DEVIATION] Web consumption (`consumed_at`) never written.
- **AUT-003** [HIGH, SPEC-DEVIATION] Web session never established from a claim.
- **AUT-004** [MEDIUM, DOC-UPDATE] `hmac.compare_digest` claimed in docstring but never used (indexed hash lookup is actually fine).
- **AUT-006** [LOW, SPEC-DEVIATION] Cleanup keyed on `created_at`, not `consumed_at`.

### Phase 5 — Ad Lifecycle, Categories & Moderation
- **AD-001** [CRITICAL, SPEC-DEVIATION] Bot publish path re-implements moderation inline, bypassing `auto_moderate()`/`set_published()` and skipping `ModeratorActionLog`; divergent `max_ads_per_user` counting.
- **AD-003** [MEDIUM, SPEC-DEVIATION] `approve_ad` never sets `original_published_at` on first publish.
- **AD-004** [MEDIUM, BEST-PRACTICE] Bot DRAFT cancel leaves physical image files orphaned.

### Phase 6 — PII Protection & Consent
- **PII-001** [CRITICAL, SPEC-DEVIATION] `withdraw_consent` NULLs `telegram_id` → withdrawn seller regains full bot access.
- **PII-002** [CRITICAL, SPEC-DEVIATION] `withdraw_consent` is unreachable from UI/bot — withdrawal flow is dead code.
- **PII-003** [HIGH, SPEC-DEVIATION] DECLINE only blocks auto-publish, not seller login (spec requires blocking login).
- **PII-004** [HIGH, SPEC-DEVIATION] Consent hard-delete never erases media files on disk.
- **PII-005** [HIGH, BEST-PRACTICE] Withdraw-mid-FSM not purged — DRAFT photos + bot FSM state leak.
- **PII-006** [MEDIUM, DOC-UPDATE] `hard_delete_at` dead field contradicts docs.
- **PII-007** [MEDIUM, BEST-PRACTICE] Naive `datetime.now()` vs `timezone.now()` TZ skew on 30-day window.
- **PII-008** [MEDIUM, BEST-PRACTICE] Raw `telegram_id` written to INFO logs.
- **PII-009** [LOW, BEST-PRACTICE] `User.__str__`/admin expose `telegram_id`.
- **PII-010** [MEDIUM, BEST-PRACTICE] `first_name`/`last_name` retained until hard-delete.

### Phase 7 — Media Handling & Security
- **MED-001** [CRITICAL, SPEC-DEVIATION] nginx serves `/media/` with no access control — unpublished/withdrawn/deleted photos fetchable by URL.
- **MED-002** [CRITICAL, SPEC-DEVIATION] EXIF/metadata never stripped — GPS/device PII persists in served bytes.
- **MED-003** [HIGH, SPEC-DEVIATION] Sweeps/erasure delete DB rows but never physical media files.
- **MED-004** [HIGH, SPEC-DEVIATION] In-flight cancel/crash leaves orphaned partial files.
- **MED-005** [MEDIUM, SPEC-DEVIATION] Two divergent `generate_storage_key`; docstring "ad_id + UUID" claim false.
- **MED-006** [MEDIUM, BEST-PRACTICE] Unguarded `open()` — UUID collision overwrites another ad's file.
- **MED-008** [LOW, BEST-PRACTICE] No media-security tests.

### Phase 8 — Search & FTS
- **SRH-001** [HIGH, SPEC-DEVIATION] 500ms translation timeout does not bound latency (blocking `shutdown(wait=True)`).
- **SRH-002** [HIGH, SPEC-DEVIATION] Search category match lacks `get_descendants()` expansion (parent searches miss children).
- **SRH-003** [HIGH, SPEC-DEVIATION] No pagination/`LIMIT` on search/listings — DoS/latency risk.
- **SRH-004** [MEDIUM, DOC-UPDATE] `lru_cache` has no TTL despite "5-minute cache" claim.
- **SRH-005** [MEDIUM, BEST-PRACTICE] Raw buyer query strings logged (PII/log-injection).
- **SRH-006** [LOW, BEST-PRACTICE] Overly broad `except (..., Exception)`.
- **SRH-007** [LOW, BEST-PRACTICE] Analytics event recorded before search executes.
- **SRH-008** [MEDIUM, DOC-UPDATE] `pg_trgm` documented but never used (implementation uses `difflib`).
- **SRH-009** [LOW, SPEC-DEVIATION] HTMX branch renders full page (dead code).

### Phase 9 — External Integrations & API
- **EXT-001** [CRITICAL, SPEC-DEVIATION] Login-token issuance entirely missing — deep-link auth non-functional; `/login/` nginx rate-limit guards a non-existent route.
- **EXT-002** [HIGH, RUNTIME-ERROR] `claim_login_token` TOCTOU race (filter-then-get, no row lock); docstring falsely claims `hmac.compare_digest`.
- **EXT-003** [HIGH, RUNTIME-ERROR] `translate_to_russian()` blocking network call on event loop.
- **EXT-004** [HIGH, SPEC-DEVIATION] Contact deep-link forwards buyer's REAL name to seller, contradicting "anonymous/no PII" design.
- **EXT-005** [MEDIUM, BEST-PRACTICE] Unofficial Google endpoint, no circuit-breaker/backoff/quota awareness.
- **EXT-006** [MEDIUM, SPEC-DEVIATION] nginx sets no HSTS; security headers confined to `/media/`.
- **EXT-007** [MEDIUM, RUNTIME-ERROR] `save_photo()` blocking filesystem write on event loop.
- **EXT-008** [MEDIUM, SPEC-DEVIATION] Base `web` service lacks restart policy (split-brain vs bot).
- **EXT-009** [LOW, BEST-PRACTICE] Ad/search content egressed to Google Translate undocumented.
- **EXT-010** [LOW, BEST-PRACTICE] No integration-health metrics; bot has no healthcheck.

### Phase 10 — Code Quality
- **QLT-001** [HIGH, SPEC-DEVIATION] Bot re-implements auto-moderation inline (omits banned-words/duplicate-title, skips `ModeratorActionLog`).
- **QLT-002** [HIGH, SPEC-DEVIATION] Bot `check_seller_available`/`record_contact_event` duplicate shared contact service.
- **QLT-003** [MEDIUM, SPEC-DEVIATION] `AnalyticsEventType.AD_PUBLISHED.value` passed raw string instead of enum member.
- **QLT-004** [MEDIUM, BEST-PRACTICE] Sort options are raw strings, not `StrEnum`.
- **QLT-005** [LOW, BEST-PRACTICE] `datetime.now()` instead of `timezone.now()` in `deletion.py`.
- **QLT-006** [LOW, BEST-PRACTICE] Root-level scaffold scripts with `print()` pollute repo root.

### Phase 11 — Test Coverage
- **TST-001** [CRITICAL, BEST-PRACTICE] `claim_login_token` (replay/expiry guard) untested.
- **TST-002** [CRITICAL, BEST-PRACTICE] Core ad-lifecycle transitions untested.
- **TST-003** [CRITICAL, BEST-PRACTICE] Entire `telegram_bot/` package has zero tests and is not collected by pytest.
- **TST-004** [HIGH, BEST-PRACTICE] No web-view (Client) tests for search/contact/consent/moderation.
- **TST-005** [HIGH, BEST-PRACTICE] No migration reproducibility/idempotency test.
- **TST-006** [HIGH, BEST-PRACTICE] Translation fallback untested (and naive test would hit network).
- **TST-007** [HIGH, BEST-PRACTICE] Media validation/storage-key generation untested.
- **TST-008** [MEDIUM, BEST-PRACTICE] CI runs pytest with no coverage reporting/threshold.
- **TST-009** [MEDIUM, BEST-PRACTICE] Auto-moderation test coupled to private internals.
- **TST-010** [MEDIUM, BEST-PRACTICE] Account-state gating & deletion/PII services untested.
- **TST-011** [LOW, BEST-PRACTICE] Contact deep-link regex duplicated in test.
- **TST-012** [LOW, BEST-PRACTICE] `slow` marker defined but unused; no `integration` marker.

---

## Cross-Cutting Themes (fix together)

1. **Web ↔ Bot architecture is not actually connected.**
   - No web-side auth issuance/consumption (AUT-001/002/003, EXT-001, TST-001).
   - Bot handlers re-implement shared services (QLT-001, QLT-002, AD-001) → divergent moderation/contact behavior and missing audit trail.
   - *Net effect:* the documented dual-process contract is non-functional.

2. **Blocking I/O on the async event loop (repeated).**
   - `save_photo()` (ENT-003, EXT-007), `translate_to_russian()` (ENT-004, EXT-003) — all need `sync_to_async`/`asyncio.to_thread` + timeouts.

3. **PII / consent compliance is broken end-to-end.**
   - Withdrawn users regain bot access (PII-001); withdrawal unreachable (PII-002); DECLINE doesn't block login (PII-003); media never purged (PII-004, MED-003); EXIF leak (MED-002); name egress (EXT-004).

4. **No transaction atomicity (data-integrity risk).**
   - DB-001/DB-002 plus MED-003/MED-004 orphaned files; PII-007 TZ skew compared against sweep timestamps.

5. **Security-by-obscurity media access.**
   - MED-001 (no access control on `/media/`) combined with MED-003/004 leaves PII photos directly fetchable.

6. **Test suite covers only the web process.**
   - TST-003 (bot untested), TST-001/002 (security-critical paths), TST-008 (no coverage gate) → green CI hides 0% coverage on the most sensitive code.

---

## Recommended Remediation Order

1. **Make it boot & be secure by default** — ENT-001/002 (boot), ENT-003/004 + EXT-003/007 (event-loop blocking), CFG-003 (fail-fast bot secret).
2. **Make auth real** — AUT-001 → AUT-002 → AUT-003 (web issuance/consumption/session), EXT-002 (claim race), AUT-006.
3. **Stop PII leakage now** — MED-001 (media access control), MED-002 (EXIF strip), PII-001/002/003/004 (consent wiring + media purge).
4. **Restore data integrity** — DB-002 (atomic multi-row writes), DB-001 (sweep lock), AD-001/QLT-001 (centralize moderation), QLT-002 (contact service).
5. **Harden search/ops** — SRH-001/002/003 (timeout, category tree, pagination), EXT-006 (HSTS), EXT-008 (web restart), SRH-005/008 doc fixes.
6. **Build the safety net** — TST-003/001/002/008 first (bot tests + coverage gate), then TST-004..007/009/010.

---

*Detailed per-finding evidence, validation notes, and rollout sequencing are in `.ai/audit/99-validation/<phase>-validated-findings.md`. Raw executor output is in `.ai/audit/<phase>/findings.md`.*
