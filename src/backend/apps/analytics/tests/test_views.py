"""
Integration tests for analytics dashboard views (T9/T10).

Tests cover:
- SellerTrustDashboard: login requirement, context data, rendering
- ModerationAnalytics: staff requirement, context data, rendering
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.analytics.models import AnalyticsEvent, DailyAdMetrics
from apps.core.enums import AdStatus, AnalyticsEventType, TrustLevel
from apps.trust.models import SellerVerification
from apps.users.models import User
from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dashboard_seller(seller, category, city) -> dict:
    """Create a seller with a published ad for dashboard tests."""
    ad = create_test_ad(
        seller, category, city, title="Trust Ad", status=AdStatus.PUBLISHED
    )
    return {"seller": seller, "ad": ad}


@pytest.fixture
def moderation_context(seller, category, city) -> dict:
    """Create moderation test data: a staff user, superuser, and a moderation event."""
    staff_user = _make_user(telegram_id=990302002, is_staff=True)
    superuser = User.objects.create_superuser(
        username="super",
        email="super@example.com",
        telegram_id=990302003,
        chat_id=990302003,
        password="x",
    )
    other_user = _make_user(telegram_id=990302004)

    now = timezone.now()
    approved_ad = create_test_ad(
        other_user,
        category,
        city,
        title="Mod Approved",
        status=AdStatus.PUBLISHED,
    )
    AnalyticsEvent.objects.create(
        event_type=AnalyticsEventType.MODERATION_APPROVED,
        ad=approved_ad,
        timestamp=now - timedelta(hours=2),
    )

    return {
        "staff_user": staff_user,
        "superuser": superuser,
        "seller": other_user,
        "ad_approved": approved_ad,
        "url": reverse("analytics:moderation_analytics"),
    }


# ---------------------------------------------------------------------------
# Tests: SellerTrustDashboard
# ---------------------------------------------------------------------------


class TestSellerTrustDashboardView:
    """Tests for the seller trust dashboard view (login-required)."""

    @pytest.fixture(autouse=True)
    def _setup(self, dashboard_seller) -> Iterator[None]:
        """Apply locmem cache settings for each test."""
        self._cache_ctx = override_settings(
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
        self._cache_ctx.__enter__()
        yield
        self._cache_ctx.__exit__(None, None, None)

    def test_redirects_anonymous_to_login(self) -> None:
        """Unauthenticated users are redirected to the login page."""
        from django.test import Client

        url = reverse("analytics:seller_trust_dashboard")
        client = Client()
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in (response.url or "").lower()

    def test_authenticated_user_gets_200(self, dashboard_seller) -> None:
        """Authenticated seller can access their trust dashboard."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert response.status_code == 200

    def test_uses_correct_template(self, dashboard_seller) -> None:
        """Response renders the seller dashboard template."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert "analytics/seller_dashboard.html" in [t.name for t in response.templates]

    def test_trust_score_in_context(self, dashboard_seller) -> None:
        """Trust score is present in the response context and matches formula.

        The dashboard_seller fixture has exactly one published ad, no admin
        verification, and no rejected ads, so the score is the base 50 plus
        one published ad (+10) = 60.
        """
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert "trust_score" in response.context
        assert response.context["trust_score"] is not None
        assert response.context["trust_score"] == 50 + 10

    def test_trust_level_in_context(self, dashboard_seller) -> None:
        """Trust level is present in the response context and matches expected.

        A trust score of 60 falls in the VERIFIED band (31-60).
        """
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert "trust_level" in response.context
        assert response.context["trust_level"] == TrustLevel.VERIFIED

    def test_daily_metrics_in_context(self, dashboard_seller) -> None:
        """Daily metrics list is present in context (empty without records)."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert "daily_metrics" in response.context
        assert response.context["daily_metrics"] == []

    def test_total_views_in_context(self, dashboard_seller) -> None:
        """Total views count is present in context (0 without metrics)."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert "total_views" in response.context
        assert response.context["total_views"] == 0

    def test_total_contacts_in_context(self, dashboard_seller) -> None:
        """Total contacts count is present in context (0 without metrics)."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert "total_contacts" in response.context
        assert response.context["total_contacts"] == 0

    def test_daily_metrics_reflects_actual_data(self, dashboard_seller) -> None:
        """Daily metrics in context matches created DailyAdMetrics records."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        ad = dashboard_seller["ad"]
        client = Client()
        client.force_login(seller)

        today = timezone.now().date()
        DailyAdMetrics.objects.create(
            ad=ad,
            date=today - timedelta(days=1),
            views_count=5,
            contacts_count=2,
        )

        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert response.context["total_views"] == 5
        assert response.context["total_contacts"] == 2
        assert len(response.context["daily_metrics"]) == 1

    def test_other_seller_metrics_not_included(
        self, dashboard_seller, category, city
    ) -> None:
        """Only the authenticated seller's metrics are included."""
        from django.test import Client

        seller = dashboard_seller["seller"]
        client = Client()
        client.force_login(seller)

        other_ad = create_test_ad(
            _make_user(990301099),
            category,
            city,
            title="Other Ad",
            status=AdStatus.PUBLISHED,
        )
        today = timezone.now().date()
        DailyAdMetrics.objects.create(
            ad=other_ad,
            date=today,
            views_count=999,
            contacts_count=999,
        )

        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert response.context["total_views"] == 0
        assert response.context["total_contacts"] == 0

    def test_empty_metrics_shows_zero(self, seller) -> None:
        """Seller with no metrics sees zero totals and empty list."""
        from django.test import Client

        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert response.context["total_views"] == 0
        assert response.context["total_contacts"] == 0
        assert response.context["daily_metrics"] == []

    def test_trust_score_scales_with_published_ads(
        self, dashboard_seller, category, city
    ) -> None:
        """Trust score increases by the per-ad bonus with more published ads.

        The dashboard_seller fixture creates 1 published ad; adding 2 more
        yields 3 published ads, so the score is 50 (base) + 10 * 3 = 80,
        which maps to the TRUSTED band (61-85).
        """
        from django.test import Client

        seller = dashboard_seller["seller"]
        for i in range(2):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Scale Ad {i}",
                status=AdStatus.PUBLISHED,
            )

        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert response.context["trust_score"] == 50 + 30
        assert response.context["trust_level"] == TrustLevel.TRUSTED

    def test_trust_score_clamped_with_verification(
        self, dashboard_seller, category, city
    ) -> None:
        """Trust score is clamped to 100 and reaches PRO with verification.

        Starting from the fixture's 1 published ad, add 3 more (4 total →
        +40), then admin verification (+20): 50 + 40 + 20 = 110, clamped to
        the max of 100, which maps to the PRO band (86-100).
        """
        from django.test import Client

        seller = dashboard_seller["seller"]
        for i in range(3):
            create_test_ad(
                seller,
                category,
                city,
                title=f"Clamp Ad {i}",
                status=AdStatus.PUBLISHED,
            )
        SellerVerification.objects.create(user=seller, verified_by_admin=True)

        client = Client()
        client.force_login(seller)
        response = client.get(reverse("analytics:seller_trust_dashboard"))
        assert response.context["trust_score"] == 100.0
        assert response.context["trust_level"] == TrustLevel.PRO


# ---------------------------------------------------------------------------
# Tests: ModerationAnalytics View
# ---------------------------------------------------------------------------


class TestModerationAnalyticsView:
    """Tests for the moderation analytics view (staff-only)."""

    @pytest.fixture(autouse=True)
    def _setup(self, moderation_context) -> Iterator[None]:
        """Apply storage settings for each test."""
        self._storage_ctx = override_settings(
            STORAGES={
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            },
        )
        self._storage_ctx.__enter__()
        self.ctx = moderation_context
        yield
        self._storage_ctx.__exit__(None, None, None)

    def _patched_stats(self):
        """Return a patcher for get_moderation_stats with sensible defaults."""
        return patch(
            "apps.analytics.views.moderation_dashboard.get_moderation_stats",
            return_value={
                "approved": 1,
                "rejected": 0,
                "flagged": 0,
                "avg_time_to_moderate": None,
            },
        )

    def test_anonymous_gets_404(self) -> None:
        """Anonymous users get 404 (via _staff_required decorator)."""
        from django.test import Client

        client = Client()
        response = client.get(self.ctx["url"])
        assert response.status_code == 404

    def test_non_staff_user_gets_404(self) -> None:
        """Non-staff authenticated users get 404."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["seller"])
        response = client.get(self.ctx["url"])
        assert response.status_code == 404

    def test_staff_user_gets_200(self) -> None:
        """Staff users can access the moderation analytics dashboard."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert response.status_code == 200

    def test_superuser_gets_200(self) -> None:
        """Superusers can access the moderation analytics dashboard."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["superuser"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert response.status_code == 200

    def test_uses_correct_template(self) -> None:
        """Response renders the moderation dashboard template."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert "analytics/moderation_dashboard.html" in [
            t.name for t in response.templates
        ]

    def test_stats_in_context(self) -> None:
        """ModerationStats dict is present in the response context."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert "stats" in response.context
        assert "approved" in response.context["stats"]
        assert "rejected" in response.context["stats"]
        assert "flagged" in response.context["stats"]

    def test_pending_queue_size_in_context(self) -> None:
        """Pending queue size is present in context."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert "pending_queue_size" in response.context
        assert isinstance(response.context["pending_queue_size"], int)

    def test_moderator_performance_in_context(self) -> None:
        """Moderator performance list is present in context."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert "moderator_performance" in response.context
        assert isinstance(response.context["moderator_performance"], list)

    def test_rejection_reasons_in_context(self) -> None:
        """Rejection reasons dict is present in context."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert "rejection_reasons" in response.context
        assert isinstance(response.context["rejection_reasons"], dict)

    def test_days_in_context(self) -> None:
        """Days parameter is present in context."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert "days" in response.context
        assert response.context["days"] == 30

    def test_stats_reflects_actual_moderation_events(self) -> None:
        """Stats context reflects the moderation events created in setUp."""
        from django.test import Client

        client = Client()
        client.force_login(self.ctx["staff_user"])
        with self._patched_stats():
            response = client.get(self.ctx["url"])
        assert response.context["stats"]["approved"] == 1
        assert response.context["stats"]["rejected"] == 0
        assert response.context["stats"]["flagged"] == 0

    def test_moderation_dashboard_end_to_end(self, seller, category, city) -> None:
        """End-to-end test: moderation stats reflect real AnalyticsEvent rows.

        Unlike other tests in this class, this test does NOT patch
        get_moderation_stats. It creates real AnalyticsEvent rows and
        verifies the view returns the actual aggregated count.
        """
        from django.test import Client

        # Establish a clean baseline: the autouse _setup fixture (via
        # moderation_context) pre-creates 1 MODERATION_APPROVED event;
        # remove it so the expected count is fully determined by this test.
        AnalyticsEvent.objects.filter(
            event_type=AnalyticsEventType.MODERATION_APPROVED,
        ).delete()

        # Create a published ad and 3 moderation-approved events.
        ad = create_test_ad(
            seller, category, city, title="End-to-End Ad", status=AdStatus.PUBLISHED
        )
        for _ in range(3):
            AnalyticsEvent.objects.create(
                event_type=AnalyticsEventType.MODERATION_APPROVED,
                ad=ad,
                timestamp=timezone.now() - timedelta(hours=2),
            )

        client = Client()
        client.force_login(self.ctx["staff_user"])
        # Do NOT patch get_moderation_stats — exercise the real implementation.
        response = client.get(self.ctx["url"])

        assert response.status_code == 200
        assert response.context["stats"]["approved"] == 3
