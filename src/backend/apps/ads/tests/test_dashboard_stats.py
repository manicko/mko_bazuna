"""
Integration tests for seller dashboard statistics (TASK_041).

Verifies the dashboard view correctly integrates SellerStats, renders
the stats card, time-range selector, and per-ad view/contact badges
in the HTML response.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.core.enums import AdStatus, AnalyticsEventType, TimeRange
from apps.users.models import User

from conftest import create_test_ad

pytestmark = [pytest.mark.django_db, pytest.mark.slow, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_user(telegram_id: int = 991000001, **overrides: object) -> User:
    """Create a User with sensible defaults for dashboard tests."""
    defaults: dict = {
        "telegram_id": telegram_id,
        "chat_id": telegram_id,
        "username": None,
        "password": "x",
    }
    defaults.update(overrides)
    return User.objects.create(**defaults)


def _make_event(
    ad: Ad,
    event_type: AnalyticsEventType,
    *,
    timestamp: timezone.datetime | None = None,
    user: User | None = None,
) -> AnalyticsEvent:
    """Create an AnalyticsEvent with sensible defaults."""
    return AnalyticsEvent.objects.create(
        event_type=event_type,
        ad=ad,
        user=user,
        timestamp=timestamp or timezone.now(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dashboard_seller(category, city):
    """Create a seller with 2 published ads and event data.

    Also creates another seller (noise) whose events should not appear.
    """
    seller = _make_user(telegram_id=991001001)
    other_user = _make_user(telegram_id=991001002)

    ad_a = create_test_ad(
        seller, category, city, title="Ad Alpha", status=AdStatus.PUBLISHED
    )
    ad_b = create_test_ad(
        seller, category, city, title="Ad Beta", status=AdStatus.PUBLISHED
    )

    now = timezone.now()

    # Events for ad_a
    _make_event(ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=1))
    _make_event(ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=5))
    _make_event(
        ad_a, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(days=2)
    )

    # Events for ad_b
    _make_event(ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=3))
    _make_event(
        ad_b, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(days=15)
    )

    # Noise: other seller's events
    other_ad = create_test_ad(
        other_user, category, city, title="Other Ad", status=AdStatus.PUBLISHED
    )
    _make_event(
        other_ad, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(hours=1)
    )

    return {
        "seller": seller,
        "other_user": other_user,
        "ad_a": ad_a,
        "ad_b": ad_b,
        "other_ad": other_ad,
    }


@pytest.fixture
def dashboard_client(dashboard_seller):
    """Return a test client logged in as the dashboard seller."""
    client = Client()
    client.force_login(dashboard_seller["seller"])
    return client


@pytest.fixture(autouse=True)
def _locmem_cache():
    """Use in-process locmem cache for deterministic SellerStats behavior."""
    with override_settings(
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
    ):
        yield


# ---------------------------------------------------------------------------
# Tests: Context assertions
# ---------------------------------------------------------------------------


class TestDashboardContext:
    """Integration tests for seller stats in the dashboard view."""

    def test_dashboard_returns_200_for_authenticated_user(
        self, dashboard_client
    ) -> None:
        """Authenticated user can access the dashboard."""
        response = dashboard_client.get("/dashboard/")
        assert response.status_code == 200

    def test_dashboard_redirects_unauthenticated(self) -> None:
        """Unauthenticated user is redirected to login."""
        client = Client()
        response = client.get("/dashboard/")
        assert response.status_code == 302

    def test_context_contains_seller_stats(self, dashboard_client) -> None:
        """Dashboard context includes seller_stats dict."""
        response = dashboard_client.get("/dashboard/")
        assert "seller_stats" in response.context
        stats = response.context["seller_stats"]
        assert "total_views" in stats
        assert "total_contacts" in stats
        assert "ads_published" in stats
        assert "per_ad_stats" in stats

    def test_context_contains_per_ad_stats_dict(
        self, dashboard_client, dashboard_seller
    ) -> None:
        """Dashboard context includes per_ad_stats_dict lookup."""
        response = dashboard_client.get("/dashboard/")
        assert "per_ad_stats_dict" in response.context
        lookup = response.context["per_ad_stats_dict"]
        ad_a = dashboard_seller["ad_a"]
        ad_b = dashboard_seller["ad_b"]
        assert ad_a.id is not None
        assert ad_b.id is not None
        assert ad_a.id in lookup
        assert ad_b.id in lookup
        assert lookup[ad_a.id]["views"] == 2
        assert lookup[ad_a.id]["contacts"] == 1
        assert lookup[ad_b.id]["views"] == 1
        assert lookup[ad_b.id]["contacts"] == 1

    def test_context_contains_time_range_options(self, dashboard_client) -> None:
        """Dashboard context includes time_range_options for template."""
        response = dashboard_client.get("/dashboard/")
        assert "time_range_options" in response.context
        options = response.context["time_range_options"]
        assert len(options) == 3
        values = [v for v, _ in options]
        assert TimeRange.ALL_TIME.value in values
        assert TimeRange.THIRTY_DAYS.value in values
        assert TimeRange.SEVEN_DAYS.value in values

    def test_context_contains_selected_time_range(self, dashboard_client) -> None:
        """Dashboard context includes selected_time_range defaulting to all_time."""
        response = dashboard_client.get("/dashboard/")
        assert "selected_time_range" in response.context
        assert response.context["selected_time_range"] == TimeRange.ALL_TIME.value


# ---------------------------------------------------------------------------
# Time range filtering
# ---------------------------------------------------------------------------


class TestDashboardTimeRange:
    """Tests for time range filtering in the dashboard view."""

    def test_time_range_param_parses_seven_days(self, dashboard_client) -> None:
        """?time_range=7_days filters stats to last 7 days."""
        response = dashboard_client.get("/dashboard/?time_range=7_days")
        assert response.context["selected_time_range"] == TimeRange.SEVEN_DAYS.value
        stats = response.context["seller_stats"]
        # ad_a: 2 views (day 1, day 5), 1 contact (day 2)
        # ad_b: 1 view (day 3), 0 contacts (day 15 is beyond 7d)
        assert stats["total_views"] == 3
        assert stats["total_contacts"] == 1

    def test_time_range_param_parses_thirty_days(self, dashboard_client) -> None:
        """?time_range=30_days filters stats to last 30 days."""
        response = dashboard_client.get("/dashboard/?time_range=30_days")
        assert response.context["selected_time_range"] == TimeRange.THIRTY_DAYS.value
        stats = response.context["seller_stats"]
        # ad_a: 2 views, 1 contact; ad_b: 1 view, 1 contact (day 15 is within 30d)
        assert stats["total_views"] == 3
        assert stats["total_contacts"] == 2

    def test_invalid_time_range_falls_back_to_all_time(self, dashboard_client) -> None:
        """Invalid time_range value defaults to ALL_TIME."""
        response = dashboard_client.get("/dashboard/?time_range=invalid")
        assert response.context["selected_time_range"] == TimeRange.ALL_TIME.value


# ---------------------------------------------------------------------------
# Stats correctness
# ---------------------------------------------------------------------------


class TestDashboardStatsCorrectness:
    """Tests for stats aggregation correctness in the dashboard view."""

    def test_stats_are_correct_all_time(self, dashboard_client) -> None:
        """ALL_TIME stats aggregate all events correctly."""
        response = dashboard_client.get("/dashboard/")
        stats = response.context["seller_stats"]
        # ad_a: 2 views, 1 contact; ad_b: 1 view, 1 contact → total 3 views, 2 contacts
        assert stats["total_views"] == 3
        assert stats["total_contacts"] == 2
        assert stats["ads_published"] == 2

    def test_stats_other_seller_excluded(self, dashboard_client) -> None:
        """Other seller's events are not included in stats."""
        response = dashboard_client.get("/dashboard/")
        stats = response.context["seller_stats"]
        assert stats["ads_published"] == 2
        assert stats["total_views"] == 3


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


class TestDashboardHtmlRendering:
    """Tests for HTML rendering of dashboard stats."""

    def test_html_contains_stats_card(self, dashboard_client) -> None:
        """Dashboard HTML includes the stats summary card."""
        response = dashboard_client.get("/dashboard/")
        html = response.content.decode()
        assert "3" in html  # total_views
        assert "2" in html  # total_contacts

    def test_html_contains_time_range_selector(self, dashboard_client) -> None:
        """Dashboard HTML includes the time range select element."""
        response = dashboard_client.get("/dashboard/?lang=ru")
        html = response.content.decode()
        assert "time_range" in html
        assert "За всё время" in html
        assert "30 дней" in html
        assert "7 дней" in html

    def test_html_contains_per_ad_stats(self, dashboard_client) -> None:
        """Dashboard HTML includes per-ad view and contact counts."""
        response = dashboard_client.get("/dashboard/?lang=ru")
        html = response.content.decode()
        assert "Ad Alpha" in html
        assert "Ad Beta" in html
        assert "просмот" in html  # "просмотр" / "просмотра" / "просмотров"
        assert "контакт" in html  # "контакт" / "контакта" / "контактов"
        assert "1 контакт" in html  # ad_a has 1 contact → singular

    def test_html_contains_ad_titles(self, dashboard_client) -> None:
        """Dashboard HTML lists ad titles."""
        response = dashboard_client.get("/dashboard/")
        html = response.content.decode()
        assert "Ad Alpha" in html
        assert "Ad Beta" in html


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestDashboardEdgeCases:
    """Tests for edge cases in the dashboard view."""

    def test_empty_stats_when_no_events(self, category, city) -> None:
        """Seller with no events gets zeroed stats."""
        empty_user = _make_user(telegram_id=991001003)
        client = Client()
        client.force_login(empty_user)
        create_test_ad(
            empty_user, category, city, title="Lonely Ad", status=AdStatus.PUBLISHED
        )
        response = client.get("/dashboard/")
        stats = response.context["seller_stats"]
        assert stats["total_views"] == 0
        assert stats["total_contacts"] == 0
        assert stats["ads_published"] == 1
        assert len(stats["per_ad_stats"]) == 1
        assert stats["per_ad_stats"][0]["views"] == 0
        assert stats["per_ad_stats"][0]["contacts"] == 0
