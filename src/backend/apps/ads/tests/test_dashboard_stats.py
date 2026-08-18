"""
Integration tests for seller dashboard statistics (TASK_041).

Verifies the dashboard view correctly integrates SellerStats, renders
the stats card, time-range selector, and per-ad view/contact badges
in the HTML response. Uses ``django.test.TestCase`` for DB-backed
assertions with the Django test client.

Requires a working PostgreSQL database per project spec.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.ads.models import Ad
from apps.analytics.models import AnalyticsEvent
from apps.categories.models import Category
from apps.core.enums import AdSource, AdStatus, AnalyticsEventType, TimeRange
from apps.locations.models import City
from apps.users.models import User

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
    return User.objects.create(**defaults)  # type: ignore[arg-type]


def _make_category(slug: str = "dash-cat") -> Category:
    """Create a Category with sensible defaults."""
    return Category.objects.create(
        name="Dashboard Category",
        slug=slug,
    )


def _make_city(slug: str = "dash-city") -> City:
    """Create a City with sensible defaults."""
    return City.objects.create(
        country_code="ME",
        name="Dashboard City",
        region="Test Region",
        slug=slug,
    )


def _make_ad(
    user: User,
    category: Category,
    city: City,
    *,
    title: str = "Dashboard Ad",
    status: AdStatus = AdStatus.PUBLISHED,
    **overrides: object,
) -> Ad:
    """Create an Ad with sensible defaults for dashboard tests."""
    defaults: dict = {
        "user": user,
        "title": title,
        "description": "Dashboard test description",
        "category": category,
        "city": city,
        "category_name": category.name,
        "status": status,
        "source": AdSource.TELEGRAM,
    }
    # PUBLISHED ads require published_at (check constraint ck_ads_published_at_if_published)
    if status == AdStatus.PUBLISHED:
        defaults["published_at"] = timezone.now()
    defaults.update(overrides)
    return Ad.objects.create(**defaults)  # type: ignore[arg-type]


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
# Tests
# ---------------------------------------------------------------------------


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        },
    },
)
class TestDashboardStatsIntegration(TestCase):
    """Integration tests for seller stats in the dashboard view."""

    @classmethod
    def setUpTestData(cls) -> None:
        """Create shared fixtures for all test methods.

        Data layout:
        - ``cls.seller`` — the seller whose dashboard we test.
        - 2 published ads (ad_a, ad_b), each with view/contact events.
        - ``cls.other_user`` — another seller (noise, should not appear).
        """
        # --- Taxonomy ---
        cls.category = _make_category("dash-stats-cat")
        cls.city = _make_city("dash-stats-city")

        # --- Users ---
        cls.seller = _make_user(telegram_id=991001001)
        cls.other_user = _make_user(telegram_id=991001002)

        # --- Ads for seller ---
        cls.ad_a = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Ad Alpha",
            status=AdStatus.PUBLISHED,
        )
        cls.ad_b = _make_ad(
            cls.seller,
            cls.category,
            cls.city,
            title="Ad Beta",
            status=AdStatus.PUBLISHED,
        )

        now = timezone.now()

        # --- Events for ad_a ---
        _make_event(cls.ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=1))
        _make_event(cls.ad_a, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=5))
        _make_event(cls.ad_a, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(days=2))

        # --- Events for ad_b ---
        _make_event(cls.ad_b, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(days=3))
        _make_event(cls.ad_b, AnalyticsEventType.CONTACT_INITIATED, timestamp=now - timedelta(days=15))

        # --- Noise: other seller's events (should never be counted) ---
        other_ad = _make_ad(
            cls.other_user,
            cls.category,
            cls.city,
            title="Other Ad",
            status=AdStatus.PUBLISHED,
        )
        _make_event(other_ad, AnalyticsEventType.AD_VIEWED, timestamp=now - timedelta(hours=1))

    def setUp(self) -> None:
        """Set up the test client and log in the seller."""
        self.client = Client()
        self.client.force_login(self.seller)

    # ── Context assertions ──────────────────────────────────────────────

    def test_dashboard_returns_200_for_authenticated_user(self) -> None:
        """Authenticated user can access the dashboard."""
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_dashboard_redirects_unauthenticated(self) -> None:
        """Unauthenticated user is redirected to login."""
        client = Client()
        response = client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)

    def test_context_contains_seller_stats(self) -> None:
        """Dashboard context includes seller_stats dict."""
        response = self.client.get("/dashboard/")
        self.assertIn("seller_stats", response.context)
        stats = response.context["seller_stats"]
        self.assertIn("total_views", stats)
        self.assertIn("total_contacts", stats)
        self.assertIn("ads_published", stats)
        self.assertIn("per_ad_stats", stats)

    def test_context_contains_per_ad_stats_dict(self) -> None:
        """Dashboard context includes per_ad_stats_dict lookup."""
        response = self.client.get("/dashboard/")
        self.assertIn("per_ad_stats_dict", response.context)
        lookup = response.context["per_ad_stats_dict"]
        assert self.ad_a.id is not None
        assert self.ad_b.id is not None
        self.assertIn(self.ad_a.id, lookup)
        self.assertIn(self.ad_b.id, lookup)
        self.assertEqual(lookup[self.ad_a.id]["views"], 2)
        self.assertEqual(lookup[self.ad_a.id]["contacts"], 1)
        self.assertEqual(lookup[self.ad_b.id]["views"], 1)
        self.assertEqual(lookup[self.ad_b.id]["contacts"], 1)

    def test_context_contains_time_range_options(self) -> None:
        """Dashboard context includes time_range_options for template."""
        response = self.client.get("/dashboard/")
        self.assertIn("time_range_options", response.context)
        options = response.context["time_range_options"]
        self.assertEqual(len(options), 3)
        values = [v for v, _ in options]
        self.assertIn(TimeRange.ALL_TIME.value, values)
        self.assertIn(TimeRange.THIRTY_DAYS.value, values)
        self.assertIn(TimeRange.SEVEN_DAYS.value, values)

    def test_context_contains_selected_time_range(self) -> None:
        """Dashboard context includes selected_time_range defaulting to all_time."""
        response = self.client.get("/dashboard/")
        self.assertIn("selected_time_range", response.context)
        self.assertEqual(response.context["selected_time_range"], TimeRange.ALL_TIME.value)

    # ── Time range filtering ────────────────────────────────────────────

    def test_time_range_param_parses_seven_days(self) -> None:
        """?time_range=7_days filters stats to last 7 days."""
        response = self.client.get("/dashboard/?time_range=7_days")
        self.assertEqual(response.context["selected_time_range"], TimeRange.SEVEN_DAYS.value)
        stats = response.context["seller_stats"]
        # ad_a: 2 views (day 1, day 5), 1 contact (day 2)
        # ad_b: 1 view (day 3), 0 contacts (day 15 is beyond 7d)
        self.assertEqual(stats["total_views"], 3)
        self.assertEqual(stats["total_contacts"], 1)

    def test_time_range_param_parses_thirty_days(self) -> None:
        """?time_range=30_days filters stats to last 30 days."""
        response = self.client.get("/dashboard/?time_range=30_days")
        self.assertEqual(response.context["selected_time_range"], TimeRange.THIRTY_DAYS.value)
        stats = response.context["seller_stats"]
        # ad_a: 2 views, 1 contact; ad_b: 1 view, 1 contact (day 15 is within 30d)
        self.assertEqual(stats["total_views"], 3)
        self.assertEqual(stats["total_contacts"], 2)

    def test_invalid_time_range_falls_back_to_all_time(self) -> None:
        """Invalid time_range value defaults to ALL_TIME."""
        response = self.client.get("/dashboard/?time_range=invalid")
        self.assertEqual(response.context["selected_time_range"], TimeRange.ALL_TIME.value)

    # ── Stats correctness ───────────────────────────────────────────────

    def test_stats_are_correct_all_time(self) -> None:
        """ALL_TIME stats aggregate all events correctly."""
        response = self.client.get("/dashboard/")
        stats = response.context["seller_stats"]
        # ad_a: 2 views, 1 contact; ad_b: 1 view, 1 contact → total 3 views, 2 contacts
        self.assertEqual(stats["total_views"], 3)
        self.assertEqual(stats["total_contacts"], 2)
        self.assertEqual(stats["ads_published"], 2)

    def test_stats_other_seller_excluded(self) -> None:
        """Other seller's events are not included in stats."""
        response = self.client.get("/dashboard/")
        stats = response.context["seller_stats"]
        # Only 2 ads for our seller, 3 views total (other seller's ad/view are excluded)
        self.assertEqual(stats["ads_published"], 2)
        self.assertEqual(stats["total_views"], 3)

    # ── HTML rendering ──────────────────────────────────────────────────

    def test_html_contains_stats_card(self) -> None:
        """Dashboard HTML includes the stats summary card."""
        response = self.client.get("/dashboard/")
        html = response.content.decode()
        # Stats card should contain total_views, total_contacts, ads_published values
        self.assertIn("3", html)  # total_views
        self.assertIn("2", html)  # total_contacts

    def test_html_contains_time_range_selector(self) -> None:
        """Dashboard HTML includes the time range select element."""
        response = self.client.get("/dashboard/")
        html = response.content.decode()
        self.assertIn("time_range", html)
        self.assertIn("All Time", html)
        self.assertIn("30 Days", html)
        self.assertIn("7 Days", html)

    def test_html_contains_per_ad_stats(self) -> None:
        """Dashboard HTML includes per-ad view and contact counts."""
        response = self.client.get("/dashboard/")
        html = response.content.decode()
        # ad_a has 2 views, 1 contact
        self.assertIn("Ad Alpha", html)
        # ad_b has 1 view, 1 contact
        self.assertIn("Ad Beta", html)
        # View and contact count badges appear in the response.
        # Each ad has exactly 1 contact, so the template renders the
        # singular form "1 contact" (pluralize produces no "s" for count=1).
        self.assertIn("views", html)
        self.assertIn("contact", html)
        # Verify the count text alongside the label
        self.assertIn("1 contact", html)

    def test_html_contains_ad_titles(self) -> None:
        """Dashboard HTML lists ad titles."""
        response = self.client.get("/dashboard/")
        html = response.content.decode()
        self.assertIn("Ad Alpha", html)
        self.assertIn("Ad Beta", html)

    # ── Edge cases ──────────────────────────────────────────────────────

    def test_empty_stats_when_no_events(self) -> None:
        """Seller with no events gets zeroed stats."""
        empty_user = _make_user(telegram_id=991001003)
        self.client.force_login(empty_user)
        _make_ad(
            empty_user,
            self.category,
            self.city,
            title="Lonely Ad",
            status=AdStatus.PUBLISHED,
        )
        response = self.client.get("/dashboard/")
        stats = response.context["seller_stats"]
        self.assertEqual(stats["total_views"], 0)
        self.assertEqual(stats["total_contacts"], 0)
        self.assertEqual(stats["ads_published"], 1)
        self.assertEqual(len(stats["per_ad_stats"]), 1)
        self.assertEqual(stats["per_ad_stats"][0]["views"], 0)
        self.assertEqual(stats["per_ad_stats"][0]["contacts"], 0)
