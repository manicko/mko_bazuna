# Phase 05 — Ad Lifecycle, Categories & Moderation: Implementation Complete

**Source plan:** `05-ad-lifecycle-validated-findings.md`
**Status:** DONE
**Date:** 2026-09-24
**Implemented by:** Executor subagent
**Validated by:** Validation Agent

All four Phase 05 findings (AD-001..AD-004) are resolved. AD-001, AD-002, and
AD-003 were implemented in this pass; AD-004 was already resolved by prior
commits (see below).

## Finding resolution summary

| ID | Severity | Status | Implementation |
|:---|:---|:---|:---|
| AD-001 | CRITICAL | Resolved | `soft_delete_user_ads` now routes each ad through `transition_to(AdStatus.DELETED)` per row (fires `post_save`, enforces the transition matrix, re-reads DB state) instead of a bulk `QuerySet.update()`. The redundant `transaction.on_commit` cache bump was removed (the `post_save` signal bumps the search cache version). `Ad.transition_to`'s DELETED branch now persists `updated_at` so soft-deleted ads no longer retain a stale "last modified" timestamp. |
| AD-002 | HIGH | Resolved | `_validate_max_ads_per_user(user_id, max_ads, ad_id)` now excludes the in-flight ad (mirroring `_is_duplicate_title`), and `set_published` excludes the current ad from the authoritative locked re-count. A user at the limit boundary (`max_ads-1` active ads) can now submit/approve the `max_ads`-th ad. |
| AD-003 | MEDIUM | Resolved | Documentation-only: added `ARCHIVED → ON_MODERATION` to the legal-transition list in `docs/01-spec/spec-index.md`, `docs/02-database/db-schema.md`, and the `Ad` class-level docstring. No code change required. |
| AD-004 | MEDIUM | Already resolved | **Variant 1** (`archive_sweep` missing `select_for_update`) — merged into Phase 03 DB-010, fixed in commit `65b9254`. **Variant 2** (hard-delete sweeps collecting media keys before bulk DELETE) — fixed in commit `a117ed2` (ENT-005): the `delete_photo()` loops were removed and physical file deletion is routed through the `AdImage` `pre_delete` signal's `on_commit` callback, which only fires for rows actually cascade-deleted. No reimplementation needed. |

## Files changed (implementation pass)

- `src/backend/apps/users/services/deletion.py` — AD-001
- `src/backend/apps/ads/models.py` — AD-001 (DELETED transition refreshes `updated_at`) + AD-003 (class docstring)
- `src/backend/apps/moderation/services/auto_moderation.py` — AD-002
- `src/backend/apps/moderation/services/moderation_log.py` — AD-002
- `src/backend/testing/moderation_fixtures.py` — AD-002 (fixture signature)
- `src/backend/apps/moderation/tests/test_auto_moderation.py` — AD-002 tests
- `src/backend/apps/moderation/tests/test_moderation_log.py` — AD-002 tests
- `src/backend/apps/users/tests/test_deletion.py` — AD-001 test (`updated_at` refresh)
- `src/backend/apps/search/tests/test_search_cache.py` — AD-001 test comments
- `docs/01-spec/spec-index.md` — AD-003
- `docs/02-database/db-schema.md` — AD-003

## Verification

- `ruff check` on all changed Python files: pass
- `basedpyright` on all changed Python files: 0 errors / 0 warnings
- Targeted tests (deletion, moderation, search cache, ads edit, bot ad create/lifecycle): pass
- Full fast test gate (`PYTEST_SKIP_MARKERS=seed`): **2072 passed, 0 failed**

## Rollback

Each fix is independently revertible:

- **AD-001:** revert to bulk `QuerySet.update()` + `on_commit` compensation, and drop the `updated_at` persistence in `transition_to`'s DELETED branch. No data migration needed.
- **AD-002:** revert quota checks to include the current ad; revert tests to the off-by-one behavior.
- **AD-003:** revert documentation-only changes.
