---
id: 09-ad-lifecycle-fix-matrix
domain: audit-remediation
tags:
  - ad-lifecycle
  - moderation
  - migrations
  - sweeps
  - fts
phase: "05-ad-lifecycle"
status: draft
---

# Ad Lifecycle Fix Matrix — Test & Documentation Requirements

> Phase: `05-ad-lifecycle` · Audit source: `.ai/audit/99-validation/05-ad-lifecycle-validated-findings.md`
> Generated during Step 3 of the remediation workflow (research → matrix → implement → docs).

This matrix consolidates every validated finding, its **preferred remediation
path** (selected in Step 2.1 remediation research), the **tests required** to
guard the change, and the **documentation changes** needed. Status moves to
`done` only after the Implementor commits + passes quality gates and the
Doc-specialist updates the listed docs.

## Decision Log (resolved during Step 2.1 research)

| Decision | Resolution | Rationale |
|---|---|---|
| **Migration number** for new `ads` schema changes | `0006` | Filesystem (`ads/migrations/`) contains only `0001`–`0005`. The stale table in `migration-workflow.md` (claiming 10 files, latest `0010`) predates a consolidation that reduced the files. `0006_backfill_translations` was extracted to a command and is gone, so `0006` is the next free slot. |
| **AD-005 + AD-008 combine** into one migration | Yes — both are `RunSQL` `CREATE OR REPLACE FUNCTION` on functions installed by `0002_initial.py`; independent logic, safe to deploy together, avoids two deploy cycles | Researchers' cross-finding recommendation |
| **AD-001 reject_ad matrix conflict** | **Add** `ON_MODERATION_FAILED → {REJECTED}` to `ALLOWED_TRANSITIONS` (rather than hard-enforcing `ON_MODERATION`-only) | Spec matrix (`spec-index.md:78`) omits this edge, but **product code requires it**: `review.py:84` fetches `[ON_MODERATION, ON_MODERATION_FAILED]`, `bulk_reject` filters both, and `test_reject_failed_moderation_ad` asserts rejection from `ON_MODERATION_FAILED`. Adding the matrix entry fixes the *actual* spec violation (no more `PUBLISHED`/`DRAFT`/`ARCHIVED → REJECTED`) while preserving the legitimate auto‑failed‑ad reject flow. `transition_to(REJECTED)` already clears `moderation_failed_at` + sets `rejected_at`. |
| **AD-002 retention window** for DELETED | 4 months (120 days) from `deleted_at` | Audit phase spec `.kilo/commands/audit/phases/05-audit-ad-lifecycle.md:75`: `\| DELETED \| 4 months \| purge \|` |
| **AD-002 AdvisoryLockId** for new command | `PURGE_DELETED_ADS = 11` | `AdvisoryLockId` enum (`core/enums.py:20-36`) uses IDs 1–10 (all taken) and 100+ for special ops. `11` is the next contiguous free value. |
| **AD-007 (staleness)** | Main claim STALE; residual fix only | `purge_rejected_ads.py` (and all 4 sweep/purge commands) **already** call `delete_photo()` outside `transaction.atomic()`. Verified by code (`purge_rejected_ads.py:73` atomic closes; `:78` loop outside) + existing test `test_sweep_commands.py:599-636` (`test_file_deletion_after_commit_not_inside_transaction`). Residual: `delete_photo()` catches only `FileNotFoundError`, not broader `OSError`; no retry. |
| **AD-008 search_vector shape** | ONE `search_vector` column, multi‑lang `tsvector` per `db-indexes.md:55-76` (Russian, Bosnian `simple`, English `english`) — **not** per‑language columns | `db-enums.md` defines exactly 3 `LanguageLocale`s (ru/bs/en); `db-indexes.md:55-76` documents a single `search_vector` built from all variants with weights A/B/C. The `search apps` app's own trigger is a *different* concern (autocomplete suggestions). |
| **AD-006 fallback locale** for bot | `LanguageLocale.BOSNIAN` | Telegram `language_code` is omitted for many users; the bot's market is Bosnian and the field's current production value is `"bs"`, so defaulting to `BOSNIAN` preserves existing behavior for the common case. |

---

## Summary Table

| ID | Finding | Severity | Classification | Preferred Fix Location | Migration | Tests | Docs | Status |
|----|---------|----------|----------------|------------------------|-----------|-------|------|--------|
| AD-001 | Direct status overwrites bypass `transition_to()` | CRITICAL | Complex / Multi-route | `ads/models.py`, `moderation/admin_actions.py`, `moderation/services/moderation_log.py` | `0006` (constraints) | `test_ad_lifecycle.py`, `test_admin_actions.py` (new) | `db-schema.md`, `db-enums.md` | ⏳ Open |
| AD-002 | No purge job for DELETED status | HIGH | Simple / Low-risk | `core/management/commands/purge_deleted_ads.py` (new), `ads/models.py`, `core/enums.py`, `docker/entrypoint-scheduler.sh` | `0006` (index) | `test_sweep_commands.py` | `db-indexes.md`, `db-enums.md`, `docker-deployment.md` | ⏳ Open |
| AD-003 | Max-ads check counts `ON_MODERATION_FAILED` as active | HIGH | Simple / Low-risk | `moderation/services/auto_moderation.py:197` | none | `test_auto_moderation.py` | none | ⏳ Open |
| AD-004 | `check()` mutates state (not read-only) | MEDIUM | Simple / Low-risk | `moderation/services/auto_moderation.py:264-324` | none | `test_auto_moderation.py` | none | ⏳ Open |
| AD-005 | Category-rename trigger relies on no-op UPDATE | MEDIUM | Complex / High-risk | `ads/migrations/0006_*.py` (`RunSQL`) | `0006` | `test_search_triggers.py`, `test_migrations.py` | `db-indexes.md:87-97` | ⏳ Open |
| AD-006 | `original_language` hardcoded `"bs"` | LOW (advisory) | Multiple-viable-routes | `core/enums.py` (`LanguageLocale.from_code`), `telegram_bot/handlers/ad_create.py:473` | none | `test_language_locale.py`, `test_ad_create.py` (new) | `db-enums.md:91-103`, `technical-specification.md` | ⏳ Open |
| AD-007 | File deletion inside transaction | LOW (advisory) | Complex / High-risk | `telegram_bot/services/media.py` | none | `test_media.py`, `test_sweep_commands.py` | `db-retention.md` (new) | ⏳ Open |
| AD-008 | Multilingual `search_vector` not implemented | HIGH (cross-finding) | Complex / High-risk | `ads/migrations/0006_*.py` (`RunSQL`) | `0006` | `test_ad_localization.py`, `test_ad_search.py` (new) | `db-indexes.md:55-76` | ⏳ Open |

---

## AD-001 — Direct status overwrites bypass `transition_to()`

**Classification:** Complex / Multiple-viable-routes
**Severity:** CRITICAL · **Priority:** mandatory

### Preferred Solution

**Single-row path — route through existing `set_*` service wrappers** (Alternative 1 from remediation research):

| Function | Current (bypass) | Preferred (routed) |
|---|---|---|
| `approve_ad()` | `ad.status = AdStatus.PUBLISHED` (manual timestamps) | `set_published(ad, moderator_id)` → `transition_to(PUBLISHED)` + audit log |
| `reject_ad()` | `ad.status = AdStatus.REJECTED` (guard only blocks re-reject) | `set_rejected(ad, moderator_id, reason)` → `transition_to(REJECTED)` + audit log |
| `soft_delete_ad()` | `ad.status = AdStatus.DELETED` | `ad.transition_to(AdStatus.DELETED)` directly (no wrapper; `any→DELETED` always valid) |
| `bulk_approve`/`bulk_reject`/`bulk_delete` | loop calling the single-row funcs | inherit the fix automatically |

**Matrix update required:** Add `ON_MODERATION_FAILED → {REJECTED}` to `ALLOWED_TRANSITIONS` in `ads/models.py:280-292` (see Decision Log). Without this, `set_rejected()` → `transition_to(REJECTED)` raises `ValueError` for auto-failed ads, breaking `review.py:84`, `bulk_reject`, and `test_reject_failed_moderation_ad`.

**Bot handler is NOT a bypass** — verified: `ad_create.py:772` calls `transition_to(ON_MODERATION)`, then `auto_moderate()` routes through `set_published()`/`set_moderation_failed()`, both of which already use `transition_to()`. No change needed in the bot handler path.

**Bulk sweep path — DB CheckConstraints** (Alternative A from remediation research):

The `archive_sweep.py` queryset-level `update(status=..., archived_at=...)` already enforces source-status (`PUBLISHED` only, line 47). The remaining gap is timestamp/side-effect consistency. Add `CheckConstraint`s to `Ad.Meta.constraints`:

```python
# Status must be accompanied by its timestamp
CheckConstraint(
    check=Q(status=AdStatus.ARCHIVED) & Q(archived_at__isnull=False) |
          ~Q(status=AdStatus.ARCHIVED),
    name="ck_ads_archived_at_if_archived",
)
# ... (5 more invariants + 2 mutual-exclusivity constraints)
```

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Happy path | `apps/ads/tests/test_ad_lifecycle.py` | `test_approve_ad_through_transition_to` | `approve_ad()` calls `set_published`/`transition_to`; `published_at` + `original_published_at` set; `published_by` set |
| Happy path | `apps/ads/tests/test_ad_lifecycle.py` | `test_reject_ad_from_moderation_succeeds` | `reject_ad()` from `ON_MODERATION` → `REJECTED`; `rejected_at` set, `rejected_by` set |
| Happy path | `apps/ads/tests/test_ad_lifecycle.py` | `test_reject_ad_from_moderation_failed_succeeds` | `reject_ad()` from `ON_MODERATION_FAILED` → `REJECTED` (after matrix update); `moderation_failed_at` cleared, `rejected_at` set |
| Edge | `apps/ads/tests/test_ad_lifecycle.py` | `test_reject_published_raises` | `reject_ad()` from `PUBLISHED` raises `ValueError` (bypass now blocked) |
| Edge | `apps/ads/tests/test_ad_lifecycle.py` | `test_reject_archived_raises` | `reject_ad()` from `ARCHIVED` raises `ValueError` |
| Edge | `apps/ads/tests/test_ad_lifecycle.py` | `test_reject_draft_raises` | `reject_ad()` from `DRAFT` raises `ValueError` |
| Edge | `apps/ads/tests/test_ad_lifecycle.py` | `test_soft_delete_any_state` | `soft_delete_ad()` from any non-terminal status → `DELETED`; `deleted_at` set |
| Regression | `apps/ads/tests/test_ad_lifecycle.py` | `test_transition_to_reject_clears_moderation_failed` | Transitioning to `REJECTED` clears `moderation_failed_at` (mutual exclusivity) |
| Regression | `apps/ads/tests/test_ad_lifecycle.py` | `test_transition_to_moderation_failed_clears_rejected` | Transitioning to `ON_MODERATION_FAILED` clears `rejected_at` |
| Integration | `apps/ads/tests/test_admin_actions.py` (NEW) | `test_approve_ad_uses_transition_to` | Spy on `Ad.transition_to`; assert `approve_ad` does not assign `ad.status` directly |
| Integration | `apps/ads/tests/test_admin_actions.py` (NEW) | `test_reject_ad_uses_transition_to` | Spy on `transition_to`; assert `reject_ad` routes through it, not direct assignment |
| Integration | `apps/ads/tests/test_admin_actions.py` (NEW) | `test_bulk_reject_skips_invalid_transitions` | Bulk reject over mixed statuses logs errors for invalid ones, succeeds for valid ones |
| DB-level | `apps/ads/tests/test_ad_localization.py` or new | `test_checkconstraint_archived_at_if_archived` | `Ad.objects.filter(status=ARCHIVED).update(archived_at=None)` raises `IntegrityError` |
| DB-level | new test | `test_checkconstraint_rejected_at_if_rejected` | Bulk `update(status=REJECTED)` without `rejected_at` raises `IntegrityError` |
| DB-level | new test | `test_checkconstraint_mutual_exclusivity` | Setting both `moderation_failed_at` and `rejected_at` raises `IntegrityError` |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-schema.md` | State Machine section (around `:132-137`) | Add `ON_MODERATION_FAILED → REJECTED` edge to the documented matrix; note admin actions route through `transition_to()` |
| `docs/02-database/db-enums.md` | AdStatus table | Confirm `ON_MODERATION_FAILED` is no longer terminal-only (add `REJECTED` edge) |

---

## AD-002 — No purge job for DELETED status

**Classification:** Simple / Low-risk
**Severity:** HIGH · **Priority:** mandatory

### Preferred Solution

New management command `purge_deleted_ads.py` — a near-exact copy of `purge_rejected_ads.py` (closest analogue: also a terminal status, also a delete-type purge):
- Advisory lock: `AdvisoryLockId.PURGE_DELETED_ADS = 11`
- Cutoff: `timezone.now() - timedelta(days=120)` (4-month retention from `deleted_at`)
- Queryset: `Ad.objects.filter(status=AdStatus.DELETED, deleted_at__lt=cutoff_date)`
- Use existing partial index `IX_ads_purge_deleted`
- Collect `ad_ids` + `storage_keys` from `AdImage` → `queryset.delete()` inside `transaction.atomic()` → `delete_photo()` loop **outside** atomic
- `--dry-run` support

New partial index in `Ad.Meta.indexes` (mirrors `IX_ads_delete_sweep`, `IX_ads_purge_failed`):
```python
models.Index(
    fields=["status", "deleted_at"],
    name="IX_ads_purge_deleted",
    condition=Q(status=AdStatus.DELETED),
)
```

Add `'purge_deleted_ads'` to `hourly_commands` in `docker/entrypoint-scheduler.sh:28-36`.

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Happy path | `apps/core/tests/test_sweep_commands.py` | `test_purge_deleted_ads_deletes_old` | Ads with `DELETED` + `deleted_at` older than 120 days are hard-deleted |
| Happy path | `apps/core/tests/test_sweep_commands.py` | `test_purge_deleted_ads_preserves_recent` | `DELETED` ads newer than 120 days are untouched |
| Happy path | `apps/core/tests/test_sweep_commands.py` | `test_purge_deleted_ads_advisory_lock` | Acquires `AdvisoryLockId.PURGE_DELETED_ADS` (ID 11) |
| Edge | `apps/core/tests/test_sweep_commands.py` | `test_purge_deleted_ads_dry_run` | `--dry-run` deletes nothing, logs count |
| Edge | `apps/core/tests/test_sweep_commands.py` | `test_purge_deleted_ads_skips_non_deleted` | `PUBLISHED`/`REJECTED` ads never touched |
| DB-level | `apps/core/tests/test_migrations.py` | `test_migration_0006_purge_deleted_index` | Migration `0006` adds `IX_ads_purge_deleted` |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-indexes.md` | Index List | Add `IX_ads_purge_deleted` entry |
| `docs/02-database/db-enums.md` | AdStatus table | Add `DELETED → 4 months purge` to retention column |
| `docs/03-ops/docker-deployment.md` | Hourly Sweeps table (`:508-516`) | Add `purge_deleted_ads` row |
| `docker/entrypoint-scheduler.sh` | `hourly_commands` list (`:28-36`) | Add `'purge_deleted_ads'` |

---

## AD-003 — Moderation max-ads check counts failed ads as active

**Classification:** Simple / Low-risk
**Severity:** HIGH · **Priority:** mandatory

### Preferred Solution

Remove `AdStatus.ON_MODERATION_FAILED` from `active_statuses` at `auto_moderation.py:197`:
```python
# Before:
active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION, AdStatus.ON_MODERATION_FAILED]
# After:
active_statuses = [AdStatus.PUBLISHED, AdStatus.ON_MODERATION]
```
This makes the code match its own comment (`# Count only published and on-moderation ads`).

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Happy path | `apps/moderation/tests/test_auto_moderation.py` | `test_failed_ads_excluded_from_active_count` | `ON_MODERATION_FAILED` ad does NOT count toward user's max-ads limit |
| Happy path | `apps/moderation/tests/test_auto_moderation.py` | `test_published_and_on_moderation_count` | `PUBLISHED` + `ON_MODERATION` ads DO count toward limit |
| Edge | `apps/moderation/tests/test_auto_moderation.py` | `test_max_ads_blocked_at_limit` | With `max_ads=2` and 2 active ads, submission is blocked; a 3rd `ON_MODERATION_FAILED` ad does NOT block |
| Regression | `apps/moderation/tests/test_auto_moderation.py` | `test_draft_rejected_archived_deleted_excluded` | All 4 non-active statuses excluded from count |

### Docs Required

| Item | Section | Action |
|------|---------|--------|
| none | — | This is a one-line fix that makes the code match its existing inline comment. No doc change needed. |

---

## AD-004 — Pre-submission `check()` function mutates ad state

**Classification:** Simple / Low-risk
**Severity:** MEDIUM · **Priority:** mandatory

### Preferred Solution

Remove all 7 `_fail_moderation(ad)` calls from `check()` (`auto_moderation.py:254-324`), making it pure read-only validation returning `(passed: bool, error_message: str)`. Update the docstring to reflect no side-effects. `check()` has **zero production callers** (only called in `test_auto_moderation.py:248,258`); `auto_moderate()` is the production handler for status transitions.

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Regression | `apps/moderation/tests/test_auto_moderation.py` | `test_check_does_not_transition_failed_ad` | After `check()` on a failing ad, `ad.status` is still `ON_MODERATION` (not transitioned to `ON_MODERATION_FAILED`) |
| Regression | `apps/moderation/tests/test_auto_moderation.py` | `test_check_does_not_create_audit_log` | No `ModeratorActionLog` or `AnalyticsEvent` created by `check()` |
| Regression | `apps/moderation/tests/test_auto_moderation.py` | `test_check_does_not_set_moderation_failed_at` | `ad.moderation_failed_at` is `None` after `check()` fails |
| Update existing | `apps/moderation/tests/test_auto_moderation.py:252-263` | `test_check_returns_seller_safe_error_on_fail` | Keep return-value assertion; the test currently unknowingly exercises the mutation — now it simply returns `(False, msg)` |

### Docs Required

| Item | Section | Action |
|------|---------|--------|
| none | — | `check()` is not documented in user-facing specs (it's a test-only validation helper). No doc change needed. |

---

## AD-005 — Category rename trigger relies on no-op UPDATE

**Classification:** Complex / High-risk (BEST-PRACTICE — code matches documented pattern, but fragile)
**Severity:** MEDIUM · **Priority:** mandatory
**Reclassified from SPEC-DEVIATION → BEST-PRACTICE** (the no-op pattern is explicitly documented in `db-indexes.md:86-97`).

### Preferred Solution

New migration `0006` — `CREATE OR REPLACE FUNCTION categories_name_propagate()`:
```sql
CREATE OR REPLACE FUNCTION categories_name_propagate() RETURNS TRIGGER AS $$
BEGIN
  UPDATE ads SET category_name = NEW.name WHERE category_id = NEW.id;
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
```
This replaces the no-op `SET category_id = ads.category_id`. The `ads_search_vector_update` BEFORE trigger (#2) still fires and refreshes `category_name` + `search_vector`. Combined into migration `0006` with AD-008.

**Important:** PostgreSQL fires row-level triggers on no-op UPDATEs by default (confirmed via official PG 18 docs). The current code works *only* because of this. The fix makes intent explicit and removes the dependency on trigger-chaining.

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Regression | `apps/ads/tests/test_search_triggers.py:96-103` | `test_category_rename_propagates` | After `category.name = "New"`, all linked ads get `category_name = "New"` (existing test — must still pass) |
| DB-level | `apps/core/tests/test_migrations.py` | `test_migration_0006_categories_trigger` | Migration `0006` contains `CREATE OR REPLACE FUNCTION categories_name_propagate` with `category_name = NEW.name` (not self-assignment) |
| DB-level | `apps/core/tests/test_migrations.py` | `test_migration_0006_reverse` | Reverse SQL restores original no-op body (or `RunSQL.noop`) |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-indexes.md` | `§4.2` Trigger Functions (`:87-97`) | Update the `categories_name_propagate` SQL snippet to show the correct `UPDATE ads SET category_name = NEW.name WHERE category_id = NEW.id`; remove or annotate the `-- trigger #2 recomputes` comment |

---

## AD-006 — `original_language` hardcoded to `bs` in bot handler

**Classification:** Multiple-viable-routes (Minimum enum fix vs. full detection)
**Severity:** LOW (advisory) · **Priority:** advisory

### Preferred Solution (Route 2 — full detection)

1. Add `LanguageLocale.from_code(tag: str | None, *, fallback: LanguageLocale) -> LanguageLocale` classmethod to `core/enums.py:159-178` — normalizes IETF tag (`en-US` → `en`), maps to enum, returns fallback for `None`/unsupported.
2. At `ad_create.py:473`, replace literal `'bs'` with:
   ```python
   original_language=LanguageLocale.from_code(
       message.from_user.language_code,
       fallback=LanguageLocale.BOSNIAN,
   ).value
   ```
3. `message.from_user` is available in `process_preview(message: types.Message, ...)` (`ad_create.py:444`); aiogram `User.language_code` is `str | None`.

**Rejected alternative — Route 1 (enum-only minimum):** Only replaces `"bs"` with `LanguageLocale.BOSNIAN.value`. Resolves the style violation but not the semantics. Acceptable as a stopgap if the team scopes AD-006 to style only.

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Unit | `apps/core/tests/test_language_locale.py` | `test_from_code_ru` | `from_code("ru", fallback=BOSNIAN)` → `LanguageLocale.RUSSIAN` |
| Unit | `apps/core/tests/test_language_locale.py` | `test_from_code_en_with_region` | `from_code("en-US", ...)` → `LanguageLocale.ENGLISH` |
| Unit | `apps/core/tests/test_language_locale.py` | `test_from_code_bs` | `from_code("bs", ...)` → `LanguageLocale.BOSNIAN` |
| Unit | `apps/core/tests/test_language_locale.py` | `test_from_code_none_falls_back` | `from_code(None, fallback=BOSNIAN)` → `LanguageLocale.BOSNIAN` |
| Unit | `apps/core/tests/test_language_locale.py` | `test_from_code_unsupported_falls_back` | `from_code("fr", fallback=BOSNIAN)` → `LanguageLocale.BOSNIAN` |
| Integration | `telegram_bot/tests/test_ad_create.py` (NEW) | `test_original_language_detected_from_user` | `process_preview` with `from_user.language_code="en-US"` → `ad.original_language == "en"` |
| Integration | `telegram_bot/tests/test_ad_create.py` (NEW) | `test_original_language_falls_back_to_bosnian` | User with `language_code=None` → `ad.original_language == "bs"` |
| Regression | `telegram_bot/tests/test_ad_create.py` (NEW) | `test_original_language_not_string_literal` | Source code of `process_preview` has no raw `"bs"` literal |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-enums.md` | `§5.3` LanguageLocale (`:91-103`) | Document `from_code()` classmethod + BOSNIAN fallback for bot path |
| `docs/01-spec/technical-specification.md` | Language Handling (`:95-108`) | Document: `original_language` is derived from Telegram `from_user.language_code`, default `BOSNIAN` when absent/unsupported |

---

## AD-007 — Physical file deletion inside database transaction

**Classification:** Partially STALE → Residual risk (Complex / High-risk)
**Severity:** LOW (advisory) · **Priority:** advisory

### Current State (verified — main claim is RESOLVED)

All 4 sweep/purge commands (`delete_sweep.py`, `purge_failed_ads.py`, `purge_rejected_ads.py`, `sweep_drafts.py`) **already** call `delete_photo()` **outside** their `transaction.atomic()` blocks. Verified in `purge_rejected_ads.py:43-79`:
- `transaction.atomic()` block (line 43) wraps the query + `queryset.delete()` (line 73)
- `transaction.atomic()` closes at line 73
- `delete_photo()` loop (lines 78-79) runs **after** the block

Existing test `test_sweep_commands.py:599-636` (`test_file_deletion_after_commit_not_inside_transaction`) already covers this. The audit finding's primary premise is **no longer applicable**.

### Residual Fix Only

Broaden `delete_photo()` exception handling in `media.py:80-96`:
- Currently catches **only** `FileNotFoundError` (line 94)
- Other `OSError` subtypes (`PermissionError`, `IsADirectoryError`, etc.) propagate uncaught
- Add bounded retry with exponential backoff for transient errors

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| Regression | `apps/core/tests/test_sweep_commands.py:599-636` | `test_file_deletion_after_commit_not_inside_transaction` | (existing) — verify still passes; no changes needed |
| Residual | `telegram_bot/tests/test_media.py` | `test_delete_photo_handles_os_error` | `delete_photo` on `PermissionError` → logs warning, does NOT raise |
| Residual | `telegram_bot/tests/test_media.py` | `test_delete_photo_retries_on_temporary_failure` | `delete_photo` on transient `OSError` → retries with backoff, succeeds on 2nd attempt |
| Residual | `telegram_bot/tests/test_media.py` | `test_delete_photo_file_not_found_silent` | `delete_photo` on missing file → logs warning, no exception (existing behavior preserved) |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-retention.md` (NEW) | — | Create: document sweep/purge command schedule, retention windows, and the photo-deletion-outside-transaction guarantee. Note AD-007 verified stale for the main claim. |

---

## AD-008 — Multilingual `search_vector` not implemented

**Classification:** Complex / High-risk (cross-finding)
**Severity:** HIGH · **Priority:** advisory (cross-finding, not in the 7 numbered findings)

### Preferred Solution

New migration `0006` — `CREATE OR REPLACE FUNCTION ads_search_vector_fn()` matching `db-indexes.md:55-76` exactly:
```sql
CREATE OR REPLACE FUNCTION ads_search_vector_fn() RETURNS TRIGGER AS $$
DECLARE v_cat TEXT;
BEGIN
  SELECT name INTO v_cat FROM categories WHERE id = NEW.category_id;
  NEW.category_name := v_cat;
  NEW.search_vector :=
    setweight(to_tsvector('russian',   coalesce(NEW.title,'')),  'A') ||
    setweight(to_tsvector('russian',   coalesce(NEW.description,'')), 'B') ||
    setweight(to_tsvector('simple',    coalesce(NEW.title_bs,'')),  'A') ||
    setweight(to_tsvector('simple',    coalesce(NEW.description_bs,'')), 'B') ||
    setweight(to_tsvector('english',   coalesce(NEW.title_en,'')),  'A') ||
    setweight(to_tsvector('english',   coalesce(NEW.description_en,'')), 'B') ||
    setweight(to_tsvector('simple',    coalesce(v_cat,'')), 'C');
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
```
Plus a one-time backfill: `UPDATE ads SET title = title;` (forces the BEFORE trigger to recompute `search_vector` with the new multi-lang body for existing rows).

**Important:** Uses ONE `search_vector` column (not per-language columns). Only 3 languages: Russian, Bosnian (`simple` config), English (`english` config). This matches `db-enums.md` (exactly 3 `LanguageLocale`s) and `db-indexes.md:55-76`.

The model fields `title_bs`, `title_en`, `description_bs`, `description_en` already exist (added by migration `0003_ad_i18n_fields.py`) — only the trigger function lags behind.

### Tests Required

| Scope | Test File | Test Case | Assertions |
|-------|-----------|-----------|------------|
| DB-level | `apps/core/tests/test_migrations.py` | `test_migration_0006_search_vector_fn_multilang` | Migration `0006` contains multi-language `ads_search_vector_fn` with `title_bs`/`title_en`/`description_bs`/`description_en` |
| Regression | `apps/ads/tests/test_search_triggers.py` | `test_category_rename_propagates` | Still passes after trigger function `CREATE OR REPLACE` (combined with AD-005) |
| Integration | `apps/ads/tests/test_ad_search.py` (NEW) | `test_search_en_content` | Insert ad with only `title_en` set; `@@ plainto_tsquery('english', ...)` matches via `search_vector` |
| Integration | `apps/ads/tests/test_ad_search.py` (NEW) | `test_search_bs_content` | Insert ad with only `title_bs` set; searchable via `simple` config match |
| Integration | `apps/ads/tests/test_ad_search.py` (NEW) | `test_search_falls_back_to_russian` | Ad with only `title` (Russian base) is searchable via `russian` config |
| Integration | `apps/ads/tests/test_ad_search.py` (NEW) | `test_category_name_in_search_vector` | Search term matching a renamed category matches the ad's `search_vector` |

### Docs Required

| File | Section | Action |
|------|---------|--------|
| `docs/02-database/db-indexes.md` | `§4.1` Search Vector (`:55-76`) | Confirm the deployed trigger matches the documented multi-language body; mark the discrepancy as resolved |
| `docs/01-spec/technical-specification.md` | Full-Text Search section | Document the implemented multi-language `search_vector` strategy (Russian/Bosnian/English weights A/B/C) |

---

## Rollout Ordering

Findings are implemented in waves to respect dependencies:

1. **Wave A (simple, independent):** AD-003, AD-004 — single-file changes, no migrations, no interdependencies.
2. **Wave B (migration-dependent, can combine):** AD-005 + AD-008 → single migration `0006` (both `CREATE OR REPLACE FUNCTION`). Plus AD-001's single-row routing + matrix update (no migration needed for the Python-side change; the matrix edit is a code edit to `ALLOWED_TRANSITIONS`).
3. **Wave C (new command + index migration):** AD-002 — new command file + index in `Ad.Meta` → migration `0006` CheckConstraints + the `IX_ads_purge_deleted` index can all go in the same migration `0006` (Django groups all model changes into one migration per `makemigrations` run). The command file + scheduler entry are code changes.
4. **Wave D (bot-only):** AD-006 — `LanguageLocale.from_code()` classmethod + `ad_create.py:473` change. No migration.
5. **Wave E (residual, bot-only):** AD-007 — `media.py` exception broadening + retry. No migration.

> Note: Waves B and C share migration `0006` (one `makemigrations` generates all model changes together). The implementation will be split by finding for commit granularity, but a single migration file results.
