# Anchored Summary: Fixture Deduplication Analysis

> **Generated:** 2026-08-21T13:46:16+02:00
> **Status:** Research phase complete — ready for subagent handoff
> **Objective:** Categorize and plan subagent execution for remaining A.2/A.3 fixture/helper deduplication work across 19+ files in the Mko Bazuna project.

---

## Objective

- Produce a categorized analysis of 19 remaining fixture/helper deduplication files for the Mko Bazuna A.2/A.3 task, then recommend subagent batch sizes and per-category approaches.

## Important Details

- Root conftest at `src/backend/conftest.py` provides canonical `seller` (telegram_id=900000001), `user` (telegram_id=900000002), `category`, `city` fixtures + `create_test_ad(user, category, city, *, title, description, status, price, source, **kwargs)` helper.
- `pyproject.toml` sets `pythonpath = ["src", "src/backend"]` — `from conftest import create_test_ad` works from ANY test file.
- Conftest fixture discovery is directory-hierarchy based: `src/backend/conftest.py` fixtures are visible to `src/backend/**/tests/` but NOT to `src/telegram_bot/tests/` (separate conftest at `src/telegram_bot/tests/conftest.py`).
- `create_test_ad` cannot backdate `created_at` (auto_now_add=True). Backdating pattern: create first, then `Ad.objects.filter(pk=ad.pk).update(created_at=...)` + `ad.refresh_from_db()`.
- `create_test_ad` defaults to `status=AdStatus.ON_MODERATION`; local helpers default to `PUBLISHED` — callers must pass `status=AdStatus.PUBLISHED` explicitly.
- `create_test_ad` defaults to `source=AdSource.TELEGRAM` and `price=100`; some local `_make_ad` helpers omit these — usually harmless but verify test assertions.
- Only 2 conftest.py files exist project-wide: `src/backend/conftest.py` and `src/telegram_bot/tests/conftest.py`.

## Work State

### Completed

- [x] Read 14+ representative files across all 5 categories
- [x] Verified root conftest exports (seller/user/category/city fixtures, `create_test_ad` function, `_set_status_timestamp` helper)
- [x] Confirmed 4 "user" test files already use root conftest's `user` fixture — NO local fixture definitions exist in any of them
- [x] Confirmed 19 files already import `from conftest import create_test_ad` (the 12 "already refactored" files + new plan test files)
- [x] Confirmed `test_ad_localization.py` uses `Ad.__new__(Ad)` (in-memory, no DB) — intentional skip

### Active

- (none — analysis phase, no code changes made yet)

### Blocked

- (none)

## Next Move

1. Hand off this analysis summary to subagent with explicit batch assignments (see batch recommendations below).
2. Verify test suite passes with `--create-db` after each batch.

## Relevant Files

| File | Role |
|---|---|
| `src/backend/conftest.py` | Canonical fixtures (`seller`, `user`, `category`, `city`) + `create_test_ad` helper; reference for all replacement calls |
| `pyproject.toml` | `pythonpath = ["src", "src/backend"]` at line 48-49; confirms `from conftest import create_test_ad` works project-wide |
| `src/backend/apps/core/tests/test_sweep_commands.py` | Local seller/category/city fixtures + complex `_make_ad` (create-then-UPDATE with `created_at` backdating + status transitions) |
| `src/backend/apps/analytics/tests/test_*.py` (6 files) | TestCase + local `_make_user`/`_make_category`/`_make_city`/`_make_ad`; only `_make_ad` replaces with `create_test_ad`; `test_moderation_analytics.py` also backdates `created_at` |
| `src/backend/apps/ads/tests/test_dashboard_stats.py` | TestCase + `_make_ad` with `created_at` backdating via UPDATE |
| `src/telegram_bot/tests/test_ad_lifecycle.py` | Local fixtures typed as `object` (wrong); can import `create_test_ad` but CANNOT drop local fixtures (bot tests outside `src/backend/` hierarchy) |
| `src/backend/apps/users/tests/test_deletion.py` | Has local `user` fixture (telegram_id=900000001, conflicts with root conftest's `seller`); tests use `user.telegram_id` dynamically, safe to remove |
| `src/backend/apps/ads/tests/test_ad_lifecycle.py` | Reference "already done" pattern: imports `create_test_ad`, uses root conftest fixtures, no local fixtures |

---

## Categorization of 19 Remaining Files

| Category | Files | Characteristics |
|---|---|---|
| **(a) Already clean** | `test_account_state.py`, `test_consent_records.py`, `test_consent_context.py`, `test_logout.py` | All already use root conftest `user` fixture. `test_account_state` has `_make_user` (creates Users with flags — keep). No ad helpers. **Verify only — likely no changes.** |
| **(b) Simple pytest** | `test_search_view.py`, `test_favorites.py`, `test_preferred_city_readback.py`, `test_preferred_city.py`, `test_gallery_markup.py`, `test_auto_moderation.py` | Pytest tests. Remove local seller/category/city fixtures. Keep file-specific fixtures (buyer, podgorica, budva, etc.). Add `status=AdStatus.PUBLISHED` to `create_test_ad` calls. |
| **(c) `created_at` backdating** | `test_sweep_commands.py`, `test_moderation_analytics.py` | Local `_make_ad` does create-then-UPDATE to backdate `created_at` + set status. Replace with `create_test_ad(...)` then `Ad.objects.filter(pk=ad.pk).update(created_at=...)` + `ad.refresh_from_db()`. |
| **(d) Analytics TestCase** | `test_dashboard_stats.py`, `test_rollup_daily_metrics.py`, `test_views.py`, `test_ads_published.py`, `test_trust_analytics.py`, `test_seller_stats.py` | `django.test.TestCase` + `setUpTestData`. KEEP `_make_user`/`_make_category`/`_make_city`/`_make_event` (plain functions). DELETE `_make_ad`. Replace calls with `create_test_ad(...)`. |
| **(e) Intentional skip** | `test_ad_localization.py` | Uses `Ad.__new__(Ad)` (in-memory, SimpleTestCase). `_make_ad` doesn't touch DB or constraints. |
| **Additional finding** | `test_deletion.py` | Local `user` fixture with telegram_id=900000001 (same as root conftest's `seller`). Tests use `user.telegram_id` dynamically, safe to remove. |

## Per-Category Edge Cases

- **Type annotations:** `telegram_bot/tests/test_ad_lifecycle.py` uses `-> object` for seller/category/city fixtures. Fix to `-> User`/`-> Category`/`-> City` with proper imports.
- **Bot conftest constraint:** Bot tests can import `create_test_ad` via `from conftest import create_test_ad` (pythonpath) but CANNOT resolve root conftest fixtures. Local fixtures must stay — only type annotation + helper replacement.
- **Import cleanup:** After removing local helpers, `from django.utils import timezone` often becomes unused. Check before committing.
- **`_create_published_ad` in `test_gallery_markup.py`:** Creates AdImage rows alongside. Replace inner `Ad.objects.create(...)` with `create_test_ad(seller, category, city, status=AdStatus.PUBLISHED)` then keep AdImage creation.
- **`_published_ad` callers:** Signature → `create_test_ad(seller, category, city, status=AdStatus.PUBLISHED, **kwargs)`.
- **`_create_ad` in `test_auto_moderation.py`:** Class method using `self.*`. Replace with `create_test_ad(self.user, self.category, self.city, ...)`.
- **`test_sweep_commands.py` `_make_ad`:** Most complex — first creates as DRAFT, then UPDATEs to target status + timestamps. Only `created_at` needs post-create UPDATE in the new version.
- **TestCase `_make_user` helpers:** Create test-specific users with non-default telegram_ids/parameters. Plain functions — KEEP as-is.

## Recommended Batch Sizes for Subagent Tasks

| Batch | Files (count) | Type | Max concurrent | Rationale |
|---|---|---|---|---|
| 1 | `test_search_view.py`, `test_favorites.py`, `test_gallery_markup.py` | (b) simple pytest | 3 | No TestCase, no backdating, no bot constraints. Fastest review cycle. Good warmup. |
| 2 | `test_preferred_city_readback.py`, `test_preferred_city.py` | (b) + multi-fixture | 2 | Multi-fixture files with file-specific fixtures (buyer, podgorica, budva). Need careful diff review. |
| 3 | `test_dashboard_stats.py`, `test_moderation_analytics.py` | (c) + (d) backdating + TestCase | 2 | `test_moderation_analytics` needs `created_at` backdating split pattern. Double complexity. |
| 4 | `test_rollup_daily_metrics.py`, `test_views.py` | (d) TestCase, no backdating | 2 | Straightforward TestCase → `create_test_ad` swap. But `_make_user`/`_make_category`/`_make_city` must stay. |
| 5 | `test_ads_published.py`, `test_trust_analytics.py`, `test_seller_stats.py` | (d) TestCase, no backdating | 3 | Simple swap — no backdating, no multi-fixture complexity. Can batch slightly larger. |
| 6 | `test_sweep_commands.py` | (b) + (c) most complex | 1 | Multi-step create-then-UPDATE backdating for `created_at` + status transitions. Single file, heavy diff. |
| 7 | `test_auto_moderation.py` | (b) method-to-function | 1 | `_create_ad` is a class method. Method call → function call with `self.*` args. Different refactor shape. |
| 8 | `telegram_bot/tests/test_ad_lifecycle.py` | (b) bot constraints | 1 | Can import `create_test_ad` but cannot drop local fixtures. Type annotation fix from `object` → proper types. Unique bot-conftest constraint. |
| 9 | `test_deletion.py` + verify (a) files | cleanup + verification | 1 | Single local `user` fixture to remove. The 4 "already clean" files just need verification. |

## Key Subagent Guidelines (to prevent timeout)

- Do NOT read all files upfront. Read only the files in the current batch.
- Do NOT do full-file rewrites. Use targeted `replace` operations (remove fixture block, add import, replace helper calls one by one).
- Run `pytest --collect-only` on the changed file after edits to verify no import/fixture errors.
- Run the actual test file with `--create-db -x -q` to verify behavior before moving to the next batch.
- For TestCase files, run with `python manage.py test <app>.tests.<module>` since `pytestmark` markers aren't present.
- Always add `from conftest import create_test_ad` at the top of each file (after existing imports).
- After removing local fixtures, check for unused imports before committing.
- Always add `status=AdStatus.PUBLISHED` to `create_test_ad` calls that relied on local helper's PUBLISHED default.
