# Problem Report: Analytics view test suite fails against `ck_ads_published_at_if_published`

**Date:** 2026-08-18
**Found during:** plan `14_seller-cabinet-ad-gallery` (regression/validation step)

## Description

The entire `src/backend/apps/analytics/tests/test_views.py` suite errors at fixture
`setUpTestData` with a database `IntegrityError`:

```
django.db.utils.IntegrityError: new row for relation "ads" violates check constraint
"ck_ads_published_at_if_published"
```

The failing INSERT is a `PUBLISHED` `Ad` created without `published_at`.

## Affected modules

- `src/backend/apps/analytics/tests/test_views.py` — `_make_ad()` helper and both
  `TestSellerTrustDashboardView` / `TestModerationAnalyticsView` classes.

## Risk

High for the test/CI pipeline: the analytics dashboard authentication and moderation
authorization tests (including the `@login_required` redirect and staff-only `Http404`
contracts) cannot run in any environment whose test database carries the `0006` schema.
This masked the very behavior verified by the same workflow's plan tasks.

## Root cause

`_make_ad()` (used by `setUpTestData`) creates an `Ad` with
`status=AdStatus.PUBLISHED` but never sets `published_at`. Migration
`apps/ads/migrations/0006_ad_ix_ads_purge_deleted_and_more.py` installs check constraint
`ck_ads_published_at_if_published`, which requires
`NOT(status = 'published') OR published_at IS NOT NULL`. Any `PUBLISHED` row with a NULL
`published_at` is therefore rejected.

Verified as pre-existing: the failure reproduces identically with the plan's changes
stashed (original committed code), so it is not caused by any plan modification.

## Architectural impact

None. This is a test-fixture defect, not a production-schema or business-logic issue. The
constraint is intentional and correct (a published ad must have a publish timestamp).

## Suggested direction

Update `_make_ad()` to include `published_at` for `PUBLISHED` ads, e.g.:

```python
defaults["published_at"] = timezone.now() if status == AdStatus.PUBLISHED else None
```

(and for `ARCHIVED`/`DELETED` statuses, the corresponding `*_at` field if the constraint
set requires it). Re-run `uv run pytest src/backend/apps/analytics/tests/test_views.py`
to confirm the suite is green. This is out of scope for the current plan and was left for
a dedicated task.
