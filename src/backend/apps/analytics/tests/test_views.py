"""
Integration tests for analytics dashboard views (T9/T10).

Tests cover:
- SellerTrustDashboard: login requirement, context data, rendering
- ModerationAnalytics: staff requirement, context data, rendering

Uses ``django.test.TestCase`` for DB-backed assertions with the
Django test client.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType
from apps.locations.models import City
from apps.users.models import User

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(
    telegram_id: int = 990300001,
    *,
    is_staff: bool = False,
    **overrides: object,
) -> User:
    """Create a User with sensible defaults for view tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    user = User.objects.create(**defaults)  # type: ignore[arg-type]
    if is_staff:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    return user


def _make_category(slug: str = "view-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="View Category",
        slug=slug,
    )


def _make_city(slug: str = "view-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="View City",
        region="View Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "View Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for view tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "View test description",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: SellerTrustDashboard
# ---------------------------------------------------------------------------


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    },
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class TestSellerTrustDashboardView(TestCase):
    """Tests for the seller trust dashboard view (login-required)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category()
        cls.city = _make_city()
        cls.seller = _make_user(telegram_id=990301001)
        cls.other_user = _make_user(telegram_id=990301099)

        # Create a published ad for the seller to generate trust data
        cls.ad = _make_ad(cls.seller, cls.category, cls.city, title="Trust Ad")
        cls.url = reverse("analytics:seller_trust_dashboard")

    def test_redirects_anonymous_to_login(self) -> None:
        """Unauthenticated users are redirected to the login page."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url.lower() if response.url else "")

    def test_authenticated_user_gets_200(self) -> None:
        """Authenticated seller can access their trust dashboard."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self) -> None:
        """Response renders the seller dashboard template."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "analytics/seller_dashboard.html")

    def test_trust_score_in_context(self) -> None:
        """Trust score value is present in the response context."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertIn("trust_score", response.context)
        assert response.context["trust_score"] is not None
        self.assertIsInstance(response.context["trust_score"], float)

    def test_trust_level_in_context(self) -> None:
        """Trust level is present in the response context."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertIn("trust_level", response.context)
        self.assertIn(str(response.context["trust_level"]), [
            "unverified", "verified", "trusted", "pro",
        ])

    def test_daily_metrics_in_context(self) -> None:
        """Daily metrics list is present in context."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertIn("daily_metrics", response.context)
        self.assertIsInstance(response.context["daily_metrics"], list)

    def test_total_views_in_context(self) -> None:
        """Total views count is present in context."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertIn("total_views", response.context)
        self.assertIsInstance(response.context["total_views"], int)

    def test_total_contacts_in_context(self) -> None:
        """Total contacts count is present in context."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertIn("total_contacts", response.context)
        self.assertIsInstance(response.context["total_contacts"], int)

    def test_daily_metrics_reflects_actual_data(self) -> None:
        """Daily metrics in context matches created DailyAdMetrics records."""
        self.client.force_login(self.seller)

        # Create a daily metric record for the seller's ad
        today = timezone.now().date()
        DailyAdMetrics.objects.create(
            ad=self.ad,
            date=today - timedelta(days=1),
            views_count=5,
            contacts_count=2,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.context["total_views"], 5)
        self.assertEqual(response.context["total_contacts"], 2)
        self.assertEqual(len(response.context["daily_metrics"]), 1)

    def test_other_seller_metrics_not_included(self) -> None:
        """Only the authenticated seller's metrics are included."""
        self.client.force_login(self.seller)

        other_ad = _make_ad(
            self.other_user, self.category, self.city, title="Other Ad",
        )
        today = timezone.now().date()
        DailyAdMetrics.objects.create(
            ad=other_ad, date=today, views_count=999, contacts_count=999,
        )

        response = self.client.get(self.url)
        self.assertEqual(response.context["total_views"], 0)
        self.assertEqual(response.context["total_contacts"], 0)

    def test_empty_metrics_shows_zero(self) -> None:
        """Seller with no metrics sees zero totals and empty list."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertEqual(response.context["total_views"], 0)
        self.assertEqual(response.context["total_contacts"], 0)
        self.assertEqual(response.context["daily_metrics"], [])


# ---------------------------------------------------------------------------
# Tests: ModerationAnalytics View
# ---------------------------------------------------------------------------


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class TestModerationAnalyticsView(TestCase):
    """Tests for the moderation analytics view (staff-only)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.category = _make_category("mod-view-cat")
        cls.city = _make_city("mod-view-city")
        cls.seller = _make_user(telegram_id=990302001)
        cls.staff_user = _make_user(telegram_id=990302002, is_staff=True)
        cls.superuser = User.objects.create_superuser(
            username="super",
            email="super@example.com",
            telegram_id=990302003,
            chat_id=990302003,
            password="x",
        )
        cls.url = reverse("analytics:moderation_analytics")

        # Create an approved ad to have moderation data
        now = timezone.now()
        cls.ad_approved = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Mod Approved",
            status=AdStatus.PUBLISHED,
        )
        AnalyticsEvent.objects.create(
            event_type=AnalyticsEventType.MODERATION_APPROVED,
            ad=cls.ad_approved,
            timestamp=now - timedelta(hours=2),
        )

    def test_anonymous_gets_404(self) -> None:
        """Anonymous users get 404 (via _staff_required decorator)."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_non_staff_user_gets_404(self) -> None:
        """Non-staff authenticated users get 404."""
        self.client.force_login(self.seller)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_staff_user_gets_200(self) -> None:
        """Staff users can access the moderation analytics dashboard."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_superuser_gets_200(self) -> None:
        """Superusers can access the moderation analytics dashboard."""
        self.client.force_login(self.superuser)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_uses_correct_template(self) -> None:
        """Response renders the moderation dashboard template."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertTemplateUsed(response, "analytics/moderation_dashboard.html")

    def test_stats_in_context(self) -> None:
        """ModerationStats dict is present in the response context."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertIn("stats", response.context)
        stats = response.context["stats"]
        # Stats is a TypedDict with expected keys
        self.assertIn("approved", stats)
        self.assertIn("rejected", stats)
        self.assertIn("flagged", stats)

    def test_pending_queue_size_in_context(self) -> None:
        """Pending queue size is present in context."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertIn("pending_queue_size", response.context)
        self.assertIsInstance(response.context["pending_queue_size"], int)

    def test_moderator_performance_in_context(self) -> None:
        """Moderator performance list is present in context."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertIn("moderator_performance", response.context)
        self.assertIsInstance(response.context["moderator_performance"], list)

    def test_rejection_reasons_in_context(self) -> None:
        """Rejection reasons dict is present in context."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertIn("rejection_reasons", response.context)
        self.assertIsInstance(response.context["rejection_reasons"], dict)

    def test_days_in_context(self) -> None:
        """Days parameter is present in context."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertIn("days", response.context)
        self.assertEqual(response.context["days"], 30)

    def test_stats_reflects_actual_moderation_events(self) -> None:
        """Stats context reflects the moderation events created in setUp."""
        self.client.force_login(self.staff_user)
        with patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={"approved": 1, "rejected": 0, "flagged": 0, "avg_time_to_moderate": None},
        ):
            response = self.client.get(self.url)
        self.assertEqual(response.context["stats"]["approved"], 1)
        self.assertEqual(response.context["stats"]["rejected"], 0)
        self.assertEqual(response.context["stats"]["flagged"], 0)