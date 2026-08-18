# Problem: moderation priority tests create ads violating status check constraints

**Status:** open
**Discovered during:** plan `16_user-cabinet_plan` (broad regression run)
**Scope:** unrelated (pre-existing) — does not block the cabinet plan

## Description

`apps/moderation/tests/test_priority.py` and
`apps/moderation/tests/test_auto_moderation.py::TestCheckFunction::test_failed_ad_not_counted_in_active_limit`
create `Ad` rows with `status=REJECTED` (and `ON_MODERATION_FAILED`) but do
NOT set the corresponding status timestamps (`rejected_at` /
`moderation_failed_at`). The pre-existing check constraints
`ck_ads_rejected_at_if_rejected` and `ck_ads_moderation_failed_at_if_failed`
require those timestamps, so every such insert raises `IntegrityError`.

## Affected modules

- `apps/moderation/tests/test_priority.py` (`_make_ad` fixture + callers)
- `apps/moderation/tests/test_auto_moderation.py`

## Root cause

The test fixtures were written before the strict status-timestamp check
constraints (or were not updated when the constraints were added). The same
class of bug was fixed incrementally for other suites in earlier commits
(e.g. `fix(analytics-tests): set published_at in _make_ad`), but the
moderation fixtures were missed.

## Risk

Low. Failing tests only; no production impact. They currently fail in CI and
mask real regressions in priority/auto-moderation coverage.

## Suggested direction

Update the `_make_ad` fixture (and any inline ad creation) to set
`rejected_at` when `status=REJECTED` and `moderation_failed_at` when
`status=ON_MODERATION_FAILED` (mirroring the published/archived fixes), so the
retained assertions exercise the intended behaviour.
