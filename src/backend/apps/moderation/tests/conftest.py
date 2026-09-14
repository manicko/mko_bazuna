"""
Shared fixtures for moderation tests.

Ensures ``ModerationCriteria`` singleton state is restored to defaults after
each test, preventing cross-test contamination under xdist parallel execution
with shared ``--reuse-db``.
"""

from typing import Final

import pytest
from django.core.cache import cache

from apps.moderation.models import ModerationCriteria

# All editable ModerationCriteria fields (excludes id, updated_at, updated_by).
_CRITERIA_FIELDS: Final[tuple[str, ...]] = (
    "title_min_length",
    "title_max_length",
    "description_min_length",
    "description_max_length",
    "price_required",
    "min_images",
    "max_images",
    "banned_words",
    "max_ads_per_user",
    "duplicate_title_threshold",
)


@pytest.fixture(autouse=True)
def _reset_moderation_criteria():
    """Restore all ModerationCriteria fields after each test (save-and-restore).

    Save-and-restore pattern: snapshot every criteria field before the test
    runs, then after ``yield`` call ``cache.clear()`` and restore the original
    values via ``QuerySet.update()``. The ``cache.clear()`` is required because
    ``update()`` bypasses the ``post_save`` signal
    (``invalidate_criteria_cache_on_save``) that would normally invalidate the
    LocMem cache, so without it ``_get_cached_criteria`` could return stale
    values for up to the 5-minute TTL.
    """
    snapshot = dict(
        ModerationCriteria.objects.filter(pk=1)
        .values(*_CRITERIA_FIELDS)
        .first()
        or {}
    )
    yield
    cache.clear()
    if snapshot:
        ModerationCriteria.objects.filter(pk=1).update(**snapshot)
