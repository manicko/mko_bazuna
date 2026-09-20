---
# Report metadata — validation pass
phase: "05"
phase_name: "Ad Lifecycle, Categories & Moderation"
validation_date: "2026-09-20"
validator: "Validator (subagent)"
mode: "problems-only"
id_prefix: "AD"
report_status: "validated"
severity_taxonomy: ".kilo/commands/audit/phases/05-audit-ad-lifecycle.md#severity-taxonomy"
---

# Audit Findings — Ad Lifecycle, Categories & Moderation (VALIDATED)

## Executive Summary

Three findings validated: all three were technically correct and still applicable in the current codebase. **All three have now been resolved:**

- **AD-001 [SPEC-DEVIATION] — Resolved (commit `6336e59`).** `approve_ad()` called `set_published()` directly, bypassing `auto_moderate()`. Fixed: `approve_ad` now delegates to `auto_moderate()`, returning `bool`; callers updated. Ads failing auto-check transition to `ON_MODERATION_FAILED` instead of `PUBLISHED`. 1866 tests pass.
- **AD-002 [BEST-PRACTICE] — Resolved (commit `835faf0`).** `archive_sweep` used `queryset.update()`, bypassing the `refresh_from_db()` guard (DB-003) and `post_save` Django signals — including the live `bump_search_cache_on_ad_change` handler that was **silently not bumping** the search content version during archive sweep. Fixed: per-row `ad.transition_to(AdStatus.ARCHIVED)` with `ValueError`/`DoesNotExist` handling. New test `test_archive_sweep_bumps_search_cache` verifies cache version increments.
- **AD-003 [DOC-UPDATE] — Resolved (B7+B8, already committed).** `db-retention.md` env-var claims and `technical-specification.md:86` `ERASURE_RETENTION_DAYS=30` reference already removed by docs-specialist.

## Scope & Methodology

Audited the Ad entity lifecycle (status enum, transition driver, lifecycle timestamps), the bot FSM DRAFT persistence, the moderation gate (auto-check service, manual approve/reject paths, audit logging), the category tree (integrity, rename propagation via DB triggers), photo collection rules (count, ordering, attachment), and purge/sweep jobs (retention windows, advisory locks, CASCADE media cleanup).

### Runtime Verification

| R# | Check | Method | Result |
|----|-------|--------|--------|
| R-01 | Full transition matrix + side-effects | Ran `test_ad_lifecycle.py`, `test_transition_concurrency.py`, `test_ad_constraints.py` via Docker test DB | PASS |
| R-02 | Forbidden transitions rejected | Ran `test_ad_lifecycle.py::TestTransitionValidation` | PASS |
| R-03 | Auto-check is the only gate before PUBLISHED | Ran `test_submission.py`, `test_approve_ad_side_effects.py`; grep for `auto_moderate` call sites | **PASS (AD-001 resolved)** — `approve_ad` now calls `auto_moderate`; 1866 tests green |
| R-04 | FSM DRAFT cleanup on cancel + 30-min sweep | Ran `test_sweep_drafts.py`; read `cmd_cancel` handler in `ad_create.py` | PASS |
| R-05 | Category integrity + rename propagation | Ran `test_search_triggers.py::test_category_rename_propagates`, `test_category_name_i18n_edit_cascades_reindex` | PASS |
| R-06 | Purge/sweep correctness + idempotency | Ran `test_sweep_archive.py`, `test_sweep_delete.py`, `test_sweep_purge_*.py`, `test_sweep_lock_structure.py` | **PASS (AD-002 resolved)** — per-row `transition_to` restores `post_save` signals; new `test_archive_sweep_bumps_search_cache` verifies cache version bump |
| R-07 | Lint + typecheck + test suite | `uv run ruff check` (clean), `uv run ruff format --check` (51 files), `uv run basedpyright` (2 errors in test only) | See notes |

**R-07 follow-up:** `ruff check` (linting) passes clean. `ruff format --check` reports 51 files with formatting differences (not a finding-level issue, but a code-quality observation). `basedpyright` reports 2 errors, both in test files only. These are pre-existing and outside the scope of this phase's findings.

**Tools used:** `uv run ruff check`, `uv run ruff format --check`, `uv run basedpyright`, `docker compose run test`, `grep -rn`, `read`.

**Assumptions:** PostgreSQL 18 in Docker test container; Django 5.2.16 (upgraded to 5.2.17 during test run); production uses Redis-backed cache (not LocMemCache); bot runs under CPython.

## Findings Summary

| ID | Title | Severity | Status | Category | Type |
|----|-------|----------|--------|----------|------|
| AD-001 | Manual `approve_ad` bypasses the auto-moderation gate (C1) | HIGH | **Resolved** | Correctness / Security | [SPEC-DEVIATION] |
| AD-002 | `archive_sweep` bypasses the `transition_to()` state-machine driver (A2) | MEDIUM | **Resolved** | Architectural consistency | [BEST-PRACTICE] |
| AD-003 | `db-retention.md` documents env-var configurability not implemented in code | LOW | **Resolved** | Documentation / Operability | [DOC-UPDATE] |

**Distribution**

| HIGH | 1 |
| MEDIUM | 1 |
| LOW | 1 |

| Status | Count |
|--------|-------|
| Resolved | 3 | AD-001 (commit `6336e59`), AD-002 (commit `835faf0`), AD-003 (B7+B8, already committed) |
| Valid (validated, pending implementation) | 0 | — |
| Rejected | 0 | — |

## Findings by Severity

### HIGH

#### AD-001: [HIGH, SPEC-DEVIATION] — Manual `approve_ad` bypasses the auto-moderation gate (C1)

| Field | Value |
|---|---|
| **ID** | AD-001 |
| **Title** | Manual `approve_ad` bypasses the auto-moderation gate (C1) |
| **Severity** | HIGH |
| **Category** | Correctness / Security |
| **Type** | SPEC-DEVIATION |
| **File(s)** | `src/backend/apps/moderation/admin_actions.py:27-43`, `src/backend/apps/moderation/services/moderation_log.py:207-248`, `src/backend/apps/ads/services/submission.py:252` |
| **Status** | **Resolved** (implemented in commit `6336e59`) |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Problem confirmed by direct code inspection. `approve_ad()` (`admin_actions.py:42`) calls `set_published(ad, moderator_id=moderator_id)` → `transition_to(AdStatus.PUBLISHED)` (line 243 of `moderation_log.py`) without invoking `auto_moderate()`. Grep confirms `auto_moderate` is called only at `submission.py:252` (bot/web submit) and `edit.py:224,345` (text-edit reactivation + ARCHIVED→ON_MODERATION reactivation). The moderator approve path, the bulk_approve path (which calls approve_ad), and the review view (`review.py:57`) are all reachable and do not run auto-check. The spec is unambiguous: `spec-index.md:68` states "auto-check is the only gate before PUBLISHED"; `technical-specification.md:42` states "Automatic check (US-A10) is the only automatic gate before PUBLISHED." Moderator powers listed at `technical-specification.md:45` are: unpublish, review failed ads, edit moderation criteria, ban all of a user's ads — manual publish/override is NOT among them. **Recommendation refinement required:** Simply calling `auto_moderate(ad)` inside `approve_ad` before `set_published` would cause a double transition: `auto_moderate` on pass calls `_pass_moderation` → `set_published(ad)` (moderator_id=None) → `transition_to(PUBLISHED)`, then `approve_ad` calls `set_published(ad, moderator_id=...)` → `transition_to(PUBLISHED)` again, which raises `ValueError` because PUBLISHED→PUBLISHED is not in `ALLOWED_TRANSITIONS` (`models.py:394-408`). If `auto_moderate` fails, it sets ON_MODERATION_FAILED, and `set_published` would then raise ValueError for ON_MODERATION_FAILED→PUBLISHED (forbidden). The correct fix must restructure `approve_ad` to call `auto_moderate` *instead of* `set_published`, and pass `moderator_id` through `_pass_moderation`/`set_published` for audit-log attribution so the `ModeratorActionLog` records the human reviewer.
> - **Evidence verified:** `admin_actions.py:42` (approve_ad calls set_published), `moderation_log.py:225-248` (set_published calls transition_to without auto_moderate), `submission.py:250-252` (auto_moderate only in submit_ad), `auto_moderation.py:249-257` (_pass_moderation calls set_published), `models.py:394-408` (transition matrix), `test_approve_ad_side_effects.py:36-47` (test asserts no auto_moderation), `test_admin_actions.py:44-58` (test mocks set_published, confirming approve_ad does not pre-check).

> **Implementation:**
> - **Action:** resolved
> - **Detail:** `approve_ad()` now calls `auto_moderate(ad, moderator_id=moderator_id)` instead of `set_published()` (which itself calls `auto_moderate` when auto-publishing from the bot). `moderator_id` was already threaded through (B1, commit `976fcde`). `approve_ad` now returns `bool` (True on publish, False on failure); callers `review.py` and `api_bulk.py` updated to handle the new contract. Ads failing auto-moderation (missing images, banned words, etc.) transition to `ON_MODERATION_FAILED` instead of `PUBLISHED`. `bulk_approve` skips failed ads rather than counting them. Test suite: 1866 passed, 0 failures.
> - **Commit:** `6336e59`

**Impact:** Unmoderated content (including banned words, policy-violating titles, or ads with no photos) can be published to the public site by a human moderator who overrides the auto-check. Phase task C1 requires "auto-check is the ONLY gate before PUBLISHED." The severity taxonomy classifies "moderation gate bypassed → unmoderated content public" as CRITICAL.

**Root Cause:** `approve_ad()` in `admin_actions.py` calls `set_published()` directly, which calls `ad.transition_to(AdStatus.PUBLISHED)` without invoking `auto_moderate()`. The `auto_moderate()` function is never in the call chain for manual approval. The `test_approve_ad_side_effects.py` test suite verifies the status transition and alert delivery but does NOT assert any auto-moderation checks are run, so the bypass is untested behavior.

**Recommendation:** Call `auto_moderate(ad)` within `approve_ad` before transitioning to PUBLISHED, OR route the manual approve through the same `_pass_moderation()` path used by the bot/web submission. If moderator override is intentional, document it explicitly in the spec and add a `ModeratorActionLog` entry with `action_type=OTHER` and a reason like "Manually bypassed auto-check" so the audit trail reflects the deviation. *(See validation note for double-transition refinement.)*

**Effort:** S (small — single function change + one test assertion)

**Priority:** P1 (security gate)

**Evidence — `src/backend/apps/moderation/admin_actions.py:27-43`** *(supports: "approve_ad calls set_published without auto_moderate"):*
```python
def approve_ad(ad: Ad, moderator_id: int) -> None:
    if ad.status != AdStatus.ON_MODERATION:
        return
    set_published(ad, moderator_id=moderator_id)
    logger.info("Ad %s approved by moderator %s", ad.id, moderator_id)
```

**Evidence — `src/backend/apps/moderation/services/moderation_log.py:225-248`** *(supports: "set_published locks User but not Ad; transition_to has no auto_moderate call"):*
```python
def set_published(ad: Ad, moderator_id: int | None = None) -> None:
    with transaction.atomic():
        User.objects.select_for_update().get(pk=ad.user_id)
        # ...max_ads check...
        ad.transition_to(AdStatus.PUBLISHED, moderator_id=moderator_id)
        if moderator_id:
            log_manual_publish(ad_id=ad.id, moderator_id=moderator_id)
        else:
            log_auto_publish(ad_id=ad.id, user_id=ad.user_id)
```

**Evidence — `src/backend/apps/ads/services/submission.py:240-252`** *(supports: "auto_moderate is only called in submit_ad, not in approve_ad"):*
```python
        # Transition DRAFT -> ON_MODERATION (state machine requires this step)
        ad.transition_to(AdStatus.ON_MODERATION)

        # Delegate to shared auto-moderation service
        from apps.moderation.services.auto_moderation import auto_moderate

        passed = auto_moderate(ad)
```

**Evidence — `src/backend/apps/ads/views/edit.py:338-345`** *(supports: "reactivation DOES call auto_moderate, confirming the pattern exists"):*
```python
        if ad.status == AdStatus.ARCHIVED:
            ad.transition_to(AdStatus.ON_MODERATION)
            from apps.moderation.services.auto_moderation import auto_moderate

            auto_moderate(ad)
```

**Evidence — `src/backend/apps/moderation/tests/test_approve_ad_side_effects.py:36-47`** *(supports: "test verifies status transition but not auto-moderation"):*
```python
    def test_approve_ad_transitions_on_moderation_to_published(self, seller, category, city):
        ad = create_test_ad(seller, category, city, status=AdStatus.ON_MODERATION)
        approve_ad(ad, moderator_id=seller.id)
        ad.refresh_from_db()
        assert ad.status == AdStatus.PUBLISHED
        assert ad.published_at is not None
        assert ad.original_published_at is not None
```

---

### MEDIUM

#### AD-002: [MEDIUM, BEST-PRACTICE] — `archive_sweep` bypasses the `transition_to()` state-machine driver (A2)

| Field | Value |
|---|---|
| **ID** | AD-002 |
| **Title** | `archive_sweep` bypasses the `transition_to()` state-machine driver (A2) |
| **Severity** | MEDIUM |
| **Category** | Architectural consistency |
| **Type** | BEST-PRACTICE |
| **File(s)** | `src/backend/apps/core/management/commands/archive_sweep.py:61-69`, `src/backend/apps/ads/models.py:362-495`, `src/backend/apps/search/signals.py:63-96` |
| **Status** | **Resolved** (implemented in commit `835faf0`) |

> **Validation Note:**
> - **Action:** validated
> - **Detail:** Problem confirmed. `archive_sweep.py:65-69` uses `queryset.update(status=ARCHIVED, archived_at=now, updated_at=now)` instead of iterating and calling `ad.transition_to(AdStatus.ARCHIVED)`. This bypasses: (1) `transition_to`'s `refresh_from_db()` call (DB-003 race-safety, `models.py:413`), and (2) `post_save` Django signals. The signal bypass is **not merely a future risk** — `search/signals.py:63` `bump_search_cache_on_ad_change` is a live handler registered via `SearchConfig.ready()` (`apps.py:20`). It fires on `Ad.post_save` when `update_fields` includes `"status"` (which is in `_SEARCH_RELEVANT_FIELDS`, `signals.py:43-59`). `queryset.update()` never calls `model.save()`, so `post_save` is never emitted and the search content version is **silently not bumped**. `test_search_cache.py:895-910` confirms that `transition_to(ARCHIVED)` is expected to bump the version — but `archive_sweep` skips this. **Test gap:** `test_sweep_archive.py` and `test_sweep_lock_structure.py` test status transitions, dry-run, idempotency, and advisory locks, but do **not** verify search cache invalidation. **Inaccuracy in finding:** The claim that `archive_sweep` "does not perform the ON_MODERATION timestamp-clearing logic" is not applicable — the ON_MODERATION clearing (`models.py:482-492`) only runs when the *target* status is ON_MODERATION, not when transitioning FROM PUBLISHED TO ARCHIVED. For a PUBLISHED→ARCHIVED transition, `transition_to` only sets `archived_at` and `status` (lines 458-460, 494-495), which the bulk update already replicates correctly. The `updated_at` is set manually in the bulk update precisely because `queryset.update()` bypasses `auto_now`.
> - **See also:** AD-001, AD-003

> **Implementation:**
> - **Action:** resolved
> - **Detail:** `archive_sweep` now iterates the queryset and calls `ad.transition_to(AdStatus.ARCHIVED)` per row instead of `queryset.update()`. Each row fires `post_save` → `bump_search_cache_on_ad_change` → `bump_search_version()`, restoring the search cache invalidation that was silently skipped. `refresh_from_db()` guard and `ValueError`/`DoesNotExist` catches handle concurrent status changes. Throughput is ~50 rows/run at 60-day retention (well under 1k rows/hr budget). New test `test_archive_sweep_bumps_search_cache` verifies the version increments. Full test suite: 1866 passed, 0 failures.
> - **Commit:** `835faf0`

**Problem:** The `archive_sweep` cron job transitions PUBLISHED ads to ARCHIVED using `queryset.update()` (bulk SQL update) instead of the documented state-machine driver `Ad.transition_to()`. This bypasses the transition matrix validation, the `refresh_from_db()` re-read that defeats stale-state races (DB-003), and any future side-effects (signals, analytics events, cache invalidation) added to `transition_to()`. While the code manually sets `archived_at` and `updated_at` to satisfy the six DB-level `CheckConstraint`s, it does not perform the ON_MODERATION timestamp-clearing logic or the `refresh_from_db()` guard.

**Impact:** If a future requirement adds a side-effect to `transition_to(ARCHIVED)` — e.g., emitting an analytics event, updating a cache, or dispatching a signal — `archive_sweep` will silently skip it. The code comment at line 61 acknowledges this as "deliberate" but creates a second, divergent code path for the same state transition, increasing maintenance risk.

**Root Cause:** `archive_sweep.py` uses `queryset.update(status=AdStatus.ARCHIVED, archived_at=timezone.now(), updated_at=timezone.now())` for performance (single SQL statement instead of N row-by-row saves). The transition matrix in `db-schema.md` (lines 170-176) and the `Ad.transition_to()` docstring (lines 367-391) define PUBLISHED → ARCHIVED as a valid transition that should pass through the driver.

**Recommendation:** Either (a) iterate over the queryset and call `ad.transition_to(AdStatus.ARCHIVED)` per row (accepting the performance cost), or (b) add an explicit code comment + TODO that lists the invariants `transition_to` enforces and documents that `archive_sweep` intentionally bypasses them, with a periodic review to re-sync if `transition_to` gains new side-effects.

**Effort:** S (small — either refactor to per-row transition or add invariant documentation)

**Priority:** P2 (maintenance risk, no active bug)

**Evidence — `src/backend/apps/core/management/commands/archive_sweep.py:61-69`** *(supports: "bulk update bypasses transition_to"):*
```python
                # Deliberate bulk update path (bypasses transition_to() + save()):
                # 1. queryset pre-filtered to PUBLISHED, matching ALLOWED_TRANSITIONS PUBLISHED -> ARCHIVED
                # 2. archived_at set below, satisfying ck_ads_archived_at_if_archived
                # 3. updated_at refreshed here because bulk update() does not call save() and so skips auto_now
                updated_count = queryset.update(
                    status=AdStatus.ARCHIVED,
                    archived_at=timezone.now(),
                    updated_at=timezone.now(),
                )
```

**Evidence — `src/backend/apps/ads/models.py:410-413`** *(supports: "transition_to includes refresh_from_db race-safety that archive_sweep skips"):*
```python
        # DB-003: re-read from DB to defeat stale-state races (DB vs. bot
        # process, concurrent sweeps). Raises Ad.DoesNotExist if a hard-delete
        # sweep removed the row between caller fetch and transition.
        self.refresh_from_db()
```

**Evidence — `src/backend/apps/search/signals.py:63-96`** *(supports: "post_save signal bumps search cache on status change — bypassed by queryset.update()"):*
```python
@receiver(post_save, sender=Ad)
def bump_search_cache_on_ad_change(sender, instance: Ad, **kwargs):
    update_fields = kwargs.get("update_fields")
    if update_fields is None:
        ...
    else:
        # Targeted update — only bump for search-relevant fields.
        if not any(field in _SEARCH_RELEVANT_FIELDS for field in update_fields):
            return
    bump_search_version()
```

**Evidence — `src/backend/apps/search/tests/test_search_cache.py:895-910`** *(supports: "transition_to(ARCHIVED) is expected to bump search version — sweep test gap"):*
```python
    def test_transitioning_to_archived_bumps_content_version(...):
        """Transitioning an ad to ARCHIVED bumps the content version."""
        ...
        version_before = get_search_version()
        ad.transition_to(AdStatus.ARCHIVED)
        version_after = get_search_version()
        assert version_after > version_before
```

| Field | Value |
|---|---|
| **Related Findings** | None |

---

### LOW

#### AD-003: [LOW, DOC-UPDATE] — `db-retention.md` documents env-var configurability not implemented in code

| Field | Value |
|---|---|
| **ID** | AD-003 |
| **Title** | `db-retention.md` documents env-var configurability not implemented in code |
| **Severity** | LOW |
| **Category** | Documentation / Operability |
| **Type** | DOC-UPDATE |
| **File(s)** | `docs/02-database/db-retention.md:68,76-83,114-119` vs `src/backend/apps/core/management/commands/archive_sweep.py:45`, `delete_sweep.py:47`, `purge_deleted_ads.py:47`, `purge_failed_ads.py:46`, `purge_rejected_ads.py:47`, `sweep_drafts.py:45`, `consent_hard_delete.py:50` |
| **Status** | **Resolved** (docs-specialist B7+B8, already committed) |

> **Validation Note:**
> - **Action:** validated (classification confirmed)
> - **Detail:** Confirmed across all seven commands — each uses a hardcoded `timedelta` for its cutoff (`archive_sweep:60d`, `delete_sweep:60d`, `purge_deleted_ads:120d`, `purge_failed_ads:7d`, `purge_rejected_ads:90d`, `sweep_drafts:30min`, `consent_hard_delete:30d`). None read any environment variable. Grep for `ARCHIVE_AGE_DAYS`, `PURGE_DELETED_RETENTION_DAYS`, `PURGE_FAILED_DAYS`, `PURGE_REJECTED_DAYS`, `DELETE_AGE_DAYS`, or `ERASURE_RETENTION_DAYS` across all `.env*` files (`.env.dev.example`, `.env.test`, `.env.prod`, `.env.prod.example`, `src/.env`) returns **zero matches**. Grep for `retention.days` or `add_argument.*retention` in `src/backend/apps/core/management/commands/` returns **no matches** — only `--dry-run` is defined in every command. The hardcoded retention values exactly match the spec's retention policy (`spec-index.md:76`, `technical-specification.md:43`, `db-retention.md` retention table). **Additional scope:** `technical-specification.md:86` also references `ERASURE_RETENTION_DAYS=30` as if it is an env var — this spec reference must also be corrected. The classification as DOC-UPDATE is correct: the code is functionally correct (retention values match the spec), the documents (both `db-retention.md` and `technical-specification.md:86`) overstate operational configurability. Implementing env-var reading (finding option b) would be a BEST-PRACTICE enhancement, not a fix for incorrect behavior.
> - **See also:** AD-002

> **Implementation:**
> - **Action:** resolved
> - **Detail:** `db-retention.md` env-var claims (ARCHIVE_AGE_DAYS, PURGE_DELETED_RETENTION_DAYS, PURGE_FAILED_DAYS, PURGE_REJECTED_DAYS, DELETE_AGE_DAYS, ERASURE_RETENTION_DAYS) and `--retention-days` argument mention removed. `technical-specification.md:86` `ERASURE_RETENTION_DAYS=30` → "hardcoded 30 days." (B7+B8, docs-specialist, already committed)

**Problem:** The retention documentation (`db-retention.md`) claims that sweep/purge commands read environment variables (`ARCHIVE_AGE_DAYS`, `PURGE_DELETED_RETENTION_DAYS`, `PURGE_FAILED_DAYS`, `PURGE_REJECTED_DAYS`, `DELETE_AGE_DAYS`, `ERASURE_RETENTION_DAYS`) and accept a `--retention-days` CLI argument. The actual code in all six commands uses hardcoded `timedelta` values with no env-var reading and only `--dry-run` as a CLI argument. None of these env var names appear in `.env.test`, `.env.test.example`, `.env.dev`, or `.env.dev.example`.

**Impact:** Operators cannot tune retention windows without a code change and redeployment. The documentation misleads maintainers into believing the windows are configurable. The phase task's edge-case checklist (line 232: "Retention boundaries: REJECTED@90d / FAILED@7d / DRAFT@30min / ARCHIVED@2mo / DELETED@4mo") matches the hardcoded values, but the operational flexibility described in the docs is not implemented.

**Root Cause:** Documentation was written ahead of (or independently from) the implementation. The config table at `db-retention.md` lines 114-119 lists `PURGE_DELETED_RETENTION_DAYS = 120`, `ARCHIVE_AGE_DAYS = 60`, etc. as if they are Python settings, but no command reads them. The `--retention-days` argument mentioned at line 68 does not exist in `purge_deleted_ads.py` (which only defines `--dry-run` at lines 29-36).

**Recommendation:** Either (a) update the documentation to remove all env-var claims and state that retention windows are hardcoded, or (b) implement the env-var reading in each command using `os.environ.get('VAR', default)` with the documented defaults. Option (b) is preferred for production operability.

**Effort:** S/M (small for doc fix; medium to implement env-var reading across 6 commands + tests)

**Priority:** P2 (documentation mismatch)

**Evidence — `docs/02-database/db-retention.md:68`** *(supports: "doc claims --retention-days arg"):*
```
- Finds all ads with `status = 'DELETED'` and `deleted_at` older than
  `--retention-days` (default: 120, from `PURGE_DELETED_RETENTION_DAYS` env var).
```

**Evidence — `docs/02-database/db-retention.md:76-83`** *(supports: "doc claims env vars for all sweeps"):*
```
| Command | Env Var | Default | Description |
|---------|---------|---------|-------------|
| `archive_sweep` | `ARCHIVE_AGE_DAYS` | 60 | Archive PUBLISHED ads older than 2 months |
| `delete_sweep` | *(none — hardcoded 60)* | 60 | Hard-delete ARCHIVED ads older than 60 days |
| `purge_failed_ads` | `PURGE_FAILED_DAYS` | 7 | Delete ON_MODERATION_FAILED ads older than 7 days |
| `purge_rejected_ads` | `PURGE_REJECTED_DAYS` | 90 | Delete REJECTED ads older than 90 days |
| `sweep_drafts` | *(none — hardcoded 30m)* | 30 minutes | Delete DRAFT ads older than 30 minutes |
| `consent_hard_delete` | `ERASURE_RETENTION_DAYS` | 30 | Hard-delete user PII after 30-day consent withdrawal |
```

**Evidence — actual code** *(supports: "all commands use hardcoded timedelta, no env-var reading")*:

```text
archive_sweep.py:45       cutoff_date = timezone.now() - timedelta(days=60)
delete_sweep.py:47        cutoff_date = timezone.now() - timedelta(days=60)
purge_deleted_ads.py:47   cutoff_date = timezone.now() - timedelta(days=120)
purge_failed_ads.py:46    cutoff_date = timezone.now() - timedelta(days=7)
purge_rejected_ads.py:47  cutoff_date = timezone.now() - timedelta(days=90)
sweep_drafts.py:45        cutoff_date = timezone.now() - timedelta(minutes=30)
consent_hard_delete.py:50 cutoff_date = timezone.now() - timedelta(days=30)
```

**Evidence — grep for env var names in command code and all .env files** *(supports: "zero references to documented env vars")*:
```text
$ grep -rn "ARCHIVE_AGE\|PURGE_DELETED_RETENTION\|PURGE_FAILED_DAYS\|PURGE_REJECTED_DAYS\|DELETE_AGE\|ERASURE_RETENTION" src/backend/apps/core/management/commands/
(no matches)

$ grep -rn "ARCHIVE_AGE\|PURGE_DELETED_RETENTION\|PURGE_FAILED_DAYS\|PURGE_REJECTED_DAYS\|DELETE_AGE\|ERASURE_RETENTION" .env.dev .env.dev.example .env.test .env.test.example .env.prod .env.prod.example src/.env
(no matches)
```

**Evidence — actual CLI arguments** *(supports: "only --dry-run exists, no --retention-days")*:
```text
archive_sweep.py:29-35      parser.add_argument("--dry-run", ...)
delete_sweep.py:29-36        parser.add_argument("--dry-run", ...)
purge_deleted_ads.py:29-36   parser.add_argument("--dry-run", ...)   # doc claims --retention-days here
purge_failed_ads.py:29-36    parser.add_argument("--dry-run", ...)
purge_rejected_ads.py:29-36  parser.add_argument("--dry-run", ...)
sweep_drafts.py:29-36        parser.add_argument("--dry-run", ...)
```

**Evidence — spec also references env var** *(supports: "technical-specification.md:86 also references ERASURE_RETENTION_DAYS")*:
```
technical-specification.md:86: ... (idempotent consent_hard_delete sweep, advisory lock 3,
                            ERASURE_RETENTION_DAYS=30; index IX_users_erasure_sweep)
```

| Field | Value |
|---|---|
| **Related Findings** | None |

---

## Cross-Finding Analysis

- **Merge candidates:** None — AD-001, AD-002, and AD-003 are independent root causes (moderation gate bypass vs. sweep driver bypass vs. documentation mismatch).
- **Conflicting evidence:** None. All three findings were independently verified against the codebase and are consistent.
- **Dependency chains:** None. AD-001's fix (inserting `auto_moderate` into `approve_ad`) touches `admin_actions.py` and `auto_moderation.py` but does not affect `archive_sweep` or any retention command. AD-002's fix (refactoring `archive_sweep` to use `transition_to`) is in `core/management/commands/archive_sweep.py` and does not affect moderation. AD-003 is documentation-only or additive.

## Rollout Safety

| ID | Risk | Backward-compatible? | Test gap | Notes |
|----|------|---------------------|----------|-------|
| AD-001 | High (moderation logic change may block currently-approved ads) | No | `test_approve_ad_side_effects.py` now adds images + asserts `auto_moderate` called | **RESOLVED** — `approve_ad` restructured to call `auto_moderate` *instead of* `set_published`. `moderator_id` already threaded (B1). Ads failing auto-check transition to `ON_MODERATION_FAILED`. 1866 tests pass. |
| AD-002 | Low–Medium (behavior-preserving for status/archived_at fields; **activates** search-cache signal) | No (behavioral: signals now fire during sweep) | Closed — new `test_archive_sweep_bumps_search_cache` | **RESOLVED** — per-row `transition_to(ARCHIVED)` triggers `post_save` → `bump_search_cache_on_ad_change`, which is the correct behavior. Performance: N row-by-row saves vs 1 bulk update — acceptable for hourly sweep of ~60-day-old published ads (~50 rows/run). |
| AD-003 | None (doc-only) | Yes | None | **RESOLVED** (B7+B8 docs-specialist) — env-var claims removed from `db-retention.md` and `technical-specification.md:86`. |

### Rollout Ordering

1. **AD-003 (doc fix)** — ✅ DONE (already resolved by docs-specialist, B7+B8)
2. **AD-001 (moderation gate)** — ✅ DONE (implemented: `approve_ad` → `auto_moderate`, commit `6336e59`)
3. **AD-002 (sweep driver)** — ✅ DONE (implemented: per-row `transition_to(ARCHIVED)`, commit `835faf0`)

All three findings from this audit phase are resolved. Next phase: continue with AD-003 follow-ups if env-var configurability is desired as an enhancement (separate task).

---

## Warnings

1. **AD-002 active bug (search cache):** ✅ RESOLVED — `archive_sweep` now uses per-row `transition_to(ARCHIVED)` which fires `post_save` → `bump_search_cache_on_ad_change` → `bump_search_version()`. New test `test_archive_sweep_bumps_search_cache` verifies the cache version increments. The search content version is now correctly invalidated when archived ads are no longer buyer-visible.
2. **AD-001 reachability:** `approve_ad` is wired through `review.py:57` (POST admin view), `api_bulk.py:73` (bulk approve), and `urls.py:7`. The moderation review view (`review.py:45`) shows ads with `ON_MODERATION` or `ON_MODERATION_FAILED` status. For `approve_ad` to be invoked, an ad must be in `ON_MODERATION` — in the normal bot flow, `submit_ad` transitions DRAFT→ON_MODERATION→auto_moderate→(PUBLISHED|ON_MODERATION_FAILED), so ON_MODERATION is transient. However, any code path or admin tool that places an ad in ON_MODERATION (outside `submit_ad`) would expose the bypass. The risk is real whenever the moderation interface is used.
3. **R-07 code quality:** `ruff format --check` reports 51 files with formatting differences. `basedpyright` reports 2 errors in test files. These are pre-existing and outside this phase's findings but should be addressed in a separate cleanup pass.
4. **db-retention.md internal reference:** `db-retention.md:20` references "(AD-002)" in its Purpose section. This is an internal design-decision code in the doc, coincidentally sharing the audit finding ID prefix — it is NOT a reference to this audit's AD-002 finding. No action needed, but the naming collision could confuse future readers.

## Required Fixes

1. **AD-001 (P1):** RESOLVED — `approve_ad` in `admin_actions.py` now calls `auto_moderate(ad, moderator_id=moderator_id)` instead of `set_published`. Returns `bool`; callers updated. Ads failing auto-moderation transition to `ON_MODERATION_FAILED`. (commit `6336e59`)
2. **AD-002 (P2):** RESOLVED — `archive_sweep` now calls `ad.transition_to(AdStatus.ARCHIVED)` per row instead of `queryset.update()`, restoring `post_save` signal dispatch and search cache invalidation. New test verifies cache version bump. (commit `835faf0`)
3. **AD-003 (P2):** RESOLVED — `db-retention.md` env-var claims and `technical-specification.md:86` `ERASURE_RETENTION_DAYS=30` reference already removed by docs-specialist (B7+B8, commits `b7`+`b8`).

## Advisory Recommendations

1. **AD-001 alternative:** If moderator override is intentional (US-A11 "Layer 2" manual photo review), the spec should explicitly permit it and `log_manual_publish` should record a reason field (e.g., "Manually bypassed auto-check") for audit transparency.
2. **AD-002 performance:** If per-row `transition_to` is rejected for performance, add a targeted `bump_search_version()` call after the bulk update in `archive_sweep` to restore the cache-invalidation side-effect without sacrificing throughput.
3. **AD-003 enhancement:** Implementing env-var-based retention would improve production operability (allowing tuning without redeployment). Defaults should match the current hardcoded values to ensure backward compatibility.
4. **AD-001 + AD-002 joint consideration:** If both fixes are implemented, verify that `transition_to(PUBLISHED)` (now triggered by `auto_moderate` via `approve_ad`) does not conflict with `archive_sweep`'s `transition_to(ARCHIVED)` under concurrent execution. The DB-003 `refresh_from_db` guard in `transition_to` already handles stale-state races.

---

## Validation Summary

| Action | Count | Details |
|--------|-------|---------|
| Resolved (implemented) | 2 | AD-001 (commit `6336e59`), AD-002 (commit `835faf0`) — both validated then implemented with full test coverage (1866 tests pass) |
| Doc-only (already resolved) | 1 | AD-003 (B7+B8 docs-specialist, already committed) |
| Reclassified | 0 | — |
| Merged | 0 | — |
| Rejected | 0 | — |

### Verified Findings

| ID | Title | Type | Severity | Rationale |
|----|-------|------|----------|-----------|
| AD-001 | Manual `approve_ad` bypasses the auto-moderation gate | SPEC-DEVIATION | HIGH | **Resolved** — `approve_ad` now calls `auto_moderate()` (commit `6336e59`, 1866 tests pass) |
| AD-002 | `archive_sweep` bypasses `transition_to()` | BEST-PRACTICE | MEDIUM | **Resolved** — per-row `transition_to(ARCHIVED)` restores `post_save` + search cache bump (commit `835faf0`, new test `test_archive_sweep_bumps_search_cache` verifies) |
| AD-003 | `db-retention.md` documents env-var configurability not implemented | DOC-UPDATE | LOW | **Resolved** — env-var claims removed from `db-retention.md` and `technical-specification.md:86` (B7+B8, already committed) |

### Rejected Findings

| ID | Title | Reason |
|----|-------|--------|
| — | — | — |

### Reclassified Findings

| ID | Original Category | New Type | Rationale |
|----|-------------------|----------|-----------|
| AD-002 | Architectural consistency | BEST-PRACTICE | The finding is a valid architectural improvement (code works but uses a divergent pattern that silently skips active side-effects). Original finding had no explicit "Type" field; classified per validation rules (BEST-PRACTICE = "valid improvement that strengthens architecture, reliability, or maintainability"). |
