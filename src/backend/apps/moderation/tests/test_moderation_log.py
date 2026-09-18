"""
Direct unit tests for moderation_log.set_published() (DB-002 TOCTOU fix).

Tests the authoritative lock + re-count + raise behavior inside
set_published(), independent of the advisory check in auto_moderate().
"""

import pytest
from django.core.cache import cache

from apps.core.enums import AdStatus
from apps.moderation.models import ModerationCriteria
from apps.moderation.services.exceptions import MaxAdsExceeded
from apps.moderation.services.moderation_log import set_published
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def moderation_criteria():
    """Create the ModerationCriteria singleton with default safe values.

    Clears the cache so both cached (auto_moderate) and uncached
    (set_published) readers see the persisted value.
    """
    cache.clear()
    criteria = ModerationCriteria.get_singleton()
    criteria.title_min_length = 5
    criteria.title_max_length = 100
    criteria.description_min_length = 10
    criteria.description_max_length = 2000
    criteria.price_required = True
    criteria.min_images = 1
    criteria.max_images = 5
    criteria.banned_words = []
    criteria.max_ads_per_user = 10
    criteria.duplicate_title_threshold = 85
    criteria.save()
    return criteria


# ---------------------------------------------------------------------------
# Tests: TOCTOU-safe cap enforcement in set_published()
# ---------------------------------------------------------------------------


class TestSetPublishedCapGuard:
    """Tests for the locked re-count + raise behavior in set_published()."""

    def test_set_published_raises_at_cap(
        self, moderation_criteria, seller, category, city
    ):
        """At cap: set_published re-counts under lock and raises MaxAdsExceeded.

        With max=1 and 1 PUBLISHED + 1 ON_MODERATION (both in the counted
        set), the locked re-count = 2 >= 1, so the ad is NOT transitioned.
        """
        moderation_criteria.max_ads_per_user = 1
        moderation_criteria.save()

        create_test_ad(
            seller,
            category,
            city,
            title="Published Ad",
            description="Published ad description text",
            status=AdStatus.PUBLISHED,
        )
        on_moderation_ad = create_test_ad(
            seller,
            category,
            city,
            title="Pending Ad",
            description="Pending ad description text",
            status=AdStatus.ON_MODERATION,
        )

        with pytest.raises(MaxAdsExceeded) as exc_info:
            set_published(on_moderation_ad)

        exc = exc_info.value
        assert exc.user_id == seller.id
        assert exc.limit == 1
        assert exc.current_count == 2  # 1 PUBLISHED + 1 ON_MODERATION

        on_moderation_ad.refresh_from_db()
        assert on_moderation_ad.status == AdStatus.ON_MODERATION

    def test_set_published_under_cap_succeeds(
        self, moderation_criteria, seller, category, city
    ):
        """Under cap: set_published transitions ON_MODERATION -> PUBLISHED.

        With max=3 and 1 PUBLISHED + 1 ON_MODERATION, locked re-count = 2 < 3.
        """
        moderation_criteria.max_ads_per_user = 3
        moderation_criteria.save()

        create_test_ad(
            seller,
            category,
            city,
            title="Published Ad",
            description="Published ad description text",
            status=AdStatus.PUBLISHED,
        )
        on_moderation_ad = create_test_ad(
            seller,
            category,
            city,
            title="Pending Ad",
            description="Pending ad description text",
            status=AdStatus.ON_MODERATION,
        )

        set_published(on_moderation_ad)

        on_moderation_ad.refresh_from_db()
        assert on_moderation_ad.status == AdStatus.PUBLISHED
        assert on_moderation_ad.published_at is not None

    def test_lock_released_on_rollback(
        self, moderation_criteria, seller, category, city
    ):
        """After MaxAdsExceeded rolls back the atomic block, the user row is
        accessible — the select_for_update() lock was released.
        """
        moderation_criteria.max_ads_per_user = 1
        moderation_criteria.save()

        create_test_ad(
            seller,
            category,
            city,
            title="Published Ad",
            description="Published ad description text",
            status=AdStatus.PUBLISHED,
        )
        on_moderation_ad = create_test_ad(
            seller,
            category,
            city,
            title="Pending Ad",
            description="Pending ad description text",
            status=AdStatus.ON_MODERATION,
        )

        with pytest.raises(MaxAdsExceeded):
            set_published(on_moderation_ad)

        # Lock released by transaction rollback; plain query succeeds.
        user = User.objects.get(pk=seller.id)
        assert user.telegram_id == seller.telegram_id

        on_moderation_ad.refresh_from_db()
        assert on_moderation_ad.status == AdStatus.ON_MODERATION
