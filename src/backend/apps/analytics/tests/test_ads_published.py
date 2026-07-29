"""
Tests for ads_published metric in SellerStats.

Verifies that ads_published counts only PUBLISHED ads, not drafts,
rejected, or other non-published statuses. This tests the fix for F4
(ads_published misleadingly counted all ads regardless of status).
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.ads.models import Ad
from apps.analytics.services import SellerStats
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus
from apps.locations.models import City
from apps.users.models import User


def _make_user(telegram_id: int = 990200001) -> User:
    """Create a User with sensible defaults."""
    return User.objects.create(
        telegram_id=telegram_id,
        chat_id=telegram_id,
        username=None,
        password="x",
    )


def _make_category(slug: str = "stats-test-cat") -> Category:
    """Create a Category."""
    return Category.objects.create(
        name="Stats Test Category",
        slug=slug,
    )


def _make_city(slug: str = "stats-test-city") -> City:
    """Create a City."""
    return City.objects.create(
        country_code="ME",
        name="Stats Test City",
        region="Stats Test Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Stats Test Ad",
    status: AdStatus = AdStatus.PUBLISHED,
) -> Ad:
    """Create an Ad with sensible defaults."""
    return Ad.objects.create(
        user=user,
        title=title,
        description="Stats test description",
        category=category,
        city=city,
        category_name=category.name,
        status=status,
        source=AdSource.TELEGRAM,
    )


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    },
)
class TestAdsPublishedMetric(TestCase):
    """Tests for the ads_published metric in SellerStats."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()
        cls.user = _make_user(telegram_id=990200001)

        # Create 3 published ads, 2 draft ads, 1 rejected ad
        for i in range(3):
            _make_ad(
                cls.user,
                cls.category,
                cls.city,
                title=f"Published {i}",
                status=AdStatus.PUBLISHED,
            )

        _make_ad(
            cls.user,
            cls.category,
            cls.city,
            title="Draft Ad",
            status=AdStatus.DRAFT,
        )
        _make_ad(
            cls.user,
            cls.category,
            cls.city,
            title="Another Draft",
            status=AdStatus.DRAFT,
        )
        _make_ad(
            cls.user,
            cls.category,
            cls.city,
            title="Rejected Ad",
            status=AdStatus.REJECTED,
        )

    def test_ads_published_counts_only_published(self) -> None:
        """ads_published should count only PUBLISHED ads, not drafts or rejected."""
        stats = SellerStats(user_id=self.user.id).get_stats()
        self.assertEqual(stats["ads_published"], 3)

    def test_ads_published_with_zero_published(self) -> None:
        """Seller with only non-published ads gets 0 ads_published."""
        user = _make_user(telegram_id=990200002)
        _make_ad(
            user,
            self.category,
            self.city,
            title="Only Draft",
            status=AdStatus.DRAFT,
        )
        stats = SellerStats(user_id=user.id).get_stats()
        self.assertEqual(stats["ads_published"], 0)

    def test_per_ad_stats_includes_all_ads(self) -> None:
        """Per-ad stats should include all user ads regardless of status."""
        stats = SellerStats(user_id=self.user.id).get_stats()
        # 3 published + 2 drafts + 1 rejected = 6 total ads
        self.assertEqual(len(stats["per_ad_stats"]), 6)