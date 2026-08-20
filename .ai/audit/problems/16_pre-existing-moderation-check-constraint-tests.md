# Problem: pre-existing tests create ads violating status check constraints

**Status:** resolved
**Discovered during:** plan `16_user-cabinet_plan` (broad regression run) and `22_seed-category-coverage_plan`
**Scope:** unrelated (pre-existing) — does not block either plan

## Description

Several test suites create `Ad` rows with a given status but do NOT set the
corresponding status timestamp, so the strict check constraints raise
`IntegrityError` on insert:

- `apps/moderation/tests/test_priority.py` and
  `apps/moderation/tests/test_auto_moderation.py::TestCheckFunction::test_failed_ad_not_counted_in_active_limit`
  create `Ad` rows with `status=REJECTED` (and `ON_MODERATION_FAILED`) but
  missing `rejected_at` / `moderation_failed_at`
  (constraints `ck_ads_rejected_at_if_rejected` and
  `ck_ads_moderation_failed_at_if_failed`).
- `apps/seed/tests/test_seed.py::TestImageGenerator` creates a `PUBLISHED` ad
  (line ~261) without `published_at`
  (constraint `ck_ads_published_at_if_published`). Both test methods
  (`test_generates_ad_images`, `test_image_keys_have_correct_format`) error at
  setup.

## Affected modules

- `apps/moderation/tests/test_priority.py` (`_make_ad` fixture + callers)
- `apps/moderation/tests/test_auto_moderation.py`
- `apps/seed/tests/test_seed.py::TestImageGenerator` (setup creates `PUBLISHED` ad without `published_at`)

## Root cause

The test fixtures were written before the strict status-timestamp check
constraints (or were not updated when the constraints were added). The same
class of bug was fixed incrementally for other suites in earlier commits
(e.g. `fix(analytics-tests): set published_at in _make_ad`), but the
moderation fixtures were missed.

## Risk

Low. Failing tests only; no production impact. They currently fail in CI and
mask real regressions in priority/auto-moderation coverage.

## Resolution

All affected test suites were updated to set the status-specific timestamp when
creating `Ad` rows:

- `apps/moderation/tests/test_priority.py` — `_make_ad` now sets `rejected_at`
  for `REJECTED`, `moderation_failed_at` for `ON_MODERATION_FAILED`, and
  `published_at` for `PUBLISHED` (mirroring the published/archived fixes).
- `apps/moderation/tests/test_auto_moderation.py` — `_create_ad` updated with the
  same status-timestamp logic; added `from django.utils import timezone` import.
- `apps/seed/tests/test_seed.py::TestImageGenerator` — `setUpTestData` now sets
  `published_at` on the `PUBLISHED` ad.
- `apps/search/tests.py` — `_create_ad` updated to handle all status timestamps;
  ad titles in `test_category_match_expands_to_descendants` fixed from English
  to Russian ("Трансорт") to match the `config=russian` FTS config.

All 50+ previously-failing tests across these suites now pass. Verified via:
- 934 total tests collected (markers registered correctly)
- 16 seed tests collected with `-m seed`
- 93 unit tests collected with `-m unit`
- Full test run: 380 integration + 376 backend tests pass
- Lint (`ruff check`) and typecheck (`basedpyright`) pass on all changed files

## Suggested direction

Update each `_make_ad` fixture (and any inline ad creation) to set the status
timestamp matching the status: `rejected_at` when `status=REJECTED`,
`moderation_failed_at` when `status=ON_MODERATION_FAILED`, and `published_at`
when `status=PUBLISHED` (mirroring the published/archived fixes), so the
retained assertions exercise the intended behaviour.
